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
SECS = yaml.safe_load(Path("config/sections.yaml").read_text(encoding="utf-8"))

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

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    tmpl = env.get_template("issue.html")
    html = tmpl.render(
        title="PipelineOps Weekly — Data Reliability, AIOps, and ML Anomaly Detection",
        header="PipelineOps Weekly",
        subheader="Hand-written analysis and curated research for teams building reliable data pipelines, AI operations workflows, and ML-based anomaly detection systems.",
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        groups=groups,              # <— pass grouped data
        sections_nav=sections_nav   # <— only sections that have items
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    print("Wrote site/dist/index.html")

if __name__ == "__main__":
    main()
