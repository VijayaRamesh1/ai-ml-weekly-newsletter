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
    items = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    order_index = {sid:i for i,sid in enumerate(SECS["order"])}
    items.sort(key=lambda x: (order_index.get(x["section_id"], 999), x.get("rank", 999)))

    # Build the nav (A–G) only for sections present
    present = {i["section_id"] for i in items}
    sections_nav = [s for s in SECS["sections"] if s["id"] in present]

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    tmpl = env.get_template("issue.html")
    html = tmpl.render(
        title="AI/ML Weekly Newsletter",
        header="AI/ML Weekly — Section Picks",
        subheader="Top picks for leaders: Executive, Strategy, Launches, Security, Applied, Infra, Research.",
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        items=items,
        sections_nav=[{"id":s["id"],"index":s["index"],"title":s["title"],"desc":s["description"]} for s in sections_nav],
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    print("Wrote site/dist/index.html")

if __name__ == "__main__":
    main()
