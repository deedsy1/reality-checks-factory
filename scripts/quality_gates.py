import os
import json
import re
import shutil
from typing import Dict, List, Tuple

import yaml

ROOT = "content/pages"
MANIFEST_PATH = "scripts/manifest.json"
SITE_CONFIG_PATH = os.getenv("SITE_CONFIG", "data/site.yaml")


def load_yaml(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def split_frontmatter(md: str) -> Tuple[Dict, str]:
    """Return (frontmatter_dict, body_md)."""
    if not md.startswith("---"):
        return {}, md
    parts = md.split("---", 2)
    if len(parts) < 3:
        return {}, md
    fm_raw = parts[1]
    body = parts[2]
    try:
        fm = yaml.safe_load(fm_raw) or {}
        if not isinstance(fm, dict):
            fm = {}
    except Exception:
        fm = {}
    return fm, body


def extract_h2_headings(body: str) -> List[str]:
    return [m.group(1).strip() for m in re.finditer(r"^##\s+(.+?)\s*$", body, flags=re.M)]


def extract_faq_count(body: str) -> int:
    """Count FAQ questions inside the '## FAQs' section.

    Accepts either:
    - '### Question?'
    - 'Q: Question?'
    """
    m = re.search(r"^##\s+FAQs\s*$", body, flags=re.M)
    if not m:
        return 0
    start = m.end()
    # Stop at next H2
    m2 = re.search(r"^##\s+", body[start:], flags=re.M)
    end = start + (m2.start() if m2 else len(body[start:]))
    section = body[start:end]
    h3 = len(re.findall(r"^###\s+.+", section, flags=re.M))
    q = len(re.findall(r"^Q:\s+.+", section, flags=re.M))
    return max(h3, q)




def count_words(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))

def count_internal_links(body: str) -> int:
    # Count markdown links that point to this site (relative /pages/ or /hubs/)
    links = re.findall(r"\[[^\]]+\]\((/[^)]+)\)", body or "")
    return sum(1 for href in links if href.startswith("/pages/") or href.startswith("/hubs/") or href.startswith("/"))
def contains_forbidden(text: str, forbidden: List[str]) -> List[str]:
    t = (text or "").lower()
    hits = []
    for phrase in forbidden:
        p = (phrase or "").strip().lower()
        if not p:
            continue
        if p in t:
            hits.append(phrase)
    return hits


def gate_page(md_path: str, cfg: dict) -> Tuple[bool, List[str]]:
    """Return (pass, reasons)."""
    reasons: List[str] = []
    md = read_text(md_path)

    fm, body = split_frontmatter(md)

    # Gate 1: Frontmatter required keys
    required_fm = cfg.get("gates", {}).get(
        "required_frontmatter",
        ["title", "slug", "summary", "description", "date", "hub", "page_type"],
    )
    missing = [k for k in required_fm if not str(fm.get(k, "")).strip()]
    if missing:
        reasons.append(f"missing frontmatter keys: {', '.join(missing)}")

    # Gate 2: Fixed H2 outline exact + ordered
    outline = (cfg.get("generation", {}) or {}).get("outline_h2", [])
    if outline:
        h2s = extract_h2_headings(body)
        # We require the H2s to contain the outline headings in order.
        # Allow extra H2s ONLY if explicitly enabled.
        allow_extra = bool(cfg.get("gates", {}).get("allow_extra_h2", False))

        if not allow_extra:
            if h2s != outline:
                reasons.append("H2 outline mismatch")
        else:
            # Ensure outline appears as a subsequence in order
            idx = 0
            for h in h2s:
                if idx < len(outline) and h.strip() == outline[idx].strip():
                    idx += 1
            if idx != len(outline):
                reasons.append("H2 outline missing or out of order")

    # Gate 3: Forbidden phrase scan
    forbidden = (cfg.get("generation", {}) or {}).get("forbidden_words", [])
    # Always enforce a minimal default set as a safety net.
    forbidden_default = [
        "as an ai",
        "i am an ai",
        "diagnose",
        "diagnosis",
        "prescribed",
        "guaranteed",
        "sue",
        "legal advice",
        "medical advice",
        "financial advice",
    ]
    merged = list(dict.fromkeys([*(forbidden or []), *forbidden_default]))
    hits = contains_forbidden(md, merged)
    if hits:
        reasons.append(f"forbidden phrases: {', '.join(hits[:8])}{'...' if len(hits) > 8 else ''}")

    # Gate 4: FAQ count
    faq_min = int(cfg.get("gates", {}).get("faq_min", 4))
    faq_max = int(cfg.get("gates", {}).get("faq_max", 6))
    faq_n = extract_faq_count(body)
    if faq_n < faq_min or faq_n > faq_max:
        reasons.append(f"FAQ count out of range ({faq_n}, expected {faq_min}-{faq_max})")



# Gate 4b: Word count (evergreen depth)
wc_cfg = (cfg.get("gates", {}) or {}).get("word_count", {}) or {}
hard_min = int(wc_cfg.get("hard_min", wc_cfg.get("min", 800)))
hard_max = int(wc_cfg.get("hard_max", wc_cfg.get("max", 2000)))
wc = count_words(body)
if wc < hard_min or wc > hard_max:
    reasons.append(f"word count out of range ({wc}, expected {hard_min}-{hard_max})")

# Gate 4c: Prohibited regex patterns (dates/prices/first-person/etc)
patterns = (cfg.get("gates", {}) or {}).get("prohibited_regex", []) or []
hits = []
for pat in patterns:
    try:
        if re.search(pat, body, flags=re.I):
            hits.append(pat)
    except re.error:
        continue
if hits:
    reasons.append(f"prohibited pattern hit ({len(hits)} rules)")

# Gate 4d: Internal links minimum
min_links = int((cfg.get("gates", {}) or {}).get("internal_links_min", 0))
if min_links > 0:
    n_links = count_internal_links(body)
    if n_links < min_links:
        reasons.append(f"too few internal links ({n_links}, expected >= {min_links})")
    # Optional Gate 5: section minimum words (lightweight)
    min_words = int(os.getenv("MIN_SECTION_WORDS", str(cfg.get("gates", {}).get("min_section_words", 0))))
    if min_words > 0 and outline:
        # Rough split by H2
        for heading in outline:
            sec = re.split(rf"^##\s+{re.escape(heading)}\s*$", body, flags=re.M)
            if len(sec) < 2:
                continue
            after = sec[1]
            # Up to next H2
            after = re.split(r"^##\s+", after, maxsplit=1, flags=re.M)[0]
            wc = len(re.findall(r"\b\w+\b", after))
            if wc < min_words and heading.strip().lower() != "faqs":
                reasons.append(f"section too short: '{heading}' ({wc} words < {min_words})")
                break

    return (len(reasons) == 0), reasons


def main():
    cfg = load_yaml(SITE_CONFIG_PATH)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f) or {}

    deleted = 0
    checked = 0
    failures = []

    for slug in manifest.get("generated_this_run", []):
        md_path = os.path.join(ROOT, slug, "index.md")
        if not os.path.isfile(md_path):
            continue

        checked += 1
        ok, reasons = gate_page(md_path, cfg)
        if ok:
            continue

        shutil.rmtree(os.path.join(ROOT, slug), ignore_errors=True)
        deleted += 1
        failures.append({"slug": slug, "reasons": reasons})

    print(f"Quality gates complete. Checked {checked} pages. Deleted {deleted} pages.")
    if failures:
        print("\n---- FAILURES (first 20) ----")
        for item in failures[:20]:
            print(f"- {item['slug']}: {', '.join(item['reasons'])}")
        if len(failures) > 20:
            print(f"...and {len(failures) - 20} more")


if __name__ == "__main__":
    main()
