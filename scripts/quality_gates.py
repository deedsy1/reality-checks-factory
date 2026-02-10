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


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def get_h2_section(body: str, heading: str) -> str:
    """Return the content under an H2 heading up to the next H2 (excluding the H2 line)."""
    m = re.search(rf"^##\s+{re.escape(heading)}\s*$", body, flags=re.M)
    if not m:
        return ""
    start = m.end()
    m2 = re.search(r"^##\s+", body[start:], flags=re.M)
    end = start + (m2.start() if m2 else len(body[start:]))
    return body[start:end].strip()


def extract_internal_links(body: str) -> List[Tuple[str, str]]:
    """Return list of (anchor_text, url) for internal markdown links."""
    links: List[Tuple[str, str]] = []
    for m in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", body):
        text = (m.group(1) or "").strip()
        url = (m.group(2) or "").strip()
        if not url:
            continue
        # Internal links: relative or site-absolute, but not http(s)
        if url.startswith("http://") or url.startswith("https://") or url.startswith("mailto:"):
            continue
        links.append((text, url))
    return links


def paragraph_sentence_ok(body: str, max_sentences: int) -> bool:
    """Enforce short paragraphs (2–3 sentences) on prose paragraphs only."""
    # Split by blank lines. Ignore headings/lists/code blocks.
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]
    in_code = False
    for b in blocks:
        if "```" in b:
            # Toggle simplistic code block detection
            ticks = b.count("```")
            if ticks % 2 == 1:
                in_code = not in_code
            continue
        if in_code:
            continue
        first = b.splitlines()[0].strip()
        if first.startswith("#") or first.startswith("-") or first.startswith("*") or first.startswith(">"):
            continue
        # Count sentences: ., !, ? not inside abbreviations (best-effort)
        sentences = re.findall(r"[.!?]+(?:\s|$)", b)
        if len(sentences) > max_sentences:
            return False
    return True


def contains_forbidden_regex(text: str, patterns: List[str]) -> List[str]:
    hits = []
    for pat in patterns:
        try:
            if re.search(pat, text, flags=re.I | re.M):
                hits.append(pat)
        except re.error:
            # Skip bad regex
            continue
    return hits


def contains_forbidden_substrings(text: str, forbidden: List[str]) -> List[str]:
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

    generation = (cfg.get("generation", {}) or {})
    gates = (cfg.get("gates", {}) or {})

    # --------------------
    # Gate 1: Frontmatter required keys
    # --------------------
    required_fm = gates.get(
        "required_frontmatter",
        ["title", "slug", "summary", "description", "date", "hub", "page_type"],
    )
    missing = [k for k in required_fm if not str(fm.get(k, "")).strip()]
    if missing:
        reasons.append(f"missing frontmatter keys: {', '.join(missing)}")

    # --------------------
    # Gate 2: Headings policy (H2 / H3 only)
    # --------------------
    if re.search(r"^#\s+", body, flags=re.M):
        reasons.append("H1 found in body (only H2/H3 allowed)")
    if re.search(r"^####+\s+", body, flags=re.M):
        reasons.append("H4+ found (only H2/H3 allowed)")

    # --------------------
    # Gate 3: Fixed H2 outline exact + ordered
    # --------------------
    outline = generation.get("outline_h2", [])
    if outline:
        h2s = extract_h2_headings(body)
        allow_extra = bool(gates.get("allow_extra_h2", False))
        if not allow_extra:
            if h2s != outline:
                reasons.append("H2 outline mismatch")
        else:
            idx = 0
            for h in h2s:
                if idx < len(outline) and h.strip() == outline[idx].strip():
                    idx += 1
            if idx != len(outline):
                reasons.append("H2 outline missing or out of order")

    # --------------------
    # Gate 4: Prohibitions + style constitution (strict)
    # --------------------
    # Substring bans (easy, low false-negative)
    forbidden_default = [
        "as an ai",
        "i am an ai",
        "diagnose",
        "diagnosis",
        "prescribed",
        "legal advice",
        "medical advice",
        "financial advice",
        "affiliate",
        "sponsored",
        "review",
        "coupon",
        "discount",
        "deal",
        "best product",
        "worst",
        "guarantee",
        "guaranteed",
        "promise",
        "click here",
    ]
    forbidden_cfg = generation.get("forbidden_words", []) or []
    merged = list(dict.fromkeys([*forbidden_cfg, *forbidden_default]))
    hits = contains_forbidden_substrings(body, merged)
    if hits:
        reasons.append(f"forbidden phrases: {', '.join(hits[:10])}{'...' if len(hits) > 10 else ''}")

    # Regex bans (hard prohibitions)
    hard_bans = [
        # Dates / recency
        r"\b(20\d{2})\b",
        r"\b(recent|currently|nowadays|these days|this year|today)\b",
        # Prices / money claims (symbols and common currencies)
        r"[$€£¥]\s*\d",
        r"\b(usd|aud|eur|gbp|cad|inr|yen|dollars|bucks)\b",
        r"\b(price|pricing|cost|costs|cheaper|expensive)\b",
        # First-person language (including contractions)
        r"\b(i|i'm|i’ve|i've|i’d|i'd|me|my|mine|we|we're|we’ve|we've|we’d|we'd|our|ours|us)\b",
        # Calls to action / behavior pushing (keep conservative)
        r"\b(you should|do this|make sure to|start by|try to|avoid doing|always do|never do|take action)\b",
        r"\b(sign up|subscribe|buy|purchase|download|join)\b",
        # Strong promises / guarantees
        r"\b(will definitely|will always|no doubt|surefire|guaranteed to|ensure that)\b",
        # Superiority comparisons
        r"\b(better than|more effective|best|worse than|superior to)\b",
    ]
    ban_hits = contains_forbidden_regex(body, hard_bans)
    if ban_hits:
        reasons.append("hard prohibitions hit")

    # --------------------
    # Gate 5: Explain before comparisons (no comparison markers before Core explanation)
    # --------------------
    comparison_markers = [
        r"\b(vs\.?|versus|compared to|in comparison|better than|worse than|more effective)\b"
    ]
    core_heading = gates.get("core_heading", "Core explanation")
    core_pos = None
    m_core = re.search(rf"^##\s+{re.escape(core_heading)}\s*$", body, flags=re.M)
    if m_core:
        core_pos = m_core.start()
    else:
        # If a site doesn't use the constitution structure, skip this specific gate.
        core_pos = None

    if core_pos is not None:
        prefix = body[:core_pos]
        if contains_forbidden_regex(prefix, comparison_markers):
            reasons.append("comparison appears before Core explanation")

    # --------------------
    # Gate 6: FAQ count
    # --------------------
    faq_min = int(gates.get("faq_min", 4))
    faq_max = int(gates.get("faq_max", 6))
    faq_n = extract_faq_count(body)
    if faq_n < faq_min or faq_n > faq_max:
        reasons.append(f"FAQ count out of range ({faq_n}, expected {faq_min}-{faq_max})")

    # --------------------
    # Gate 7: Length (no thin content)
    # --------------------
    min_words = int(gates.get("min_words", 800))
    wc = word_count(body)
    if wc < min_words:
        reasons.append(f"too short ({wc} words < {min_words})")

    # --------------------
    # Gate 8: Short paragraphs (2–3 sentences max)
    # --------------------
    max_sentences = int(gates.get("max_sentences_per_paragraph", 3))
    if max_sentences > 0 and not paragraph_sentence_ok(body, max_sentences):
        reasons.append("paragraphs too long (sentence count)")

    # --------------------
    # Gate 9: Internal linking rules
    # --------------------
    links = extract_internal_links(body)
    internal_min = int(gates.get("internal_links_min", 3))
    if len(links) < internal_min:
        reasons.append(f"too few internal links ({len(links)} < {internal_min})")

    # Anchor text policy: no "click here"
    bad_anchor = [t for (t, _u) in links if t.strip().lower() == "click here"]
    if bad_anchor:
        reasons.append('bad anchor text: "click here"')

    # Contextual placement: require at least 1 link in Definitions/Core/Summary (if those headings exist)
    for sec_name in gates.get("link_sections_min1", ["Definitions", "Core explanation", "Summary"]):
        sec = get_h2_section(body, sec_name)
        if not sec:
            continue  # don't fail older structures
        sec_links = extract_internal_links(sec)
        if len(sec_links) < 1:
            reasons.append(f"missing internal link in section: {sec_name}")

    # --------------------
    # Gate 10: Optional per-section minimum words (lightweight)
    # --------------------
    min_section_words = int(gates.get("min_section_words", 0))
    if min_section_words > 0 and outline:
        for heading in outline:
            if heading.strip().lower() == "faqs":
                continue
            sec = get_h2_section(body, heading)
            if not sec:
                continue
            sec_wc = word_count(sec)
            if sec_wc < min_section_words:
                reasons.append(f"section too short: '{heading}' ({sec_wc} < {min_section_words})")
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
