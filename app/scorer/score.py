import json, re, yaml
from pathlib import Path
from datetime import datetime, timezone
from rapidfuzz import fuzz

W = yaml.safe_load(Path("config/weights.yaml").read_text())["weights"]
SEC_MULT = yaml.safe_load(Path("config/weights.yaml").read_text()).get("security_multiplier", 1.1)

KW = {
    "research": ["arxiv", "paper", "benchmark", "sota", "dataset", "eval", "preprint"],
    "applic":  ["enterprise", "deployment", "production", "governance", "latency", "throughput", "sdk"],
    "security":["security", "prompt injection", "exfiltration", "jailbreak", "leak", "rbac", "dpo", "dp"],
    "business":["launch", "pricing", "partnership", "customers", "ga", "general availability", "roi", "revenue"],
}

def contains_any(text, words):
    t = text.lower()
    return sum(1 for w in words if w in t)

def days_old(iso):
    dt = datetime.fromisoformat(iso.replace("Z","")).astimezone(timezone.utc)
    return max(0, (datetime.now(timezone.utc) - dt).days)

def summarize_two_sentences(text):
    s = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return (" ".join(s[:2]) or text[:280]).strip()

def score(item):
    text = (item.get("title","") + " " + item.get("text","")).lower()
    tech = min(1.0, 0.2*contains_any(text, KW["research"]) + 0.1*(len(item.get("text",""))>3000))
    app  = min(1.0, 0.25*contains_any(text, KW["applic"]) + 0.25*contains_any(text, KW["security"]))
    biz  = min(1.0, 0.25*contains_any(text, KW["business"]))
    timely = max(0.0, 1.0 - (days_old(item["published"])/7.0))  # 0..1 over last 7 days
    edu = min(1.0, 0.0001*len(item.get("text","")))  # longer = more context, crude proxy
    base = (
        W["technical_innovation"]*tech +
        W["practical_applicability"]*app +
        W["timeliness"]*timely +
        W["community_impact"]*0.0 +   # placeholder for stars/mentions later
        W["educational_value"]*edu
    )
    sec_boost = SEC_MULT if contains_any(text, KW["security"]) else 1.0
    return min(1.0, base*sec_boost), tech, app, biz

def domain(url):
    m = re.search(r"https?://([^/]+)/?", url or "")
    return m.group(1).lower() if m else "unknown"

def main():
    lines = Path("data/candidates.jsonl").read_text(encoding="utf-8").splitlines()
    items = [json.loads(l) for l in lines if l.strip()]
    # de-dup near-identical titles
    deduped = []
    for x in items:
        if any(fuzz.token_set_ratio(x["title"], y["title"]) > 90 for y in deduped):
            continue
        deduped.append(x)
    # score
    scored = []
    for it in deduped:
        final, tech, app, biz = score(it)
        p1 = summarize_two_sentences(it.get("text",""))
        p2 = "Why it matters: enterprise/security & business relevance at-a-glance."
        scored.append({
            "title": it["title"], "url": it["url"], "source": it["source"],
            "published": it["published"], "final_score": round(final,3),
            "tech": round(tech,2), "app": round(app,2), "biz": round(biz,2),
            "summary_p1": p1, "summary_p2": p2, "domain": domain(it["url"])
        })
    # diversity cap: max 3 per domain
    capped, per = [], {}
    for s in sorted(scored, key=lambda r: r["final_score"], reverse=True):
        d = s["domain"]; per[d] = per.get(d, 0) + 1
        if per[d] <= 3: capped.append(s)
    top10 = capped[:10]
    for i, row in enumerate(top10): row["rank"] = i+1; row.pop("domain", None)
    Path("data/top10.json").write_text(json.dumps(top10, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Wrote data/top10.json (top 10)")

if __name__ == "__main__":
    main()
