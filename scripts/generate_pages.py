import os, json, time, re
from typing import Any, Dict, List
import datetime
import requests

BASE_URL = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1").rstrip("/")
API_KEY = os.environ["MOONSHOT_API_KEY"]

PAGES_PER_RUN = int(os.getenv("PAGES_PER_RUN", "10"))
TITLES_PER_RUN = int(os.getenv("TITLES_PER_RUN", "50"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1600"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "1"))  # Moonshot constraint on your account/model
SLEEP_SECONDS = float(os.getenv("SLEEP_SECONDS", "0.3"))

OUTPUT_DIR = os.getenv("OUTPUT_DIR", "content/pages")
MANIFEST_PATH = "scripts/manifest.json"

MODEL = os.getenv("KIMI_MODEL", "kimi-k2.5")

# Strictly controlled: no web, no external links, no advice language.
SYSTEM = """You are a content generator for a static Hugo website.
NO web browsing. NO external links. NO code fences. NO markdown commentary.
You must follow instructions exactly.

Forbidden words anywhere: diagnose, diagnosis, medically, legal advice, sue, guaranteed.

You will output ONLY valid JSON (no surrounding text).
"""

PROMPT_TITLES = """Return ONLY a valid JSON array of {n} evergreen page titles as strings.
No markdown, no commentary.

Niche: "Is this normal? Reality checks for work, money, burnout, and modern life."
Constraints:
- globally applicable
- reassurance & perspective (not advice)
- not medical/legal/financial advice
- no dates, no prices, no country-specific laws
""".strip()

PROMPT_PAGE_JSON = """Return ONLY valid JSON with keys:
title (string),
description (string, <= 160 chars),
hub (one of: work-career, money-stress, burnout-load, milestones, social-norms),
page_type (one of: is-it-normal, checklist, red-flags, myth-vs-reality, explainer),
body_md (string: Markdown only, no frontmatter, no H1, start directly with a short intro paragraph).

Write for the title: "{title}"

Body requirements:
- Intro: 2–4 sentences, answer-first, calm and reassuring.
- Exactly 6–8 H2 sections (use '## ' headings).
- Must include a section titled "Common reasons this happens".
- Must include a section titled "When it might be a sign of a bigger issue" (non-medical, non-legal, non-advisory).
- Must include a section titled "FAQs" with 6–10 bullet questions and answers.
  Format each FAQ as:
  - **Q:** ...
    **A:** ...
- Add 4–8 INTERNAL links in Markdown using placeholder slugs like:
  [Related topic](/pages/some-slug/)
- Do NOT include external links.
- Do NOT include medical/legal/financial advice. Avoid diagnosis language.
""".strip()

REQUIRED_H2_MIN = 6
REQUIRED_FAQ_MIN = 6

def load_manifest() -> Dict[str, Any]:
    if not os.path.exists(MANIFEST_PATH):
        return {"generated_slugs": []}
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_manifest(m: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)

def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s[:90].strip("-")

def extract_first_json(text: str) -> Any:
    if not text:
        raise ValueError("Empty response from model")
    t = text.strip()
    # If model violates and wraps in fences, strip fences:
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)

    # Try direct parse
    try:
        return json.loads(t)
    except Exception:
        pass

    # Find first array or object
    m = re.search(r"(\[[\s\S]*\]|\{[\s\S]*\})", t)
    if not m:
        raise ValueError(f"No JSON found. First 400 chars:\n{t[:400]}")
    return json.loads(m.group(1))

def request_with_retry(url: str, headers: Dict[str, str], payload: Dict[str, Any], tries: int = 3) -> Dict[str, Any]:
    last_err = None
    for attempt in range(1, tries + 1):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=60)
            if r.status_code >= 400:
                # Print body for debugging; keep short
                print(f"Moonshot API error: {r.status_code}")
                print("Response:", r.text[:2000])
                r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            # backoff
            time.sleep(min(2.5 * attempt, 6.0))
    raise last_err

def kimi_chat(system: str, user: str) -> str:
    url = f"{BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": MODEL,
        "temperature": TEMPERATURE,
        "n": 1,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    data = request_with_retry(url, headers, payload, tries=3)
    return data["choices"][0]["message"]["content"]

def looks_good_payload(d: Dict[str, Any]) -> List[str]:
    problems = []
    for k in ["title", "description", "hub", "page_type", "body_md"]:
        if k not in d or not isinstance(d[k], str) or not d[k].strip():
            problems.append(f"missing/invalid {k}")
    if "body_md" in d and isinstance(d.get("body_md"), str):
        body = d["body_md"]
        h2 = len(re.findall(r"^##\s+", body, flags=re.MULTILINE))
        if h2 < REQUIRED_H2_MIN:
            problems.append(f"too few H2s ({h2})")
        # FAQ count: count **Q:** occurrences
        faq_q = len(re.findall(r"\*\*Q:\*\*", body))
        if faq_q < REQUIRED_FAQ_MIN:
            problems.append(f"too few FAQs ({faq_q})")
        # Banned words
        if re.search(r"\bdiagnos(e|is)\b", body, flags=re.IGNORECASE):
            problems.append("contains diagnose/diagnosis")
    return problems

def build_frontmatter(title: str, slug: str, description: str, hub: str, page_type: str) -> str:
    # Hugo YAML frontmatter
    today = datetime.date.today().isoformat()
    fm = f"""---
title: "{title.replace('"','\\"')}"
slug: "{slug}"
description: "{description.replace('"','\\"')}"
date: {today}
hub: "{hub}"
page_type: "{page_type}"
---
"""
    return fm

def main():
    import datetime
    manifest = load_manifest()
    existing = set(manifest.get("generated_slugs", []))

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    titles_raw = kimi_chat(SYSTEM, PROMPT_TITLES.format(n=TITLES_PER_RUN))
    titles = extract_first_json(titles_raw)
    if not isinstance(titles, list) or not titles:
        raise ValueError(f"Title planner returned invalid JSON. First 400 chars:\n{str(titles_raw)[:400]}")

    generated = 0
    attempted = 0

    for t in titles:
        if generated >= PAGES_PER_RUN:
            break
        if not isinstance(t, str) or not t.strip():
            continue
        attempted += 1
        title = t.strip()
        slug = slugify(title)
        if slug in existing:
            continue

        payload = None
        last_problems = None

        for attempt in range(1, 3):  # 2 attempts for speed; strict rails
            resp_text = kimi_chat(SYSTEM, PROMPT_PAGE_JSON.format(title=title))
            try:
                obj = extract_first_json(resp_text)
                if isinstance(obj, dict):
                    problems = looks_good_payload(obj)
                    if not problems:
                        payload = obj
                        break
                    last_problems = problems
                else:
                    last_problems = ["non-object JSON"]
            except Exception as e:
                last_problems = [f"json parse error: {e}"]
            print(f"[WARN] Invalid page payload attempt {attempt} for '{title}': {last_problems}")
            time.sleep(SLEEP_SECONDS)

        if not payload:
            print(f"[SKIP] Could not generate valid payload for '{title}'. Last problems: {last_problems}")
            continue

        # Assemble final Hugo page bundle
        hub = payload["hub"].strip()
        page_type = payload["page_type"].strip()
        desc = payload["description"].strip()[:160]
        body = payload["body_md"].strip()

        # Final hard ban pass
        if re.search(r"\bdiagnos(e|is)\b", (title + " " + desc + " " + body), flags=re.IGNORECASE):
            print(f"[SKIP] Banned word detected (diagnose) for '{title}'")
            continue

        # Write bundle: content/pages/<slug>/index.md
        page_dir = os.path.join(OUTPUT_DIR, slug)
        os.makedirs(page_dir, exist_ok=True)

        # frontmatter written by code -> eliminates frontmatter failures
        today = __import__("datetime").date.today().isoformat()
        frontmatter = f"""---
title: "{title.replace('"','\\"')}"
slug: "{slug}"
description: "{desc.replace('"','\\"')}"
date: {today}
hub: "{hub}"
page_type: "{page_type}"
---
"""
        with open(os.path.join(page_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write(frontmatter)
            f.write("\n")
            f.write(body)
            f.write("\n")

        existing.add(slug)
        generated += 1
        print(f"[OK] {generated}/{PAGES_PER_RUN} {slug}")
        time.sleep(SLEEP_SECONDS)

    manifest["generated_slugs"] = sorted(existing)
    save_manifest(manifest)
    print(f"Generated {generated} pages (attempted {attempted} titles).")

if __name__ == "__main__":
    main()
