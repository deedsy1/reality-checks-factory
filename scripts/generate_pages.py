import os
import json
import time
import re
import random
import requests
from datetime import date
import yaml

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
SITE_CONFIG_PATH = os.getenv("SITE_CONFIG", "data/site.yaml")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

def resolve_site_config_path() -> str:
    """Prefer the single contract at data/site.yaml.
    Backward compatible: fall back to scripts/site_config.yaml if needed.
    """
    p = SITE_CONFIG_PATH
    if os.path.isfile(p):
        return p
    fallback = "scripts/site_config.yaml"
    if os.path.isfile(fallback):
        return fallback
    raise FileNotFoundError(f"Site config not found: {p} (and no {fallback} fallback)")

def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def ensure_manifest_shape(m: dict) -> dict:
    if not isinstance(m, dict):
        return {"used_titles": [], "generated_this_run": []}
    m.setdefault("used_titles", [])
    m.setdefault("generated_this_run", [])
    return m

def load_manifest():
    if not os.path.exists(MANIFEST_PATH):
        return {"used_titles": [], "generated_this_run": []}
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return ensure_manifest_shape(json.load(f))

def save_manifest(m):
    m = ensure_manifest_shape(m)
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
    raw = (raw or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    raw2 = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw2 = re.sub(r"\s*```$", "", raw2)
    try:
        return json.loads(raw2)
    except json.JSONDecodeError:
        pass

    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise json.JSONDecodeError("No JSON object found", raw, 0)
    return json.loads(m.group(0))

def call_kimi(system: str, prompt: str):
    payload = {
        "model": MODEL,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
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

def build_prompts(cfg: dict):
    brand = cfg.get("brand", "Reality Checks")
    hubs = cfg.get("content", {}).get("hubs", [
        "work-career", "money-stress", "burnout-load", "milestones", "social-norms"
    ])
    page_types = cfg.get("content", {}).get("page_types", [
        "is-it-normal", "checklist", "red-flags", "myth-vs-reality", "explainer"
    ])

    forbidden = cfg.get("writing", {}).get("forbidden_words", [])
    forbidden_str = ", ".join(forbidden) if forbidden else "diagnose, diagnosis, prescribed, guaranteed, sue"

    outline = cfg.get("prompts", {}).get("fixed_h2_outline", [
        "What this feeling usually means",
        "Common reasons",
        "What makes it worse",
        "What helps (non-advice)",
        "When it might signal a bigger issue",
        "FAQs",
    ])
    outline_md = "\n".join([f"## {h}" for h in outline])

    closing_templates = cfg.get("prompts", {}).get("closing_reassurance_templates", [])
    closing_hint = ""
    if closing_templates:
        closing_hint = "Choose ONE closing reassurance line in a similar style to these:\n- " + "\n- ".join(closing_templates[:3])

    system = f"""You write calm, reassuring evergreen content for the site "{brand}".
NO medical, legal, or financial advice. Avoid diagnosing. Avoid giving instructions like a professional.
Forbidden words/phrases: {forbidden_str}.
Return JSON only. Do not wrap in markdown fences.
"""

    page_prompt = f"""Return ONLY JSON with:
title
summary (one sentence reassurance; also used as meta description)
description (<= 160 chars, no quotes)
hub (one of: { " | ".join(hubs) })
page_type (one of: { " | ".join(page_types) })
closing_reassurance (one short, gentle line; NOT advice)
body_md (markdown only; must include the exact H2 headings below)

Use these H2 sections exactly:
{outline_md}

Rules:
- Keep tone grounded and human, not clinical.
- No "diagnose/diagnosis/prescribed/guaranteed/sue".
- FAQs: 4-6 Q&As (short).
- Do not include the closing reassurance inside body_md; put it in closing_reassurance.
{closing_hint}
"""
    return system, page_prompt

def choose_close(data: dict, cfg: dict) -> str:
    close = (data.get("closing_reassurance") or "").strip()
    if close:
        return close

    templates = cfg.get("prompts", {}).get("closing_reassurance_templates", [])
    if templates:
        return random.choice(templates).strip()
    return "If this hit close to home, you’re not alone — and you’re not failing."

def main():
    cfg = load_yaml(resolve_site_config_path()) if os.path.exists(SITE_CONFIG_PATH) else {}
    system, page_prompt = build_prompts(cfg)

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

    per_title_fail = {}
    PER_TITLE_CAP = int(os.getenv("PER_TITLE_CAP", "2"))

    for title in titles:
        if produced >= PAGES_PER_RUN or attempts >= MAX_ATTEMPTS:
            break

        slug = slugify(title)

        if slug in used:
            continue

        if per_title_fail.get(slug, 0) >= PER_TITLE_CAP:
            continue

        attempts += 1

        try:
            raw = call_kimi(system, f"{page_prompt}\n\nTitle: {title}")
            data = parse_json_strict_or_extract(raw)
        except Exception:
            retries += 1
            per_title_fail[slug] = per_title_fail.get(slug, 0) + 1
            continue

        body = (data.get("body_md") or "").strip()

        required_h2 = cfg.get("prompts", {}).get("fixed_h2_outline", [])
        if required_h2:
            missing = [h for h in required_h2 if f"## {h}" not in body]
            if missing:
                deletes += 1
                per_title_fail[slug] = per_title_fail.get(slug, 0) + 1
                continue
        else:
            if body.count("## ") < 6:
                deletes += 1
                per_title_fail[slug] = per_title_fail.get(slug, 0) + 1
                continue

        required = ["title", "summary", "description", "hub", "page_type"]
        if any((k not in data or not str(data[k]).strip()) for k in required):
            deletes += 1
            per_title_fail[slug] = per_title_fail.get(slug, 0) + 1
            continue

        close = choose_close(data, cfg)

        page_dir = os.path.join(CONTENT_ROOT, slug)
        os.makedirs(page_dir, exist_ok=True)

        def esc(s: str) -> str:
            return str(s).replace('"', r'\"').strip()

        md = f"""---
title: "{esc(data['title'])}"
slug: "{slug}"
summary: "{esc(data['summary'])}"
description: "{esc(data['description'])}"
date: "{date.today().isoformat()}"
hub: "{esc(data['hub'])}"
page_type: "{esc(data['page_type'])}"
---

**{esc(data['summary'])}**

{body}

---

*{esc(close)}*
"""

        with open(os.path.join(page_dir, "index.md"), "w", encoding="utf-8") as f:
            f.write(md)

        produced += 1
        used.add(slug)
        manifest.setdefault("used_titles", []).append(slug)
        manifest.setdefault("generated_this_run", []).append(slug)
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
