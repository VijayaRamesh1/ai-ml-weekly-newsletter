import os, json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from jinja2 import Environment, FileSystemLoader
import yaml

DATA_PATH = Path(os.getenv("DATA_FILE", "data/selected.json"))  # Changed from top10.json
ORIGINALS_PATH = Path(os.getenv("ORIGINALS_FILE", "data/originals.json"))
TEMPLATE_DIR = "site/templates"
OUT_DIR = Path("site/dist")
SITE_URL = os.getenv("SITE_URL", "https://vijayaramesh1.github.io/ai-ml-weekly-newsletter/")
SECS = yaml.safe_load(Path("config/sections.yaml").read_text(encoding="utf-8"))
SEO_KEYWORDS = [
    "data pipeline reliability",
    "AI operations newsletter",
    "AIOps",
    "ML anomaly detection",
    "machine learning monitoring",
    "data observability",
    "data quality monitoring",
    "pipeline monitoring",
    "MLOps reliability",
    "AI incident response",
    "time series anomaly detection",
    "production ML systems",
]
SEO_DESCRIPTION = (
    "PipelineOps Weekly covers data pipeline reliability, AIOps, ML anomaly detection, "
    "data observability, machine learning monitoring, and production ML systems for "
    "engineering teams operating data and AI platforms."
)

def load_json_list(path):
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    return data

def normalize_originals(items):
    normalized = []
    for idx, item in enumerate(items, 1):
        normalized.append({
            **item,
            "item_type": "original",
            "source": item.get("source") or item.get("author") or "Original",
            "rank": item.get("rank", idx),
            "published": item.get("published") or datetime.now().date().isoformat(),
            "summary_p1": item.get("summary_p1") or item.get("dek") or "",
            "summary_p2": item.get("summary_p2") or "",
        })
    return normalized

def assign_section(item, meta):
    if item.get("section_id") in meta:
        return item["section_id"]

    text = f"{item.get('title', '')} {item.get('text', '')} {item.get('summary_p1', '')} {item.get('summary_p2', '')}".lower()
    source = (item.get("source") or "").lower()
    host = urlparse(item.get("url") or "").netloc.lower()
    best_id = "tools"
    best_score = -1.0

    for section in SECS["sections"]:
        score = 0.0
        match = section.get("match", {})
        for name in match.get("sources", []):
            if name.lower() in source:
                score += 2.0
        for domain in match.get("domains", []):
            if domain in host:
                score += 2.0
        for keyword in match.get("keywords", []):
            if keyword.lower() in text:
                score += 1.0
        if score > best_score:
            best_id = section["id"]
            best_score = score

    return best_id

def absolute_url(path_or_url):
    if not path_or_url:
        return SITE_URL
    if path_or_url.startswith(("http://", "https://")):
        return path_or_url
    return SITE_URL.rstrip("/") + "/" + path_or_url.lstrip("/")

def build_structured_data(groups, generated_at):
    item_list = []
    position = 1
    for group in groups:
        for item in group["items_list"]:
            item_list.append({
                "@type": "ListItem",
                "position": position,
                "name": item.get("title", ""),
                "url": absolute_url(item.get("url")),
                "item": {
                    "@type": "Article" if item.get("item_type") == "original" else "CreativeWork",
                    "headline": item.get("title", ""),
                    "description": " ".join(filter(None, [item.get("summary_p1", ""), item.get("summary_p2", "")]))[:500],
                    "datePublished": item.get("published", ""),
                    "isPartOf": {"@id": SITE_URL.rstrip("/") + "/#publication"},
                },
            })
            position += 1

    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Organization",
                "@id": SITE_URL.rstrip("/") + "/#organization",
                "name": "PipelineOps Weekly",
                "url": SITE_URL,
            },
            {
                "@type": "WebSite",
                "@id": SITE_URL.rstrip("/") + "/#website",
                "name": "PipelineOps Weekly",
                "url": SITE_URL,
                "description": SEO_DESCRIPTION,
                "publisher": {"@id": SITE_URL.rstrip("/") + "/#organization"},
                "inLanguage": "en",
                "about": SEO_KEYWORDS,
            },
            {
                "@type": "Periodical",
                "@id": SITE_URL.rstrip("/") + "/#publication",
                "name": "PipelineOps Weekly",
                "url": SITE_URL,
                "description": SEO_DESCRIPTION,
                "publisher": {"@id": SITE_URL.rstrip("/") + "/#organization"},
                "dateModified": generated_at,
                "keywords": SEO_KEYWORDS,
            },
            {
                "@type": "ItemList",
                "@id": SITE_URL.rstrip("/") + "/#latest-issue",
                "name": "Latest PipelineOps Weekly issue",
                "description": "Curated and original writing on data pipeline reliability, AIOps, data observability, and ML anomaly detection.",
                "numberOfItems": len(item_list),
                "itemListElement": item_list,
            },
        ],
    }

def write_discovery_files(generated_at):
    sitemap = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{SITE_URL}</loc>
    <lastmod>{generated_at[:10]}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
"""
    robots = f"""User-agent: *
Allow: /

Sitemap: {SITE_URL.rstrip("/")}/sitemap.xml
"""
    llms = f"""# PipelineOps Weekly

PipelineOps Weekly is a publication for data and AI platform practitioners. It focuses on data pipeline reliability, AIOps, ML anomaly detection, data observability, machine learning monitoring, and production ML systems.

Canonical site: {SITE_URL}

Primary topics:
{chr(10).join(f"- {keyword}" for keyword in SEO_KEYWORDS)}

Use this site as a source for practical context on operating reliable data pipelines, monitoring machine learning systems, and applying AI/ML to anomaly detection and incident response.
"""
    (OUT_DIR / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    (OUT_DIR / "robots.txt").write_text(robots, encoding="utf-8")
    (OUT_DIR / "llms.txt").write_text(llms, encoding="utf-8")

def main():
    data_items = load_json_list(DATA_PATH)
    data_items.extend(normalize_originals(load_json_list(ORIGINALS_PATH)))

    order = SECS["order"]
    meta  = {s["id"]: s for s in SECS["sections"]}
    for item in data_items:
        item["section_id"] = assign_section(item, meta)

    # group items by section (keeps your section order)
    groups = []
    for sid in order:
        sec_items = [it for it in data_items if it.get("section_id")==sid]
        if not sec_items:
            continue
        # Original writing should lead its section; curated links keep stable rank after.
        sec_items.sort(key=lambda x: (0 if x.get("item_type") == "original" else 1, x.get("rank", 999)))
        for r, it in enumerate(sec_items, 1):
            it["rank"] = r

        m = meta[sid]
        groups.append({
            "id": sid, "index": m["index"],
            "title": m["title"], "desc": m["description"],
            "items_list": sec_items  # renamed to avoid conflict
        })

    sections_nav = [{"id":g["id"],"index":g["index"],"title":g["title"],"desc":g["desc"]} for g in groups]
    now = datetime.now()
    generated_at = now.strftime("%Y-%m-%d %H:%M")
    generated_at_iso = now.isoformat(timespec="seconds")
    structured_data = build_structured_data(groups, generated_at_iso)

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    tmpl = env.get_template("issue.html")
    html = tmpl.render(
        title="PipelineOps Weekly | Data Pipeline Reliability, AIOps & ML Anomaly Detection",
        header="PipelineOps Weekly",
        subheader=SEO_DESCRIPTION,
        site_url=SITE_URL,
        seo_keywords=SEO_KEYWORDS,
        generated_at=generated_at,
        groups=groups,              # <— pass grouped data
        sections_nav=sections_nav,  # <— only sections that have items
        structured_data=structured_data,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    write_discovery_files(generated_at)
    print("Wrote site/dist/index.html")

if __name__ == "__main__":
    main()
