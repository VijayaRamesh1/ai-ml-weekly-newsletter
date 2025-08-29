import json
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

DATA_PATH = Path("data/top10.json")
TEMPLATE_DIR = "site/templates"
OUT_DIR = Path("site/dist")

def load_items():
    data = json.loads(Path(DATA_PATH).read_text(encoding="utf-8"))
    # sort just in case and ensure fields exist
    data = sorted(data, key=lambda x: x.get("rank", 9999))
    return data

def main():
    items = load_items()
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    tmpl = env.get_template("issue.html")

    html = tmpl.render(
        title="AI Weekly Newsletter",
        header="AI Weekly Newsletter — Data-Driven Issue",
        subheader="Top 10 stories ranked by Technical Innovation, Enterprise/Security Applicability, and Business Impact.",
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        items=items,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")
    print("Wrote site/dist/index.html from data/top10.json")

if __name__ == "__main__":
    main()
