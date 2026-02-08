import os, json, time, re
import requests

BASE_URL = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1").rstrip("/")
API_KEY = os.environ["MOONSHOT_API_KEY"]

PAGES_PER_RUN = int(os.getenv("PAGES_PER_RUN", "15"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1800"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "content/pages")
MANIFEST_PATH = "scripts/manifest.json"

TEMPERATURE = float(os.getenv("TEMPERATURE", "0.3"))
N = int(os.getenv("N", "1"))

# Real model id for K2.5:
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
    r = requests.post(url, headers=headers, json=payload, timeout=120)
    if r.status_code >= 400:
        print("Moonshot API error:", r.status_code)
        print("Response:", r.text[:2000])
        r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]

SYSTEM = """You are a content generator for a static Hugo website.
NO web browsing. NO external links.
Output MUST be a single Markdown file with Hugo YAML frontmatter at top.
Frontmatter required: title, slug, description, date, hub, page_type.
Tone: calm, reassuring, non-advisory, globally applicable.
Avoid legal/medical/financial advice. Avoid dates, prices, and country-specific claims.
"""

PROMPT_PLAN = """Generate a list of 30 evergreen page titles for the niche:
"Is this normal? Reality checks for work, money, burnout, and modern life."
Return ONLY a JSON array of strings. No commentary.
"""

PROMPT_PAGE = """Create 1 page in Markdown for the title: "{title}"

Requirements:
- Start with YAML frontmatter exactly:
  ---
  title: ...
  slug: ...
  description: ...
  date: 2026-02-09
  hub: one of [work-career, money-stress, burnout-load, milestones, social-norms]
  page_type: one of [is-it-normal, checklist, red-flags, myth-vs-reality, explainer]
  ---
- Then content with:
  - Answer-first intro (2–4 sentences)
  - 5–8 H2 sections
  - A section "Common reasons this happens"
  - A section "When it might be a sign of a bigger issue" (non-medical, non-legal)
  - 6–10 FAQs (format each FAQ as **Q:** / **A:**)
  - 3–6 internal links pointing to "/pages/<slug>/" placeholders where relevant
- Do NOT include external links.
- Do NOT include anything that requires updating later.
"""

def main():
    manifest = load_manifest()
    existing = set(manifest.get("generated_slugs", []))

    titles_json = kimi_chat(SYSTEM, PROMPT_PLAN)
    titles = json.loads(titles_json)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    generated = 0
    for t in titles:
        if generated >= PAGES_PER_RUN:
            break
        slug = slugify(t)
        if slug in existing:
            continue

        md = kimi_chat(SYSTEM, PROMPT_PAGE.format(title=t)).strip()
        page_dir = os.path.join(OUTPUT_DIR, slug)
        os.makedirs(page_dir, exist_ok=True)
        with open(os.path.join(page_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write(md + "\n")

        existing.add(slug)
        generated += 1
        time.sleep(1.2)

    manifest["generated_slugs"] = sorted(existing)
    save_manifest(manifest)
    print(f"Generated {generated} pages using model: {MODEL}")

if __name__ == "__main__":
    main()
