import os, json, re, yaml, time
from pathlib import Path
from datetime import datetime, timezone
import google.generativeai as genai

CAND = Path("data/candidates.jsonl")
SECS = yaml.safe_load(Path("config/sections.yaml").read_text(encoding="utf-8"))
OUT  = Path(os.getenv("TOP_FILE", "data/selected.json"))
TOP_N = int(os.getenv("TOP_PER_SECTION", "5"))                # choose 5 or 10
SHORTLIST = int(os.getenv("SHORTLIST_PER_SECTION", "30"))     # candidates shown to LLM
PAUSE = float(os.getenv("SELECTOR_PAUSE_SECONDS", "0.6"))
DOMAIN_CAP = int(os.getenv("DOMAIN_CAP_PER_SECTION", "2"))    # diversity within a section

# Configure Gemini
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel(os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))

def llm_chat(system_prompt: str, user_prompt: str, max_tokens: int = 800, temperature: float = 0.2) -> str:
    """Return model text using Gemini Flash."""
    try:
        response = model.generate_content(
            user_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=temperature,
                top_p=0.9,
                max_output_tokens=max_tokens,
            )
        )
        return response.text or ""
    except Exception as e:
        print(f"Gemini API error: {str(e)[:100]}...")
        return ""

def days_old(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z","")).astimezone(timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return 999

def domain(u):
    m = re.search(r"https?://([^/]+)/?", u or ""); return m.group(1).lower() if m else "unknown"

def assign_section(item):
    text = (item.get("title","") + " " + item.get("text","")).lower()
    url  = item.get("url",""); src = item.get("source","")
    best = None; best_s = -1
    for s in SECS["sections"]:
        sc = 0.0
        for d in s["match"]["domains"]:
            if d in url: sc += 2.5
        for name in s["match"]["sources"]:
            if name.lower() in src.lower(): sc += 2.0
        for kw in s["match"]["keywords"]:
            if kw.lower() in text: sc += 1.0
        if sc > best_s: best, best_s = s, sc
    return best or next(x for x in SECS["sections"] if x["id"]=="applied")

def load_candidates():
    items=[]
    for line in CAND.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        it = json.loads(line)
        sec = assign_section(it)
        it["section_id"]=sec["id"]; it["section_title"]=sec["title"]; it["section_index"]=sec["index"]
        items.append(it)
    return items

SYS = ("You are an editor for senior IT leaders. From the list, PICK EXACTLY N items "
       "that maximize enterprise relevance, novelty, and decision value. Prefer freshness, "
       "source diversity, and clear implications. Output ONLY JSON with keys 'picks' (array of indices) "
       "and 'reasons' (map index->short reason). No other text.")

def build_prompt(section_title, shortlist, n):
    lines=[]
    for i, it in enumerate(shortlist, 1):
        excerpt = (it.get("text","") or "")[:600].replace("\n"," ")
        lines.append(
            f"{i}. title={it['title']} | source={it['source']} | date={it['published']} | url={it['url']}\n"
            f"   excerpt: {excerpt}"
        )
    return f"""Section: {section_title}
Pick exactly {n}.

Candidates (numbered):
{chr(10).join(lines)}

Return JSON:
{{
  "picks": [<exactly {n} indices from 1..{len(shortlist)}>],
  "reasons": {{"<index>":"<why useful for leaders>"}}
}}"""

def coerce_json(s):
    s = re.sub(r"^```(json)?\s*|\s*```$", "", (s or "").strip(), flags=re.I)
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.S|re.I)
    m = re.search(r"\{.*\}", s, flags=re.S)
    try: return json.loads(m.group(0) if m else s)
    except Exception: return {}

def select_for_section(section, items, n):
    # shortlist: recent first, then longer articles
    short = sorted(items, key=lambda x: (days_old(x["published"]), -len(x.get("text",""))))[:SHORTLIST]
    if not short: return []

    payload = llm_chat(SYS, build_prompt(section["title"], short, n), max_tokens=900, temperature=0.2)
    data = coerce_json(payload)
    picks = data.get("picks") or []

    # sanitize picks to unique 1..len(short)
    picks = [int(p) for p in picks if str(p).isdigit() and 1 <= int(p) <= len(short)]
    uniq = []
    for p in picks:
        if p not in uniq: uniq.append(p)
    # backfill if fewer than n
    k = 1
    while len(uniq) < min(n, len(short)):
        if k not in uniq and k <= len(short): uniq.append(k)
        k += 1

    # enforce per-domain cap
    chosen=[]; per={}
    for idx in uniq:
        cand = dict(short[idx-1])
        d = domain(cand["url"]); per[d] = per.get(d,0) + 1
        if per[d] <= DOMAIN_CAP:
            chosen.append(cand)
        if len(chosen) == n: break

    # rank within section
    for r, it in enumerate(chosen, 1):
        it["rank"] = r
    # attach editor reasons if provided
    reasons = data.get("reasons") or {}
    for i, it in enumerate(chosen, 1):
        it["editor_reason"] = reasons.get(str(i)) or reasons.get(str(i).zfill(1), "")

    time.sleep(PAUSE)
    return chosen

def main():
    all_items = load_candidates()
    by_sec = {}
    for it in all_items:
        by_sec.setdefault(it["section_id"], []).append(it)

    out=[]
    for sid in SECS["order"]:
        section = next(s for s in SECS["sections"] if s["id"]==sid)
        out.extend(select_for_section(section, by_sec.get(sid, []), TOP_N))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT} with {len(out)} items (Top {TOP_N} per section)")

if __name__ == "__main__":
    main()

