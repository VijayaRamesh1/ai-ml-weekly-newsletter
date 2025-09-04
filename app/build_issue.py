import os, json
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import yaml

DATA_PATH = Path(os.getenv("DATA_FILE", "data/selected.json"))  # Changed from top10.json
TEMPLATE_DIR = "site/templates"
OUT_DIR = Path("site/dist")
SECS = yaml.safe_load(Path("config/sections.yaml").read_text(encoding="utf-8"))

def main():
    data_items = json.loads(DATA_PATH.read_text(encoding="utf-8"))

    order = SECS["order"]
    meta  = {s["id"]: s for s in SECS["sections"]}

    # group items by section (keeps your section order)
    groups = []
    for sid in order:
        sec_items = [it for it in data_items if it.get("section_id")==sid]
        if not sec_items:
            continue
        # ensure stable rank inside section
        sec_items.sort(key=lambda x: x.get("rank", 999))
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
        title="The AI/ML Brief — Executive Intelligence",
        header="The AI/ML Brief",
        subheader="A weekly executive brief on AI — strategy, launches, security, applied engineering, infra, and research.",
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        groups=groups,              # <— pass grouped data
        sections_nav=sections_nav   # <— only sections that have items
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    print("Wrote site/dist/index.html")

if __name__ == "__main__":
    main()
