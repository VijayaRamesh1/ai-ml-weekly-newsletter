import json
import os
import time
from pathlib import Path
from groq import Groq

# Configuration
MODEL = os.getenv("GROQ_MODEL", "deepseek-r1-distill-llama-70b")
CACHE_FILE = Path("data/summary_cache.json")
TOP10_FILE = Path("data/top10.json")

# Initialize Groq client
client = Groq(api_key=os.environ["GROQ_API_KEY"])

def load_cache():
    """Load existing summary cache."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except:
            return {}
    return {}

def save_cache(cache):
    """Save summary cache to disk."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

def get_article_key(title, url):
    """Generate cache key for article."""
    return f"{title[:50]}_{hash(url) % 10000}"

def summarize_article(title, url, text, cache):
    """Generate AI summary for article."""
    cache_key = get_article_key(title, url)
    
    # Check cache first
    if cache_key in cache:
        print(f"Cache hit for: {title[:60]}...")
        return cache[cache_key]
    
    print(f"Generating summary for: {title[:60]}...")
    
    try:
        # Non-streaming call (better for CI logs + simple JSON parsing)
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system", 
                    "content": "You summarize AI/ML articles for enterprise readers. Return ONLY JSON with keys summary_p1 and summary_p2. No reasoning, no bullets. summary_p1 should be 1-2 sentences about what the article covers. summary_p2 should be 1 sentence about why it matters for business/enterprise."
                },
                {
                    "role": "user", 
                    "content": f"Title: {title}\nURL: {url}\nArticle (truncated):\n{text[:12000]}\n\nReturn JSON now."
                }
            ],
            temperature=0.2,
            max_tokens=300,
        )
        
        payload = resp.choices[0].message.content.strip()
        
        # Try to parse JSON response
        try:
            summary_data = json.loads(payload)
            summary_p1 = summary_data.get("summary_p1", "")
            summary_p2 = summary_data.get("summary_p2", "")
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            print(f"JSON parse failed, using fallback for: {title[:40]}...")
            summary_p1 = f"What's new: {title}"
            summary_p2 = "Why it matters: enterprise/security & business relevance at-a-glance."
        
        # Cache the result
        cache[cache_key] = {
            "summary_p1": summary_p1,
            "summary_p2": summary_p2
        }
        
        # Small delay to avoid rate limits
        time.sleep(0.5)
        
        return cache[cache_key]
        
    except Exception as e:
        print(f"Error summarizing {title[:40]}: {str(e)[:100]}...")
        # Fallback summary
        fallback = {
            "summary_p1": f"What's new: {title}",
            "summary_p2": "Why it matters: enterprise/security & business relevance at-a-glance."
        }
        cache[cache_key] = fallback
        return fallback

def main():
    """Main function to summarize top 10 articles."""
    if not TOP10_FILE.exists():
        print("No top10.json found. Run semantic_rank.py first.")
        return
    
    # Load articles and cache
    articles = json.loads(TOP10_FILE.read_text(encoding="utf-8"))
    cache = load_cache()
    
    print(f"Processing {len(articles)} articles with Groq summarization...")
    
    # Summarize each article
    for article in articles:
        title = article.get("title", "")
        url = article.get("url", "")
        text = article.get("text", "")
        
        if not text:
            # If no text, try to get from candidates
            candidates_file = Path("data/candidates.jsonl")
            if candidates_file.exists():
                for line in candidates_file.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        candidate = json.loads(line)
                        if candidate.get("title") == title and candidate.get("url") == url:
                            text = candidate.get("text", "")
                            break
        
        summary = summarize_article(title, url, text, cache)
        
        # Update article with AI summaries
        article["summary_p1"] = summary["summary_p1"]
        article["summary_p2"] = summary["summary_p2"]
    
    # Save updated articles
    TOP10_FILE.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # Save cache
    save_cache(cache)
    
    print(f"✅ Summarized {len(articles)} articles using Groq {MODEL}")
    print(f"Cache saved with {len(cache)} entries")

if __name__ == "__main__":
    main()
