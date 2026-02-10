#!/usr/bin/env python3
import os
import re
import sys
import yaml
from typing import Dict, List, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_YAML = os.path.join(REPO_ROOT, "data", "site.yaml")

def load_yaml(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        return {}

def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def split_frontmatter(md: str) -> Tuple[Dict, str]:
    """Return (frontmatter_dict, body_text)."""
    if not md.startswith("---"):
        return {}, md
    parts = md.split("\n---\n", 2)
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
    """Counts FAQ items by looking for H3 headings under the FAQs section."""
    # Find the FAQs section
    m = re.search(r"^##\s+FAQs\s*$", body, flags=re.M)
    if not m:
        return 0
    after = body[m.end():]
    # Up to next H2
    after = re.split(r"^##\s+", after, maxsplit=1, flags=re.M)[0]
    # Count H3 lines inside
    return len(re.findall(r"^###\s+.+$", after, flags=re.M))

def contains_forbidden(text: str, forbidden: List[str]) -> List[str]:
    hits = []
    lower = text.lower()
    for w in forbidden:
        if not w:
            continue
        if w.lower() in lower:
            hits.append(w)
    return hits

def iter_internal_links(body: str) -> List[Tuple[str, str]]:
    """Return list of (anchor_text, url) for markdown links that are internal."""
    links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", body)
    out = []
    for text, url in links:
        url = url.strip()
        if url.startswith("http://") or url.startswith("https://") or url.startswith("mailto:"):
            continue
        if url.startswith("/"):
            out.append((text.strip(), url))
    return out

def strip_code_fences(md: str) -> str:
    # Remove fenced code blocks to avoid false positives
    return re.sub(r"```.*?```", "", md, flags=re.S)

def paragraph_sentence_counts(body: str) -> List[int]:
    """Return sentence counts per paragraph (excluding headings & list-like blocks)."""
    body = strip_code_fences(body)
    paras = re.split(r"\n\s*\n", body.strip())
    counts = []
    for p in paras:
        p = p.strip()
        if not p:
            continue
        if p.startswith("#"):
            continue
        if re.match(r"^(\-|\*|\d+\.)\s+", p):
            continue
        # Ignore short fragments (like single bold line)
        if len(re.findall(r"\b\w+\b", p)) < 8:
            continue
        # Count sentences (roughly)
        sentences = re.findall(r"[.!?]+", p)
        counts.append(len(sentences))
    return counts

def intro_word_count(body: str) -> int:
    """Word count before the first H2 heading."""
    before = re.split(r"^##\s+", body, maxsplit=1, flags=re.M)[0]
    return len(re.findall(r"\b\w+\b", before))

def word_count(body: str) -> int:
    body = strip_code_fences(body)
    return len(re.findall(r"\b\w+\b", body))

def heading_level_violations(body: str) -> List[str]:
    """Enforce H2/H3 only (no H1, H4+)."""
    bad = []
    for m in re.finditer(r"^(#+)\s+.+$", body, flags=re.M):
        level = len(m.group(1))
        if level == 1 or level >= 4:
            bad.append(m.group(0).strip())
    return bad

def regex_hits(text: str, patterns: List[str]) -> List[str]:
    hits = []
    for pat in patterns or []:
        try:
            if re.search(pat, text, flags=re.I | re.M):
                hits.append(pat)
        except re.error:
            # ignore invalid patterns
            continue
    return hits

def gate_page(md_path: str, cfg: dict) -> Tuple[bool, List[str]]:
    """Return (pass, reasons)."""
    reasons: List[str] = []
    md = read_text(md_path)
    fm, body = split_frontmatter(md)

    gates = (cfg.get("gates", {}) or {})
    generation = (cfg.get("generation", {}) or {})

    # Gate 1: Frontmatter required keys
    required_fm = gates.get(
        "required_frontmatter",
        ["title", "slug", "summary", "description", "date", "hub", "page_type"],
    )
    missing = [k for k in required_fm if not str(fm.get(k, "")).strip()]
    if missing:
        reasons.append(f"missing frontmatter keys: {', '.join(missing)}")

    # Gate 2: Fixed H2 outline exact + ordered
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

    # Gate 3: Forbidden phrase scan (simple substring)
    forbidden = generation.get("forbidden_words", [])
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

    # Gate 4: Regex prohibitions (body only; optional)
    banned_regex = gates.get("banned_regex", [])
    body_for_scan = strip_code_fences(body)
    if gates.get("ban_dates_in_body", True):
        # Scan with config patterns; if not provided, do nothing.
        rh = regex_hits(body_for_scan, banned_regex)
        if rh:
            reasons.append("regex prohibitions hit (see config)")

    # Gate 5: FAQ count
    faq_min = int(gates.get("faq_min", 4))
    faq_max = int(gates.get("faq_max", 6))
    faq_n = extract_faq_count(body)
    if faq_n < faq_min or faq_n > faq_max:
        reasons.append(f"FAQ count out of range ({faq_n}, expected {faq_min}-{faq_max})")

    # Gate 6: Heading levels (H2/H3 only)
    if gates.get("enforce_heading_levels", True):
        bad_heads = heading_level_violations(body_for_scan)
        if bad_heads:
            reasons.append("invalid heading levels (H1 or H4+)")

    # Gate 7: Intro existence (words before first H2)
    min_intro_words = int(gates.get("min_intro_words", 0))
    if min_intro_words > 0:
        iwc = intro_word_count(body_for_scan)
        if iwc < min_intro_words:
            reasons.append(f"intro too short ({iwc} words < {min_intro_words})")

    # Gate 8: Minimum word count
    min_words = int(gates.get("min_words", 0))
    max_words = int(gates.get("max_words", 10_000))
    wc = word_count(body_for_scan)
    if wc < min_words:
        reasons.append(f"too short ({wc} words < {min_words})")
    if wc > max_words:
        reasons.append(f"too long ({wc} words > {max_words})")

    # Gate 9: Internal linking
    min_links = int(gates.get("min_internal_links", 0))
    links = iter_internal_links(body_for_scan)
    if min_links > 0 and len(links) < min_links:
        reasons.append(f"too few internal links ({len(links)} < {min_links})")
    # No "click here" anchors
    for t, _u in links:
        if t.strip().lower() in ("click here", "here"):
            reasons.append('bad link anchor ("click here"/"here")')
            break

    # Gate 10: Paragraph sentence length
    max_sent = int(gates.get("max_sentences_per_paragraph", 0))
    if max_sent > 0:
        counts = paragraph_sentence_counts(body_for_scan)
        if any(c > max_sent for c in counts):
            reasons.append("paragraphs too long (too many sentences)")

    return (len(reasons) == 0), reasons

def main():
    cfg = load_yaml(SITE_YAML)
    content_root = os.path.join(REPO_ROOT, "content", "pages")
    failures = 0

    for dirpath, dirnames, filenames in os.walk(content_root):
        if "index.md" not in filenames:
            continue
        p = os.path.join(dirpath, "index.md")
        ok, reasons = gate_page(p, cfg)
        if not ok:
            failures += 1
            slug = os.path.basename(os.path.dirname(p))
            for r in reasons:
                print(f"[FAIL] {slug}: {r}")

    print(f"Quality gates complete. Failed {failures} pages.")
    if failures > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
