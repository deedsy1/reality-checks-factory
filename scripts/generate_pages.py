import os, json, time, re
import requests

BASE_URL = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1").rstrip("/")
API_KEY = os.environ["MOONSHOT_API_KEY"]

PAGES_PER_RUN = int(os.getenv("PAGES_PER_RUN", "20"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "2200"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "content/pages")
MANIFEST_PATH = "scripts/manifest.json"

# Cost control defaults
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.3"))
N = 1

# Model id may differ per account. Set KIMI_MODEL in env if needed.
MODEL = os.getenv("KIMI_MODEL", "kimi-k2.5")

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
    r = requests.post(url, headers=headers, json=payload, timeout=180)
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]

SYSTEM = """You generate pages for a static Hugo website.
NO web browsing. NO external links.
Output MUST be a single Markdown document with YAML frontmatter at the top.
Frontmatter required: title, slug, description, date, hub, page_type.
Tone: calm, reassuring, globally applicable, non-advisory.
Avoid legal/medical/financial advice. Avoid prices, dates (except the frontmatter date), and country-specific rules.
"""

PROMPT_PLAN = """Generate 40 evergreen page titles for:
\"Is this normal? Reality checks for work, money, burnout, and modern life.\"

Requirements:
- Every title must be a natural query or statement people search, e.g. "Is it normal to ..."
- Avoid medical diagnosis, legal advice, investing advice, and anything that depends on laws.
- Spread across the five hubs:
  work-career, money-stress, burnout-load, milestones, social-norms

Return ONLY a JSON array of objects with keys:
- title
- hub (one of the hubs above)
- page_type (one of: is-it-normal, checklist, red-flags, myth-vs-reality, explainer)

No commentary. No markdown.
"""

PROMPT_PAGE = """Create 1 page in Markdown for the title: "{title}"

Frontmatter (YAML) REQUIRED:
title: "{title}"
slug: "{slug}"
description: (140-160 chars, calm, no hype)
date: 2026-02-08
hub: "{hub}"
page_type: "{page_type}"

Content requirements:
- Answer-first intro (2–4 sentences)
- 5–8 H2 sections with practical, reassuring framing
- Include an H2 called "Common reasons this happens"
- Include an H2 called "When it might be a sign of a bigger issue" (no medical/legal advice; just signals to consider support)
- Include an H2 called "Simple reality checks" with 5-9 bullet points
- Add "FAQs" section with 6–10 Q/A pairs (use format **Q:** and **A:**)
- Add 4–8 internal links to other pages using this format: /pages/<slug>/
- No external links.
- No time-sensitive claims.
"""

def main():
    manifest = load_manifest()
    existing = set(manifest.get("generated_slugs", []))

    plan_raw = kimi_chat(SYSTEM, PROMPT_PLAN)
    plan = json.loads(plan_raw)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    generated = 0
    for item in plan:
        if generated >= PAGES_PER_RUN:
            break
        title = item["title"]
        hub = item["hub"]
        page_type = item["page_type"]
        slug = slugify(title)

        if slug in existing:
            continue

        md = kimi_chat(SYSTEM, PROMPT_PAGE.format(title=title, slug=slug, hub=hub, page_type=page_type))

        # Hugo page bundle for clean URLs: content/pages/<slug>/index.md
        page_dir = os.path.join(OUTPUT_DIR, slug)
        os.makedirs(page_dir, exist_ok=True)
        with open(os.path.join(page_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write(md.strip() + "\n")

        existing.add(slug)
        generated += 1
        time.sleep(1.2)  # gentle pacing to avoid rate spikes

    manifest["generated_slugs"] = sorted(existing)
    save_manifest(manifest)
    print(f"Generated {generated} pages.")

if __name__ == "__main__":
    main()
