import os
import json
import time
import re
import random
import requests
from datetime import date

START_TIME = time.time()

BASE_URL = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1").rstrip("/")
API_KEY = os.environ["MOONSHOT_API_KEY"]
MODEL = os.getenv("KIMI_MODEL", "kimi-k2.5")

PAGES_PER_RUN = int(os.getenv("PAGES_PER_RUN", "10"))
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "25"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1600"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "1"))
SLEEP_SECONDS = float(os.getenv("SLEEP_SECONDS", "0.3"))

CONTENT_ROOT = "content/pages"
MANIFEST_PATH = "scripts/manifest.json"
TITLES_POOL_PATH = "scripts/titles_pool.txt"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

SYSTEM = """You generate calm, reassuring evergreen content.
NO medical, legal, or financial advice.
FORBIDDEN words: diagnose, diagnosis, prescribed, guaranteed, sue.
Return JSON only.
"""

PAGE_PROMPT = """Return ONLY JSON with:
title
summary (one sentence reassurance)
description
hub (work-career | money-stress | burnout-load | milestones | social-norms)
page_type (is-it-normal | checklist | red-flags | myth-vs-reality | explainer)
body_md (markdown only)

Use these H2 sections exactly:
## What this feeling usually means
## Common reasons
## What makes it worse
## What helps (non-advice)
## When it might signal a bigger issue
## FAQs
"""

def load_manifest():
    if not os.path.exists(MANIFEST_PATH):
        return {"used_titles": [], "generated_this_run": []}
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_manifest(m):
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)

def slugify(s):
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s[:80].strip("-")

def load_titles():
    with open(TITLES_POOL_PATH, "r", encoding="utf-8") as f:
        return [t.strip() for t in f if t.strip()]

def parse_json_strict_or_extract(raw: str) -> dict:
    """Parse strict JSON; if model wraps it, extract the first {...} block."""
    raw = raw.strip()

    # Fast path: strict JSON
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Remove common wrappers like ```json ... ```
    raw2 = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw2 = re.sub(r"\s*```$", "", raw2)

    try:
        return json.loads(raw2)
    except json.JSONDecodeError:
        pass

    # Extract first JSON object block
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise json.JSONDecodeError("No JSON object found in model output", raw, 0)
    return json.loads(m.group(0))

def call_kimi(prompt):
    payload = {
        "model": MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_OUTPUT_TOKENS,

        # IMPORTANT: ask the API to force JSON object output (if supported by model)
        "response_format": {"type": "json_object"},

        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }

    last_err = None
    for attempt in range(3):
        r = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=HEADERS,
            json=payload,
            timeout=60,
        )
        if r.status_code < 400:
            return r.json()["choices"][0]["message"]["content"]

        # backoff on transient errors
        if r.status_code in (429, 500, 502, 503):
            time.sleep(2 ** attempt)
            continue

        last_err = r.text
        break

    raise RuntimeError(last_err or "API retries exhausted")

def main():
    os.makedirs(CONTENT_ROOT, exist_ok=True)
    manifest = load_manifest()
    titles = load_titles()
    random.shuffle(titles)

    produced = 0
    attempts = 0
    retries = 0
    deletes = 0

    manifest["generated_this_run"] = []
    used = set(manifest.get("used_titles", []))

    for title in titles:
        if produced >= PAGES_PER_RUN or attempts >= MAX_ATTEMPTS:
            break

        attempts += 1
        slug = slugify(title)

        if slug in used:
            continue

        try:
            raw = call_kimi(f"{PAGE_PROMPT}\n\nTitle: {title}")
            data = parse_json_strict_or_extract(raw)
        except Exception as e:
            retries += 1
            # optional: uncomment to see why it failed
            # print("[RETRY]", title, "=>", str(e)[:200])
            continue

        body = (data.get("body_md") or "").strip()
        if body.count("## ") < 6:
            deletes += 1
            continue

        # Ensure required keys exist
        required = ["title", "summary", "description", "hub", "page_type"]
        if any((k not in data or not str(data[k]).strip()) for k in required):
            deletes += 1
            continue

        page_dir = os.path.join(CONTENT_ROOT, slug)
        os.makedirs(page_dir, exist_ok=True)

        md = f"""---
title: "{str(data['title']).replace('"', '\\"')}"
slug: "{slug}"
summary: "{str(data['summary']).replace('"', '\\"')}"
description: "{str(data['description']).replace('"', '\\"')}"
date: "{date.today().isoformat()}"
hub: "{data['hub']}"
page_type: "{data['page_type']}"
---

**{str(data['summary']).replace('"', '\\"')}**

{body}
"""

        with open(os.path.join(page_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write(md)

        produced += 1
        used.add(slug)
        manifest["used_titles"].append(slug)
        manifest["generated_this_run"].append(slug)
        time.sleep(SLEEP_SECONDS)

    save_manifest(manifest)

    duration = int(time.time() - START_TIME)
    print("\n===== FACTORY SUMMARY =====")
    print(f"Pages attempted: {attempts}")
    print(f"Pages produced: {produced}")
    print(f"Retries: {retries}")
    print(f"Deletes: {deletes}")
    print(f"Duration: {duration // 60}m {duration % 60}s")
    print("===========================\n")

if __name__ == "__main__":
    main()
