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
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "25"))  # caps total API calls
MAX_RETRIES_PER_TITLE = int(os.getenv("MAX_RETRIES_PER_TITLE", "2"))
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
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise json.JSONDecodeError("No JSON found", raw, 0)
    return json.loads(m.group(0))

def call_kimi(prompt):
    payload = {
        "model": MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }

    for attempt in range(3):
        r = requests.post(
            f"{BASE_URL}/chat/completions",
            headers=HEADERS,
            json=payload,
            timeout=60,
        )
        if r.status_code < 400:
            return r.json()["choices"][0]["message"]["content"]
        if r.status_code in (429, 500, 502, 503):
            time.sleep(2 ** attempt)
            continue
        raise RuntimeError(r.text)

    raise RuntimeError("API retries exhausted")

def main():
    os.makedirs(CONTENT_ROOT, exist_ok=True)
    manifest = load_manifest()
    titles = load_titles()
    random.shuffle(titles)

    produced = 0
    api_calls = 0
    retries = 0
    deletes = 0
    title_retries = {}

    manifest["generated_this_run"] = []
    used = set(manifest.get("used_titles", []))

    for title in titles:
        if produced >= PAGES_PER_RUN or api_calls >= MAX_ATTEMPTS:
            break

        slug = slugify(title)
        if slug in used:
            continue

        title_retries.setdefault(slug, 0)

        try:
            api_calls += 1
            raw = call_kimi(f"{PAGE_PROMPT}\n\nTitle: {title}")
            data = parse_json_strict_or_extract(raw)
        except Exception:
            retries += 1
            title_retries[slug] += 1
            if title_retries[slug] >= MAX_RETRIES_PER_TITLE:
                used.add(slug)
            continue

        body = (data.get("body_md") or "").strip()
        if body.count("## ") < 6:
            deletes += 1
            continue

        required = ["title", "summary", "description", "hub", "page_type"]
        if any((k not in data or not str(data[k]).strip()) for k in required):
            deletes += 1
            continue

        safe_title = str(data["title"]).replace('"', "'")
        safe_summary = str(data["summary"]).replace('"', "'")
        safe_description = str(data["description"]).replace('"', "'")

        page_dir = os.path.join(CONTENT_ROOT, slug)
        os.makedirs(page_dir, exist_ok=True)

        md = f"""---
title: "{safe_title}"
slug: "{slug}"
summary: "{safe_summary}"
description: "{safe_description}"
date: "{date.today().isoformat()}"
hub: "{data['hub']}"
page_type: "{data['page_type']}"
---

**{safe_summary}**

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
    print(f"API calls: {api_calls}")
    print(f"Pages produced: {produced}")
    print(f"Retries: {retries}")
    print(f"Deletes: {deletes}")
    print(f"Duration: {duration // 60}m {duration % 60}s")
    print("===========================\n")

if __name__ == "__main__":
    main()
