# AI/ML Weekly Newsletter

An automated newsletter that collects AI/ML news from RSS feeds, scores them using custom criteria, and publishes a weekly top 10.

## Features
- **Live RSS Collection**: Pulls articles from configurable sources
- **Intelligent Scoring**: Ranks by technical innovation, applicability, and business impact
- **Semantic Ranking**: Uses FastEmbed ONNX model for meaning-based scoring
- **MMR Diversity**: Maximal Marginal Relevance for better coverage
- **Automated Pipeline**: GitHub Actions build and deploy weekly
- **GitHub Pages**: Live newsletter accessible via web

## How it works
1. **Collector** pulls articles from RSS feeds in `config/sources.yaml`
2. **Semantic Ranker** evaluates articles using embeddings + keywords + MMR diversity
3. **Builder** generates HTML newsletter from top 10 articles
4. **GitHub Actions** automatically deploys to GitHub Pages

## Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Test the pipeline
python app/collector/rss_collect.py
python app/scorer/semantic_rank.py
python app/build_issue.py

# Open the newsletter
open site/dist/index.html
```

## Status
- ✅ Templates restored and working locally
- ✅ Robust Pages workflow deployed
- ✅ Semantic ranking with FastEmbed implemented
- 🔄 Triggering new build with semantic scoring
- 🌐 Live site will update once build completes
