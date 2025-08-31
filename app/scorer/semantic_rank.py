import json, re, math, yaml
from pathlib import Path
from datetime import datetime, timezone
from fastembed import TextEmbedding
import numpy as np

IN  = Path("data/candidates.jsonl")
OUT = Path("data/top10.json")

# -------- 1) Axes & keywords
AXIS_PROMPTS = {
    "tech": (
        "Does this push the AI/ML research frontier (SOTA, novel evals, new methods, "
        "meaningful benchmarks, scaling insights)?"
    ),
    "app": (
        "Is this directly useful for enterprises or security teams (deployability, safety, "
        "governance, latency/throughput, SDKs, incident reports, mitigations)?"
    ),
    "biz": (
        "Is there material business impact (pricing/GA launches, partnerships, adoption, ROI, "
        "clear productization or cost reductions)?"
    ),
}
LEX = {
    "tech":  ["arxiv","benchmark","sota","dataset","eval","preprint","architecture","optimization","scaling law"],
    "app":   ["enterprise","deployment","latency","throughput","sdk","guardrail","governance","policy","safety","observability"],
    "sec":   ["security","prompt injection","exfiltration","jailbreak","leak","rbac","data loss","pii"],
    "biz":   ["launch","pricing","general availability","GA","customers","revenue","cost","partnership","integration","roadmap"],
}

# -------- 2) Small helpers
def _cos(a,b): return float(np.dot(a,b) / (np.linalg.norm(a)*np.linalg.norm(b) + 1e-8))

def _days_old(iso):
    dt = datetime.fromisoformat(iso.replace("Z","")).astimezone(timezone.utc)
    return max(0, (datetime.now(timezone.utc) - dt).days)

def _kw_score(text, words):
    t = text.lower()
    hits = sum(t.count(w) for w in words)
    # length-normalized (diminishing returns)
    return min(1.0, hits / (1 + math.log10(len(t) + 10)))

def _sigmoid(z):  # smooth calibration to 0..1
    return 1 / (1 + math.exp(-z))

def _mmr_select(rows, embeddings, k=10, diversity=0.3):
    """Greedy selection: score - diversity * max_sim_with_selected."""
    selected = []
    selected_idx = []
    sims = embeddings @ embeddings.T
    for _ in range(min(k, len(rows))):
        best_i, best_val = None, -1e9
        for i, r in enumerate(rows):
            if i in selected_idx: continue
            penal = 0.0 if not selected_idx else max(sims[i, j] for j in selected_idx)
            val = r["final_score"] - diversity * penal
            if val > best_val:
                best_val, best_i = val, i
        selected_idx.append(best_i)
        selected.append(rows[best_i])
    # re-rank by original score
    selected.sort(key=lambda x: x["final_score"], reverse=True)
    for i, r in enumerate(selected, 1):
        r["rank"] = i
    return selected

# -------- 3) Load items
lines = IN.read_text(encoding="utf-8").splitlines() if IN.exists() else []
items = [json.loads(l) for l in lines if l.strip()]

if not items:
    OUT.write_text("[]", encoding="utf-8")
    raise SystemExit("No candidates found. Did collector run?")

# -------- 4) Build texts for embedding (title + first 1.5k chars)
def clip(t, n=1500): return (t or "")[:n]
texts = [ (it.get("title","") + " — " + clip(it.get("text",""))) for it in items ]

# Fast, tiny embedding model (downloads once in CI)
embedder = TextEmbedding("BAAI/bge-small-en-v1.5")
doc_emb = np.vstack([np.array(e) for e in embedder.embed(texts)])

# Anchor embeddings for each axis
axis_emb = {k: np.array(next(embedder.embed([v]))) for k,v in AXIS_PROMPTS.items()}

# -------- 5) Score each item (keywords + semantics + time + security)
rows = []
for it, emb in zip(items, doc_emb):
    text = (it.get("title","") + " " + it.get("text","")).lower()

    # keyword signals
    kw_tech = _kw_score(text, LEX["tech"])
    kw_app  = _kw_score(text, LEX["app"]) + 0.5 * _kw_score(text, LEX["sec"])
    kw_biz  = _kw_score(text, LEX["biz"])

    # semantic similarity to axis prompts
    sim_tech = _cos(emb, axis_emb["tech"])
    sim_app  = _cos(emb, axis_emb["app"])
    sim_biz  = _cos(emb, axis_emb["biz"])

    # combine per-axis, calibrate with sigmoid
    tech = _sigmoid(2.2*sim_tech + 1.2*kw_tech)
    app  = _sigmoid(2.2*sim_app  + 1.2*kw_app)
    biz  = _sigmoid(2.0*sim_biz  + 1.0*kw_biz)

    # freshness bonus (0..1 over 0–7 days)
    timely = max(0.0, 1.0 - _days_old(it["published"])/7.0)

    # security multiplier if security words present
    sec_flag = _kw_score(text, LEX["sec"]) > 0
    sec_mult = 1.10 if sec_flag else 1.00

    # weights (tuneable)
    W = yaml.safe_load(Path("config/weights.yaml").read_text())["weights"]
    base = (
        W["technical_innovation"]*tech +
        W["practical_applicability"]*app +
        W["educational_value"]*0.05 +  # small bias towards longer/contextual items
        W["timeliness"]*timely +
        W["community_impact"]*0.0      # placeholder
    )
    final = min(1.0, base * sec_mult)

    # 2-sentence preview (fallback to slice)
    sents = re.split(r"(?<=[.!?])\s+", it.get("text","").strip())
    p1 = (" ".join(sents[:2]) or it.get("text","")[:240]).strip()
    p2 = "Why it matters: implications for enterprises/security/business."

    rows.append({
        "title": it["title"],
        "url": it["url"],
        "source": it["source"],
        "published": it["published"],
        "tech": round(tech,2), "app": round(app,2), "biz": round(biz,2),
        "final_score": float(round(final,3)),
        "summary_p1": p1, "summary_p2": p2
    })

# -------- 6) Diversity: cap 3 per domain + MMR for coverage
def domain(u):
    m = re.search(r"https?://([^/]+)/?", u or ""); return m.group(1).lower() if m else "unknown"

per, capped, emb_kept = {}, [], []
for r, e in sorted(zip(rows, doc_emb), key=lambda x: x[0]["final_score"], reverse=True):
    d = domain(r["url"]); per[d] = per.get(d,0) + 1
    if per[d] <= 3:  # source cap
        capped.append(r); emb_kept.append(e)
if len(capped) > 10:
    top10 = _mmr_select(capped, np.vstack(emb_kept), k=10, diversity=0.35)
else:
    top10 = sorted(capped, key=lambda r: r["final_score"], reverse=True)[:10]
    for i, r in enumerate(top10, 1): r["rank"] = i

OUT.write_text(json.dumps(top10, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Wrote {OUT} (n={len(top10)})")

