# PipelineOps Weekly

PipelineOps Weekly is a focused publication for people building and operating data pipelines, AI operations workflows, and ML-based anomaly detection systems.

The newsletter combines:

- Hand-written field notes from the editor and guest contributors
- Curated engineering articles from cloud, data, observability, and platform teams
- Research papers translated into production tradeoffs
- A GitHub Pages site generated automatically from selected content

## Editorial Focus

Sections are organized around the operating reality of modern data and AI systems:

- Original Field Notes
- Data Pipeline Architecture
- AIOps & Observability
- ML Anomaly Detection
- Research to Production
- Tools & Release Watch

## How It Works

1. Add original pieces to `data/originals.json`.
2. Maintain curated links in `data/selected.json`, or regenerate them later from RSS/arXiv sources.
3. Render the issue to `site/dist/index.html` with `app/build_issue.py`.
4. Publish the generated site through GitHub Pages via `.github/workflows/publish.yml`.

The GitHub Actions workflow is currently in static render mode. Gemini-dependent collection, selection, and summarization are dormant until you re-enable them.

## Local Development

```bash
pip install -r requirements.txt

python app/collector/rss_collect.py
python app/collector/arxiv_api_collect.py
python app/editorial/select_topN_per_section.py
python app/summarizer/gemini_summary.py
python app/build_issue.py
```

For current static publishing, render from committed content without external AI calls:

```bash
python app/build_issue.py
open site/dist/index.html
```

## Writing Original Articles

Add hand-written pieces to `data/originals.json`:

```json
{
  "title": "What Makes a Data Pipeline Worth Monitoring?",
  "author": "Your Name",
  "source": "Original",
  "published": "2026-07-04",
  "section_id": "originals",
  "url": "",
  "summary_p1": "The article intro or first paragraph.",
  "summary_p2": "The operational takeaway or second paragraph."
}
```

Original items are rendered ahead of curated links in their section.

## Optional AI Generation

Gemini is not required for the current publish flow. If you later want automated selection and summarization again, copy `env.example` to `.env` locally, set `GEMINI_API_KEY`, and restore the dormant commands in `.github/workflows/publish.yml`.
