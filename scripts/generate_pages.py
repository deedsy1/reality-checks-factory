import os
import json
import time
import re
import random
import requests
from datetime import date

BASE_URL = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1").rstrip("/")
API_KEY = os.environ["MOONSHOT_API_KEY"]
MODEL = os.getenv("KIMI_MODEL", "kimi-k2.5")

PAGES_PER_RUN = int(os.getenv("PAGES_PER_RUN", "10"))
MAX_ATTEMPTS = int(os.getenv("MAX_ATTEMPTS", "30"))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "1700"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "1"))
SLEEP_SECONDS = float(os.getenv("SLEEP_SECONDS", "0.2"))

CONTENT_ROOT = "content/pages"
MANIFEST_PATH = "scripts/manifest.json"
TITLES_POOL_PATH = "scripts/titles_pool.txt"

HUBS = ["work-career", "money-stress", "burnout-load", "milestones", "social-norms"]
PAGE_TYPES = ["is-it-normal", "red-flags", "myth-vs-reality", "checklist", "explainer"]

FIXED_H2 = [
    "What this feeling usually means",
    "Common reasons",
    "What makes it worse",
    "What helps (non-advice)",
    "When it might signal a bigger issue",
    "FAQs",
]

HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

SYSTEM = """You generate calm, reassuring evergreen content.
NO medical, legal, or financial advice.
Forbidden words: diagnose, diagnosis, prescribed, guaranteed, sue.

You MUST return valid JSON only. No markdown fences, no commentary.
"""

def load_manifest():
    if not os.path.exists(MANIFEST_PATH):
        return {"used_slugs": [], "generated_this_run": [], "template_index": 0}
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        m = json.load(f)
    if "used_slugs" not in m:
        m["used_slugs"] = m.get("used_titles", [])
    if "generated_this_run" not in m:
        m["generated_this_run"] = []
    if "template_index" not in m:
        m["template_index"] = 0
    return m

def save_manifest(m):
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=2, ensure_ascii=False)

def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s[:90].strip("-")

def load_titles():
    with open(TITLES_POOL_PATH, "r", encoding="utf-8") as f:
        return [t.strip() for t in f if t.strip() and not t.strip().startswith("#")]

def word_overlap_score(a_slug: str, b_slug: str) -> float:
    a = set(a_slug.split("-"))
    b = set(b_slug.split("-"))
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, len(a | b))

def too_similar(slug: str, existing_slugs: set[str], threshold: float = 0.55) -> bool:
    for s in existing_slugs:
        if word_overlap_score(slug, s) >= threshold:
            return True
    return False

def parse_frontmatter(md_text: str) -> dict:
    if not md_text.strip().startswith("---"):
        return {}
    parts = md_text.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = parts[1]
    out = {}
    for line in fm.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out

def build_internal_link_map() -> dict:
    link_map = {h: [] for h in HUBS}
    if not os.path.isdir(CONTENT_ROOT):
        return link_map

    for slug in os.listdir(CONTENT_ROOT):
        p = os.path.join(CONTENT_ROOT, slug, "index.md")
        if not os.path.isfile(p):
            continue
        txt = open(p, "r", encoding="utf-8").read()
        fm = parse_frontmatter(txt)
        hub = fm.get("hub", "")
        if hub in link_map:
            link_map[hub].append(slug)

    for h in link_map:
        random.shuffle(link_map[h])
    return link_map

def call_kimi(prompt: str) -> str:
    payload = {
        "model": MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
    }

    last_err = None
    for attempt in range(3):
        r = requests.post(f"{BASE_URL}/chat/completions", headers=HEADERS, json=payload, timeout=60)
        if r.status_code < 400:
            return r.json()["choices"][0]["message"]["content"]

        last_err = r.text
        if r.status_code in (429, 500, 502, 503):
            time.sleep(2 ** attempt)
            continue
        break

    raise RuntimeError(f"Kimi API failed: {last_err}")

def require_json_obj(text: str) -> dict:
    if not text or not text.strip():
        raise ValueError("Empty response")
    t = text.strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", t)
    if not m:
        raise ValueError(f"No JSON object found. First 300 chars:\n{t[:300]}")
    return json.loads(m.group(0))

def choose_page_type(manifest: dict) -> str:
    idx = int(manifest.get("template_index", 0)) % len(PAGE_TYPES)
    manifest["template_index"] = idx + 1
    return PAGE_TYPES[idx]

def build_prompt(title: str, page_type: str, link_targets: list[str]) -> str:
    targets_md = "\n".join([f"- /pages/{s}/" for s in link_targets]) if link_targets else "- (no existing pages yet)"

    fixed = "\n".join([f"## {h}" for h in FIXED_H2])

    return f"""Return ONLY a valid JSON object with keys:
title
summary (ONE sentence, 12–22 words, no advice, no dates, no prices)
hub (one of: {", ".join(HUBS)})
page_type (must be exactly: {page_type})
body_md (markdown body ONLY; NO frontmatter)

You MUST use these exact H2 headings (in this exact order):
{fixed}

Internal linking rules:
- You MUST include 4–6 internal links, using ONLY these exact URLs (pick relevant ones):
{targets_md}
- Format links as: [anchor text](/pages/slug/)
- Do NOT invent slugs. Do NOT use external links.

Content rules:
- Calm, reassuring, globally applicable.
- Avoid medical/legal/financial advice.
- Avoid forbidden words: diagnose, diagnosis, prescribed, guaranteed, sue.
- Keep it evergreen.

Now write the page for the title:
{title}
"""

def looks_valid(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    for k in ("title", "summary", "hub", "page_type", "body_md"):
        if k not in data or not str(data[k]).strip():
            return False
    body = data["body_md"]
    for h in FIXED_H2:
        if f"## {h}" not in body:
            return False
    if len(re.findall(r"\]\(/pages/[^)]+/\)", body)) < 4:
        return False
    return True

def yaml_escape(s: str) -> str:
    s = s.replace('"', '\\"')
    s = s.replace("\n", " ").strip()
    return s

def main():
    os.makedirs(CONTENT_ROOT, exist_ok=True)
    manifest = load_manifest()
    titles = load_titles()
    random.shuffle(titles)

    existing_slugs = set(manifest.get("used_slugs", []))
    link_map = build_internal_link_map()

    manifest["generated_this_run"] = []
    produced = 0
    attempts = 0

    while produced < PAGES_PER_RUN and attempts < MAX_ATTEMPTS:
        if not titles:
            break
        title = titles.pop(0)
        attempts += 1

        slug = slugify(title)
        if slug in existing_slugs:
            continue
        if too_similar(slug, existing_slugs):
            continue

        page_type = choose_page_type(manifest)

        all_existing = []
        for h in HUBS:
            all_existing.extend(link_map.get(h, []))
        random.shuffle(all_existing)
        link_targets = all_existing[:6]

        prompt = build_prompt(title, page_type, link_targets)

        data = None
        for _ in range(2):
            try:
                raw = call_kimi(prompt)
                data = require_json_obj(raw)
                if looks_valid(data):
                    break
            except Exception:
                data = None

        if not data or not looks_valid(data):
            continue

        hub = data["hub"] if data["hub"] in HUBS else "social-norms"
        page_type_out = data["page_type"] if data["page_type"] in PAGE_TYPES else page_type

        page_dir = os.path.join(CONTENT_ROOT, slug)
        os.makedirs(page_dir, exist_ok=True)

        title_y = yaml_escape(str(data["title"]))
        summary_y = yaml_escape(str(data["summary"]))
        body = str(data["body_md"]).strip()

        md = (
            "---\n"
            f'title: "{title_y}"\n'
            f'slug: "{slug}"\n'
            f'description: "{summary_y}"\n'
            f'date: "{date.today().isoformat()}"\n'
            f'hub: "{hub}"\n'
            f'page_type: "{page_type_out}"\n'
            "---\n\n"
            f"{summary_y}\n\n"
            f"{body}\n"
        )

        with open(os.path.join(page_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write(md)

        produced += 1
        existing_slugs.add(slug)
        manifest["used_slugs"].append(slug)
        manifest["generated_this_run"].append(slug)
        link_map.setdefault(hub, []).append(slug)

        print(f"[OK] {produced}/{PAGES_PER_RUN} {slug} ({page_type_out}, {hub})")
        time.sleep(SLEEP_SECONDS)

    save_manifest(manifest)
    print(f"Produced {produced} pages in {attempts} attempts")

if __name__ == "__main__":
    main()
