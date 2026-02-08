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

# Cap total API calls per run (prevents "3 pages took 12 minutes" disasters)
MAX_API_CALLS = int(os.getenv("MAX_ATTEMPTS", "25"))

# Cap retries per title (prevents one stubborn title burning the whole run)
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

def ensure_manifest_schema(m: dict) -> dict:
    """Self-heal manifest structure so old/partial manifests never break runs."""
    if not isinstance(m, dict):
        m = {}
    if "used_titles" not in m or not isinstance(m.get("used_titles"), list):
        m["used_titles"] = []
    if "generated_this_run" not in m or not isinstance(m.get("generated_this_run"), list):
        m["generated_this_run"] = []
    if "failed_titles" not in m or not isinstance(m.get("failed_titles"), list):
        m["failed_titles"] = []
    return m

def load_manifest():
    if not os.path.exists(MANIFEST_PATH):
        return ensure_manifest_schema({})
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return ensure_manifest_schema(json.load(f))
    except Exception:
        # If the file is corrupted, recover gracefully
        return ensure_manifest_schema({})

def save_manifest(m):
    # Atomic write prevents half-written JSON in CI
    tmp_path = MANIFEST_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2)
    os.replace(tmp_path, MANIFEST_PATH)

def slugify(s):
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s[:80].strip("-")

def load_titles():
    with open(TITLES_POOL_PATH, "r", encoding="utf-8") as f:
        return [t.strip() for t in f if t.strip()]

def parse_json_strict_or_extract(raw: str) -> dict:
    raw = (raw or "").strip()

    # Strict JSON first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strip common code fences
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

def call_kimi(prompt: str) -> str:
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

        if r.status_code in (429, 500, 502, 503):
            time.sleep(2 ** attempt)
            continue

        last_err = r.text
        break

    raise RuntimeError(last_err or "API retries exhausted")

def main():
    os.makedirs(CONTENT_ROOT, exist_ok=True)

    manifest = load_manifest()
    manifest["generated_this_run"] = []  # reset each run

    titles = load_titles()
    random.shuffle(titles)

    produced = 0
    api_calls = 0
    retries = 0
    deletes = 0

    used = set(manifest.get("used_titles", []))
    per_title_retries = {}

    for title in titles:
        if produced >= PAGES_PER_RUN or api_calls >= MAX_API_CALLS:
            break

        slug = slugify(title)
        if slug in used:
            continue

        per_title_retries.setdefault(slug, 0)

        # Call model
        try:
            api_calls += 1
            raw = call_kimi(f"{PAGE_PROMPT}\n\nTitle: {title}")
            data = parse_json_strict_or_extract(raw)
        except Exception:
            retries += 1
            per_title_retries[slug] += 1
            if per_title_retries[slug] >= MAX_RETRIES_PER_TITLE:
                # blacklist this title for future runs
                used.add(slug)
                manifest["used_titles"].append(slug)
                manifest["failed_titles"].append(slug)
            continue

        # Validate output
        body = (data.get("body_md") or "").strip()
        if body.count("## ") < 6:
            deletes += 1
            per_title_retries[slug] += 1
            if per_title_retries[slug] >= MAX_RETRIES_PER_TITLE:
                used.add(slug)
                manifest["used_titles"].append(slug)
                manifest["failed_titles"].append(slug)
            continue

        required = ["title", "summary", "description", "hub", "page_type"]
        if any((k not in data or not str(data[k]).strip()) for k in required):
            deletes += 1
            per_title_retries[slug] += 1
            if per_title_retries[slug] >= MAX_RETRIES_PER_TITLE:
                used.add(slug)
                manifest["used_titles"].append(slug)
                manifest["failed_titles"].append(slug)
            continue

        # Safe strings for YAML
        safe_title = str(data["title"]).replace('"', "'").strip()
        safe_summary = str(data["summary"]).replace('"', "'").strip()
        safe_description = str(data["description"]).replace('"', "'").strip()

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
    print(f"API calls: {api_calls} (cap {MAX_API_CALLS})")
    print(f"Pages produced: {produced} (target {PAGES_PER_RUN})")
    print(f"Retries: {retries}")
    print(f"Deletes: {deletes}")
    print(f"Duration: {duration // 60}m {duration % 60}s")
    print("===========================\n")

if __name__ == "__main__":
    main()
