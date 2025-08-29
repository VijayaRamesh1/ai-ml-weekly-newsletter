import json, time, yaml, feedparser, trafilatura
from pathlib import Path
from datetime import datetime, timedelta, timezone

OUT = Path("data/candidates.jsonl"); OUT.parent.mkdir(parents=True, exist_ok=True)

def to_iso(ts):
    if not ts: return datetime.now(timezone.utc).isoformat()
    return datetime(*ts[:6], tzinfo=timezone.utc).isoformat()

def recent(ts, days=7):
    dt = datetime.now(timezone.utc) if not ts else datetime(*ts[:6], tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt) <= timedelta(days=days)

def fetch_text(url):
    try:
        html = trafilatura.fetch_url(url, no_ssl=True, timeout=15)
        return trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    except Exception:
        return ""

def main():
    cfg = yaml.safe_load(Path("config/sources.yaml").read_text())
    with OUT.open("w", encoding="utf-8") as f:
        for src in cfg.get("sources", []):
            feed = feedparser.parse(src["url"])
            for e in feed.entries[:50]:
                ts = e.get("published_parsed") or e.get("updated_parsed")
                if not recent(ts, 7): continue
                url = e.get("link"); title = e.get("title", "").strip()
                text = fetch_text(url)
                item = {
                    "title": title, "url": url, "source": src["name"],
                    "published": to_iso(ts), "text": text[:20000]  # cap
                }
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Wrote {OUT}")

if __name__ == "__main__":
    main()
