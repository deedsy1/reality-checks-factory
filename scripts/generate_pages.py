import os
import json
import time
import re
import random
import shutil
import requests
from datetime import date

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

You MUST return valid JSON only.
"""

PAGE_PROMPT = """Return ONLY JSON with these keys:
title
description
hub (one of: work-career, money-stress, burnout-load, milestones, social-norms)
page_type (one of: is-it-normal, checklist, red-flags, myth-vs-reality, explainer)
body_md (markdown body ONLY, no frontmatter)

Body rules:
- Start with a short reassurance paragraph
- At least 5 H2 sections
- One section titled "FAQs" with 6–10 questions
- Neutral, global, non-advisory tone
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

def is_similar(slug, existing_slugs):
    for s in existing_slugs:
        overlap = len(set(slug.split("-")) & set(s.split("-")))
        if overlap >= 3:
            return True
    return False

def call_kimi(prompt):
    payload = {
        "model": MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_OUTPUT_TOKENS,
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

        print("API error:", r.text)
        break

    raise RuntimeError("Kimi API failed after retries")

def main():
    os.makedirs(CONTENT_ROOT, exist_ok=True)

    manifest = load_manifest()
    titles = load_titles()
    random.shuffle(titles)

    produced = 0
    attempts = 0
    manifest["generated_this_run"] = []

    existing_slugs = set(manifest.get("used_titles", []))

    for title in titles:
        if produced >= PAGES_PER_RUN or attempts >= MAX_ATTEMPTS:
            break

        attempts += 1
        slug = slugify(title)

        if slug in existing_slugs or is_similar(slug, existing_slugs):
            continue

        try:
            raw = call_kimi(f"{PAGE_PROMPT}\n\nTitle: {title}")
            data = json.loads(raw)
        except Exception as e:
            print("[SKIP] generation failed:", e)
            continue

        body = data.get("body_md", "")
        if body.count("\n## ") < 5 or "FAQ" not in body:
            print("[SKIP] structure invalid:", title)
            continue

        page_dir = os.path.join(CONTENT_ROOT, slug)
        os.makedirs(page_dir, exist_ok=True)

        md = f"""---
title: "{data['title']}"
slug: "{slug}"
description: "{data['description']}"
date: "{date.today().isoformat()}"
hub: "{data['hub']}"
page_type: "{data['page_type']}"
---

{body}
"""

        with open(os.path.join(page_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write(md)

        produced += 1
        existing_slugs.add(slug)
        manifest["used_titles"].append(slug)
        manifest["generated_this_run"].append(slug)

        print(f"[OK] {produced}/{PAGES_PER_RUN} {slug}")
        time.sleep(SLEEP_SECONDS)

    save_manifest(manifest)
    print(f"Produced {produced} pages in {attempts} attempts")

if __name__ == "__main__":
    main()
