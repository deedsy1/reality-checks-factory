import os, re, sys

ROOT = "content/pages"

BANNED = [
    r"\byou should\b",
    r"\bguarantee(d)?\b",
    r"\blegal advice\b",
    r"\bmedical advice\b",
    r"\bdiagnos(e|is)\b",
    r"\bsue\b",
    r"\bprescribe\b",
]

REQUIRED_KEYS = ["title:", "slug:", "description:", "date:", "hub:", "page_type:"]
MIN_H2 = 5
MIN_FAQ = 6

def count(pattern, text):
    return len(re.findall(pattern, text, flags=re.IGNORECASE | re.MULTILINE))

def main():
    failures = []
    if not os.path.isdir(ROOT):
        print("No pages yet. PASS.")
        return

    for slug in os.listdir(ROOT):
        p = os.path.join(ROOT, slug, "index.md")
        if not os.path.isfile(p):
            continue
        txt = open(p, "r", encoding="utf-8").read()

        for k in REQUIRED_KEYS:
            if k not in txt:
                failures.append((slug, f"Missing frontmatter key: {k}"))

        for b in BANNED:
            if re.search(b, txt, flags=re.IGNORECASE):
                failures.append((slug, f"Banned phrase hit: {b}"))

        h2 = count(r"^##\s+", txt)
        if h2 < MIN_H2:
            failures.append((slug, f"Too few H2 sections: {h2}"))

        # FAQs counted as lines starting with **Q:**
        faq = count(r"^\*\*Q:\*\*", txt)
        if faq < MIN_FAQ:
            failures.append((slug, f"Too few FAQs: {faq}"))

    if failures:
        for slug, msg in failures[:80]:
            print(f"[FAIL] {slug}: {msg}")
        print(f"Total failures: {len(failures)}")
        sys.exit(1)

    print("Quality gates: PASS")

if __name__ == "__main__":
    main()
