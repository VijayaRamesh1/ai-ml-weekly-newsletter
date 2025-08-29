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
        html = trafilatura.fetch_url(url, no_ssl=True)
        return trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return ""

def main():
    try:
        print("Loading config...")
        cfg = yaml.safe_load(Path("config/sources.yaml").read_text())
        print(f"Found {len(cfg.get('sources', []))} sources")
        
        with OUT.open("w", encoding="utf-8") as f:
            for src in cfg.get("sources", []):
                try:
                    print(f"Processing source: {src['name']} ({src['url']})")
                    feed = feedparser.parse(src["url"])
                    print(f"  Feed has {len(feed.entries)} entries")
                    
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
                except Exception as e:
                    print(f"Error processing source {src['name']}: {e}")
                    continue
                    
        print(f"Wrote {OUT}")
    except Exception as e:
        print(f"Fatal error in collector: {e}")
        raise

if __name__ == "__main__":
    main()
