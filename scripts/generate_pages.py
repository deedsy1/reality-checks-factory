import os, json, time, re
import requests

BASE_URL = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1").rstrip("/")
API_KEY = os.environ.get("MOONSHOT_API_KEY", "")

PAGES_PER_RUN = int(os.getenv("PAGES_PER_RUN", "15"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "content/pages")
MANIFEST_PATH = os.getenv("MANIFEST_PATH", "scripts/manifest.json")

# Model + cost controls
MODEL = os.getenv("KIMI_MODEL", "kimi-k2.5")
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1800"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "1"))  # Moonshot constraint: some models only allow temperature=1
N = int(os.getenv("N", "1"))

SLEEP_SECONDS = float(os.getenv("SLEEP_SECONDS", "0.6"))  # faster, still polite

BANNED_RE = [
    r"\bdiagnos(e|is)\b",
    r"\bmedical advice\b",
    r"\blegal advice\b",
    r"\bguarantee(d)?\b",
    r"\byou should\b",
    r"\bsue\b",
    r"\bprescribe\b",
]

REQUIRED_FRONTMATTER_KEYS = ["title:", "slug:", "description:", "date:", "hub:", "page_type:"]

HUBS = ["work-career", "money-stress", "burnout-load", "milestones", "social-norms"]
PAGE_TYPES = ["is-it-normal", "checklist", "red-flags", "myth-vs-reality", "explainer"]

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
    """
    Extract the first JSON array from a string, handling chatter and ```json fences.
    """
    if not text or not text.strip():
        raise ValueError("Empty response from model")

    t = text.strip()
    # Strip markdown fences
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)

    m = re.search(r"\[[\s\S]*\]", t)
    if not m:
        raise ValueError(f"No JSON array found. First 400 chars:\n{t[:400]}")
    return json.loads(m.group(0))

def kimi_chat(system: str, user: str, max_tokens: int | None = None) -> str:
    url = f"{BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "temperature": TEMPERATURE,
        "n": N,
        "max_tokens": int(max_tokens or MAX_OUTPUT_TOKENS),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    r = requests.post(url, headers=headers, json=payload, timeout=180)

    if r.status_code >= 400:
        print("Moonshot API error:", r.status_code)
        print("Response:", r.text[:2000])
        r.raise_for_status()

    data = r.json()
    return data["choices"][0]["message"]["content"]

def looks_valid(md: str) -> bool:
    if not md or len(md.strip()) < 600:
        return False
    t = md.strip()

    # Must start with YAML frontmatter
    if not t.startswith("---"):
        return False
    if t.count("---") < 2:
        return False

    for k in REQUIRED_FRONTMATTER_KEYS:
        if k not in t:
            return False

    # No banned phrases
    for b in BANNED_RE:
        if re.search(b, t, flags=re.IGNORECASE):
            return False

    # Structural requirements
    if len(re.findall(r"^##\s+", t, flags=re.MULTILINE)) < 5:
        return False

    # FAQ: allow several styles
    has_faq_header = re.search(r"^##\s+FAQs?\b", t, flags=re.IGNORECASE | re.MULTILINE) is not None
    q_count = len(re.findall(r"^\s*(?:[-*]\s+)?(?:\*\*)?Q:", t, flags=re.IGNORECASE | re.MULTILINE))
    if not (has_faq_header and (q_count >= 6 or q_count == 0)):  # allow bullet FAQs w/out explicit Q: markers
        # If FAQ header exists but no Q markers, accept (some templates use bullets).
        return False if not has_faq_header else True

    return True

SYSTEM = """You are a content generator for a static Hugo website.

STRICT RULES:
- NO web browsing. NO external links. NO citations.
- Output MUST be a SINGLE Markdown file and NOTHING else.
- It MUST start with YAML frontmatter delimited by '---' lines.
- Forbidden words anywhere: diagnose, diagnosis, medical advice, legal advice, sue, guaranteed, prescribe, "you should".

FORMAT RULES:
- Use simple headings.
- Include a clear "FAQs" section.
- Must include at least 5 H2 sections.

SAFETY:
- Provide general reassurance and perspective, not instructions.
- No legal, medical, or financial advice.
- No country-specific laws. No dates, prices, or time-sensitive claims.

When asked for JSON, output ONLY valid JSON (no code fences, no commentary).
"""

PROMPT_PLAN = """Return ONLY a valid JSON array of 40 page titles (strings).
No markdown, no code fences, no commentary.

Niche: "Is this normal? Reality checks for work, money, burnout, and modern life."
Focus on evergreen, globally applicable questions people search.
"""

PROMPT_PAGE = """Create 1 Markdown page for the title: "{title}"

ABSOLUTE REQUIREMENTS:
- Output ONLY the Markdown file.
- Start with YAML frontmatter:

---
title: "..."
slug: "..."
description: "..."
date: 2026-02-09
hub: one of [{hubs}]
page_type: one of [{page_types}]
---

CONTENT REQUIREMENTS:
- Answer-first intro (2–4 sentences)
- 6–8 H2 sections (##)
- Include these exact sections somewhere as H2s:
  - ## Common reasons this happens
  - ## When it might be a sign of a bigger issue
  - ## FAQs
- In the "bigger issue" section, stay non-medical/non-legal (no diagnosis, no treatment, no directives).
- FAQs: 6–10 Q/A items. Use either "Q:"/"A:" lines or bullet questions + short answers.
- Add 4–8 internal links in markdown to "/pages/<slug>/" placeholders where relevant.
- Do NOT use forbidden words.
"""

REPAIR_TITLES = """You produced output that was not a valid JSON array.
Rewrite it as ONLY a valid JSON array of strings. No commentary, no code fences.
Here is your previous output:
{bad}
"""

REPAIR_PAGE = """You produced a page that does not meet the strict format.
Rewrite it so it fully complies. Output ONLY the corrected Markdown file.

Checklist:
- Starts with YAML frontmatter delimited by --- lines
- Frontmatter includes: title, slug, description, date, hub, page_type
- At least 6 H2 sections
- Includes H2 sections: "Common reasons this happens", "When it might be a sign of a bigger issue", "FAQs"
- FAQs section has 6–10 Q/A items
- No forbidden words (diagnose/diagnosis/etc)
- No external links

Here is your previous output:
{bad}
"""

def get_titles():
    raw = kimi_chat(SYSTEM, PROMPT_PLAN, max_tokens=800)
    print("Planner raw response (first 300 chars):", raw[:300].replace("\n", "\\n"))
    try:
        return extract_json_array(raw)
    except Exception as e:
        # Repair once (cheaper than repeated blind retries)
        repaired = kimi_chat(SYSTEM, REPAIR_TITLES.format(bad=raw), max_tokens=800)
        return extract_json_array(repaired)

def main():
    if not API_KEY:
        raise RuntimeError("MOONSHOT_API_KEY is missing. Set it in GitHub Actions Secrets.")

    manifest = load_manifest()
    existing = set(manifest.get("generated_slugs", []))

    titles = get_titles()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    generated = 0
    for t in titles:
        if generated >= PAGES_PER_RUN:
            break

        slug = slugify(t)
        if slug in existing:
            continue

        prompt = PROMPT_PAGE.format(
            title=t,
            hubs=", ".join(HUBS),
            page_types=", ".join(PAGE_TYPES),
        )

        # First attempt
        md = kimi_chat(SYSTEM, prompt)

        # Repair once if invalid (saves wasted full regenerations)
        if not looks_valid(md):
            md = kimi_chat(SYSTEM, REPAIR_PAGE.format(bad=md), max_tokens=MAX_OUTPUT_TOKENS)

        # Final fallback: one more fresh generation
        if not looks_valid(md):
            md = kimi_chat(SYSTEM, prompt)

        if not looks_valid(md):
            print(f"[SKIP] Could not generate valid page after repair+retry: {t}")
            continue

        page_dir = os.path.join(OUTPUT_DIR, slug)
        os.makedirs(page_dir, exist_ok=True)
        with open(os.path.join(page_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write(md.strip() + "\n")

        existing.add(slug)
        generated += 1
        time.sleep(SLEEP_SECONDS)

    manifest["generated_slugs"] = sorted(existing)
    save_manifest(manifest)
    print(f"Generated {generated} pages.")

if __name__ == "__main__":
    main()
