import json, time, yaml, feedparser, re
from pathlib import Path
from datetime import datetime, timedelta, timezone
import urllib.parse
import urllib.request

CFG = yaml.safe_load(Path("config/arxiv.yaml").read_text(encoding="utf-8"))
CAND = Path("data/candidates.jsonl")

API = "http://export.arxiv.org/api/query"  # Atom feed endpoint

def http_get(url, ua="JatayuIndex/1.0 (+https://example.com)"):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def to_iso(struct):
    if not struct: return ""
    dt = datetime(*struct[:6], tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00","Z")

def recent(struct, days):
    if not struct: return False
    dt = datetime(*struct[:6], tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt) <= timedelta(days=days)

def primary_source(e):
    cat = getattr(e, "arxiv_primary_category", {}).get("term") if hasattr(e, "arxiv_primary_category") else None
    return f"arXiv {cat}" if cat else "arXiv"

def get_pdf(e):
    for L in getattr(e, "links", []):
        if L.get("type") == "application/pdf": return L.get("href")
    return None

def main():
    cats = CFG.get("categories", ["cs.AI","cs.CL","cs.LG","stat.ML"])
    days_back = int(CFG.get("days_back", 8))
    max_results = int(CFG.get("max_results", 400))
    include_kw = [k.lower() for k in CFG.get("include_keywords", [])]
    exclude_kw = [k.lower() for k in CFG.get("exclude_keywords", [])]
    min_chars = int(CFG.get("min_chars", 0))

    # Load existing URLs to avoid dups when we append
    seen = set()
    if CAND.exists():
        for line in CAND.read_text(encoding="utf-8").splitlines():
            if not line.strip(): continue
            try:
                u = json.loads(line).get("url")
                if u: seen.add(u)
            except: pass

    # Build a single query across categories, newest first
    q = " OR ".join([f"cat:{c}" for c in cats])
    params = {
        "search_query": q,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": str(max_results),
    }
    url = f"{API}?{urllib.parse.urlencode(params)}"
    raw = http_get(url)
    feed = feedparser.parse(raw)

    added = 0
    out = CAND.open("a", encoding="utf-8")
    for e in feed.entries:
        if not recent(e.get("published_parsed") or e.get("updated_parsed"), days_back):
            continue
        title = (e.get("title") or "").strip()
        abstract = (e.get("summary") or "").strip()
        if len(abstract) < min_chars: 
            continue
        link = e.get("link") or get_pdf(e) or ""
        if not link or link in seen: 
            continue

        hay = (title + " " + abstract).lower()
        if include_kw and not any(k in hay for k in include_kw): 
            continue
        if any(k in hay for k in exclude_kw): 
            continue

        item = {
            "title": title,
            "url": link,
            "source": primary_source(e),
            "published": to_iso(e.get("published_parsed") or e.get("updated_parsed")),
            "text": abstract[:20000],
        }
        out.write(json.dumps(item, ensure_ascii=False) + "\n")
        seen.add(link); added += 1

    out.close()
    print(f"arXiv API: wrote {added} items from {len(feed.entries)} entries (cats={','.join(cats)})")

if __name__ == "__main__":
    main()
