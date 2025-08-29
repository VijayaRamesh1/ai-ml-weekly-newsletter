import json, yaml, feedparser, trafilatura, httpx
from pathlib import Path
from datetime import datetime, timedelta, timezone

OUT = Path("data/candidates.jsonl"); OUT.parent.mkdir(parents=True, exist_ok=True)

def to_iso(ts):
    if not ts: return datetime.now(timezone.utc).isoformat()
    return datetime(*ts[:6], tzinfo=timezone.utc).isoformat()

def recent(ts, days=7):
    dt = datetime.now(timezone.utc) if not ts else datetime(*ts[:6], tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt) <= timedelta(days=days)

def fetch_text(url: str) -> str:
    try:
        r = httpx.get(url, headers={"User-Agent":"AI-Weekly-Newsletter/0.1"}, timeout=20, follow_redirects=True)
        if r.status_code >= 400: return ""
        return trafilatura.extract(r.text, include_comments=False, include_tables=False, favor_recall=True) or ""
    except Exception:
        return ""

def main():
    cfg = yaml.safe_load(Path("config/sources.yaml").read_text(encoding="utf-8"))
    count = 0
    with OUT.open("w", encoding="utf-8") as f:
        for src in cfg.get("sources", []):
            feed = feedparser.parse(src["url"])
            for e in feed.entries[:50]:
                ts = e.get("published_parsed") or e.get("updated_parsed")
                if not recent(ts, 7):  # widen to 14 if empty
                    continue
                url = e.get("link"); title = (e.get("title") or "").strip()
                if not url: continue
                text = fetch_text(url)
                f.write(json.dumps({
                    "title": title, "url": url, "source": src["name"],
                    "published": to_iso(ts), "text": text[:20000]
                }, ensure_ascii=False) + "\n")
                count += 1
    print(f"Wrote {OUT} with {count} items")

if __name__ == "__main__":
    main()
