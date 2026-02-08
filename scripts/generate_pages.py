import os
import json
import time
import re
import requests

BASE_URL = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1").rstrip("/")
API_KEY = os.environ["MOONSHOT_API_KEY"]

PAGES_PER_RUN = int(os.getenv("PAGES_PER_RUN", "10"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1800"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "1"))  # Moonshot constraint for some models/accounts
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "content/pages")
MANIFEST_PATH = "scripts/manifest.json"

MODEL = os.getenv("KIMI_MODEL", "kimi-k2.5")
N = 1  # keep n=1 to minimize cost

REQUIRED_KEYS = ["title:", "slug:", "description:", "date:", "hub:", "page_type:"]

def load_manifest():
    if not os.path.exists(MANIFEST_PATH):
        return {"generated_slugs": []}
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_manifest(m):
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)

def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s[:90].strip("-")

def extract_json_array(text: str):
    if not text:
        raise ValueError("Empty response from model")
    t = text.strip()
    # strip markdown fences
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)
    m = re.search(r"\[[\s\S]*\]", t)
    if not m:
        raise ValueError(f"No JSON array found. First 400 chars:\n{t[:400]}")
    return json.loads(m.group(0))

def kimi_chat(system: str, user: str) -> str:
    url = f"{BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "temperature": TEMPERATURE,
        "n": N,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    r = requests.post(url, headers=headers, json=payload, timeout=120)

    if r.status_code >= 400:
        print("Moonshot API error:", r.status_code)
        print("Response:", r.text[:2000])
        r.raise_for_status()

    data = r.json()
    return data["choices"][0]["message"]["content"]

def looks_valid(md: str) -> bool:
    if not md or len(md.strip()) < 200:
        return False
    t = md.strip()
    if not t.startswith("---"):
        return False
    for k in REQUIRED_KEYS:
        if k not in t:
            return False
    if t.count("\n## ") < 5:
        return False
    # We accept either a FAQs heading or multiple Q: entries
    if (re.search(r"^##\s+FAQs?\b", t, flags=re.IGNORECASE | re.MULTILINE) is None and
        len(re.findall(r"(^\s*[-*]\s+Q:|^\*\*Q:|^###\s+Q:)", t, flags=re.IGNORECASE | re.MULTILINE)) < 3):
        return False
    return True

SYSTEM = """You are a content generator for a static Hugo website.
NO web browsing. NO external links.
Output MUST be a single Markdown file and MUST start with YAML frontmatter delimited by '---' lines.

Forbidden words/phrases anywhere: diagnose, diagnosis, medically, legal advice, sue, guaranteed.

Frontmatter required keys:
title, slug, description, date, hub, page_type

Tone: calm, reassuring, non-advisory, globally applicable.
Avoid legal/medical/financial advice. Avoid dates, prices, and country-specific claims.
Output ONLY the markdown file. No commentary. No code fences.
"""

PROMPT_PLAN = """Return ONLY a valid JSON array of 40 strings.
No markdown, no code fences, no commentary, no bullets.

Example:
["Title 1","Title 2"]

Now generate 40 evergreen page titles for the niche:
"Is this normal? Reality checks for work, money, burnout, and modern life."
"""

PROMPT_PAGE = """Create 1 page in Markdown for the title: "{title}"

Requirements:
- Start with YAML frontmatter:
  title: ...
  slug: ...
  description: ...
  date: 2026-02-08
  hub: one of [work-career, money-stress, burnout-load, milestones, social-norms]
  page_type: one of [is-it-normal, checklist, red-flags, myth-vs-reality, explainer]
- Then content with:
  - Answer-first intro (2–4 sentences)
  - 5–8 H2 sections (practical + reassuring)
  - "Common reasons this happens" section
  - "When it might be a sign of a bigger issue" section (non-medical, non-legal)
  - A section titled exactly: "## FAQs" with 6–10 Q/A items using either:
    - "- Q: ...\n  A: ..." format, OR
    - "**Q:** ...\n**A:** ..." format
  - 4–8 internal links in markdown pointing to "/pages/<slug>/" placeholders where relevant
- Do NOT include external links.
- Do NOT include anything that requires updating later.
- If you do not include ALL required frontmatter keys and at least 5 H2s and a "## FAQs" section, your output is invalid.
- Output ONLY the markdown file. No commentary.
"""

def main():
    manifest = load_manifest()
    existing = set(manifest.get("generated_slugs", []))

    titles_raw = kimi_chat(SYSTEM, PROMPT_PLAN)
    print("Planner raw response (first 400 chars):", (titles_raw or "")[:400])
    titles = extract_json_array(titles_raw)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    generated = 0
    for t in titles:
        if generated >= PAGES_PER_RUN:
            break

        slug = slugify(t)
        if slug in existing:
            continue

        md = ""
        for attempt in range(1, 4):
            md = kimi_chat(SYSTEM, PROMPT_PAGE.format(title=t))
            if looks_valid(md):
                break
            print(f"[WARN] Page failed format attempt {attempt} for: {t}")
            time.sleep(0.8)

        if not looks_valid(md):
            print(f"[SKIP] Could not generate valid page after retries: {t}")
            continue

        page_dir = os.path.join(OUTPUT_DIR, slug)
        os.makedirs(page_dir, exist_ok=True)
        with open(os.path.join(page_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write(md.strip() + "\n")

        existing.add(slug)
        generated += 1
        time.sleep(0.8)

    manifest["generated_slugs"] = sorted(existing)
    save_manifest(manifest)
    print(f"Generated {generated} pages.")

if __name__ == "__main__":
    main()
