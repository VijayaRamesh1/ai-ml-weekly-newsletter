# app/summarizer/gemini_summary.py
import json, os, re, time, hashlib
from pathlib import Path
import google.generativeai as genai

# --- Config ---
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
TOP_FILE = Path(os.getenv("TOP_FILE", "data/selected.json"))  # Changed from top10.json
CANDIDATES = Path("data/candidates.jsonl")
CACHE_FILE = Path("data/summary_cache.json")
SUMMARY_TARGET_TOKENS = int(os.getenv("SUMMARY_TARGET_TOKENS", "520"))  # ~500+ tokens
MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "24000"))                # give model plenty of context
MAX_TOKENS = int(os.getenv("SUMMARY_MAX_TOKENS", "1400"))               # room for long output
PAUSE = float(os.getenv("SUMMARY_PAUSE_SECONDS", "0.7"))
RETRIES = 2  # extra expansion attempts if too short

# Configure Gemini
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel(MODEL)

# --- Helpers ---
def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

def cache_key(title: str, url: str) -> str:
    return hashlib.sha1(f"{title}|{url}".encode("utf-8")).hexdigest()

def est_tokens(text: str) -> int:
    # crude but effective: ~1 token ≈ 0.75 words
    words = len(re.findall(r"\w+", text))
    return int(words / 0.75)

def strip_code_fences(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^```(json)?\s*|\s*```$", "", s, flags=re.IGNORECASE)
    # strip potential <think>…</think> or similar reasoning wrappers
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL | re.IGNORECASE)
    return s.strip()

def coerce_json(payload: str) -> dict:
    s = strip_code_fences(payload)
    # try direct parse
    try:
        return json.loads(s)
    except Exception:
        pass
    # try to extract the largest {...} block
    m = re.search(r"\{.*\}", s, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    # last resort
    return {}

def load_full_text_if_missing(title: str, url: str, text: str) -> str:
    if text: return text
    if not CANDIDATES.exists(): return ""
    for line in CANDIDATES.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        obj = json.loads(line)
        if obj.get("title") == title and obj.get("url") == url:
            return obj.get("text", "")
    return ""

SYS_PROMPT = (
    "You are an expert AI/ML analyst writing long-form summaries for enterprise readers. "
    "Return ONLY valid JSON with keys summary_p1 and summary_p2 (no other keys, no preface). "
    "Both values must be plain text paragraphs (no bullets). "
    "Write with high factual discipline—if metrics/datasets/limits aren't stated, say 'not stated'. "
    "Avoid chain-of-thought or hidden reasoning—just the final summaries."
)

def user_prompt(title: str, url: str, text: str, min_tokens: int) -> str:
    return f"""
Title: {title}
URL: {url}

Article (truncated to provide context):
{text[:MAX_CHARS]}

Write TWO paragraphs in JSON (keys: summary_p1, summary_p2) with a COMBINED length ≥ {min_tokens} tokens.
- summary_p1 (WHAT + HOW):  cover novelty, method/architecture, data/training, evals/metrics, limitations.
- summary_p2 (WHY IT MATTERS): map to enterprise use-cases, security/GRC implications, ops/perf, cost, ROI, adoption risks.
- Use concrete details and numbers when available; do not invent facts. No citations or quotes.
Return ONLY JSON.
""".strip()

def call_gemini(title: str, url: str, text: str, min_tokens: int) -> dict:
    try:
        response = model.generate_content(
            user_prompt(title, url, text, min_tokens),
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                top_p=0.9,
                max_output_tokens=MAX_TOKENS,
            )
        )
        
        payload = response.text or ""
        data = coerce_json(payload)
        if not isinstance(data, dict):
            data = {}
        p1 = (data.get("summary_p1") or "").strip()
        p2 = (data.get("summary_p2") or "").strip()
        return {"summary_p1": p1, "summary_p2": p2}
        
    except Exception as e:
        print(f"Gemini API error: {str(e)[:100]}...")
        return {"summary_p1": "", "summary_p2": ""}

def ensure_length(data: dict, title: str, url: str, text: str, min_tokens: int) -> dict:
    comb = (data.get("summary_p1","") + " " + data.get("summary_p2","")).strip()
    if est_tokens(comb) >= min_tokens:
        return data
    # Ask the model to EXPAND, preserving JSON shape
    short_tokens = est_tokens(comb)
    expand_by = max(50, min_tokens - short_tokens + 40)
    
    try:
        expand_prompt = f"""Expand the previous summaries while keeping the same JSON keys and style.
Target combined length ≥ {min_tokens} tokens (currently ~{short_tokens}).
Add concrete method details, dataset names/sizes, metrics, latency/cost/security notes, and deployment caveats if present.
Return ONLY JSON with keys summary_p1 and summary_p2.

Context:
Title: {title}
URL: {url}
Article (truncated):
{text[:MAX_CHARS]}
"""
        
        response = model.generate_content(
            expand_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.25,
                top_p=0.9,
                max_output_tokens=MAX_TOKENS,
            )
        )
        
        data2 = coerce_json(response.text or "")
        # fallback merge if needed
        p1 = (data2.get("summary_p1") or data.get("summary_p1","")).strip()
        p2 = (data2.get("summary_p2") or data.get("summary_p2","")).strip()
        return {"summary_p1": p1, "summary_p2": p2}
        
    except Exception as e:
        print(f"Gemini expansion error: {str(e)[:100]}...")
        return data

def summarize_article(title: str, url: str, raw_text: str, cache: dict) -> dict:
    key = cache_key(title, url)
    if key in cache:
        print(f"Cache hit: {title[:60]}")
        return cache[key]

    text = load_full_text_if_missing(title, url, raw_text)
    print(f"Summarizing: {title[:60]}…")
    data = call_gemini(title, url, text, SUMMARY_TARGET_TOKENS)
    tries = 0
    while est_tokens((data.get("summary_p1","") + " " + data.get("summary_p2",""))) < SUMMARY_TARGET_TOKENS and tries < RETRIES:
        data = ensure_length(data, title, url, text, SUMMARY_TARGET_TOKENS)
        tries += 1
        time.sleep(PAUSE)

    # final guardrail
    if not data.get("summary_p1") or not data.get("summary_p2"):
        data = {
            "summary_p1": f"What's new: {title}. Details not available (source text limited).",
            "summary_p2": "Why it matters: implications for enterprise adoption, security, and business impact."
        }

    cache[key] = data
    time.sleep(PAUSE)
    return data

def main():
    if not TOP_FILE.exists():
        print("No selected.json found. Run the selector first.")
        return

    articles = json.loads(TOP_FILE.read_text(encoding="utf-8"))
    cache = load_cache()
    print(f"Processing {len(articles)} articles with Gemini {MODEL}…")

    for art in articles:
        title = art.get("title","")
        url   = art.get("url","")
        text  = art.get("text","")
        summary = summarize_article(title, url, text, cache)
        art["summary_p1"] = summary["summary_p1"]
        art["summary_p2"] = summary["summary_p2"]

    TOP_FILE.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")
    save_cache(cache)
    print(f"✅ Summarized {len(articles)} articles (target ≥ {SUMMARY_TARGET_TOKENS} tokens each)")

if __name__ == "__main__":
    main()
