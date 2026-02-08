import os, re, sys

ROOT = "content/pages"

BANNED = [
    r"\bdiagnos(e|is)\b",
    r"\bmedical advice\b",
    r"\blegal advice\b",
    r"\bsue\b",
    r"\bprescribe\b",
    r"\bguarantee(d)?\b",
]

REQUIRED_FRONTMATTER_KEYS = ["title:", "slug:", "description:", "date:", "hub:", "page_type:"]
MIN_H2 = 5
MIN_FAQ = 6

def count(pattern, text):
    return len(re.findall(pattern, text, flags=re.IGNORECASE | re.MULTILINE))

def main():
    if not os.path.isdir(ROOT):
        print(f"No pages directory found at {ROOT}. Nothing to validate.")
        sys.exit(0)

    failures = []

    for slug in os.listdir(ROOT):
        p = os.path.join(ROOT, slug, "index.md")
        if not os.path.isfile(p):
            continue
        txt = open(p, "r", encoding="utf-8").read()

        # must have frontmatter delimiters
        if not txt.strip().startswith("---") or txt.count("---") < 2:
            failures.append((slug, "Missing YAML frontmatter delimiters '---'"))
            continue

        for k in REQUIRED_FRONTMATTER_KEYS:
            if k not in txt:
                failures.append((slug, f"Missing frontmatter key: {k}"))

        for b in BANNED:
            if re.search(b, txt, flags=re.IGNORECASE):
                failures.append((slug, f"Banned phrase hit: {b}"))

        h2 = count(r"^##\s+", txt)
        if h2 < MIN_H2:
            failures.append((slug, f"Too few H2 sections: {h2}"))

        # More forgiving FAQ detection
        has_faq_header = re.search(r"^##\s+FAQs?\b", txt, flags=re.IGNORECASE | re.MULTILINE) is not None
        q_markers = count(r"^\s*(?:[-*]\s+)?(?:\*\*)?Q:", txt)

        # If FAQs header exists, accept either Q: markers or bullet Qs
        bullet_questions = count(r"^\s*[-*]\s+.+\?$", txt)

        faq_score = 0
        if has_faq_header:
            faq_score = max(q_markers, bullet_questions)

        if faq_score < MIN_FAQ:
            failures.append((slug, f"Too few FAQs: {faq_score}"))

    if failures:
        for slug, msg in failures[:80]:
            print(f"[FAIL] {slug}: {msg}")
        print(f"Total failures: {len(failures)}")
        sys.exit(1)

    print("Quality gates: PASS")

if __name__ == "__main__":
    main()
