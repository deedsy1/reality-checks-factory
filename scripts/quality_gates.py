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
    r"\binvest\b",
    r"\bROI\b",
]

REQUIRED_FRONTMATTER_KEYS = ["title:", "slug:", "description:", "date:", "hub:", "page_type:"]
MIN_H2 = 5
MIN_FAQ = 6
MIN_WORDS = 650

def count(pattern, text):
    return len(re.findall(pattern, text, flags=re.IGNORECASE | re.MULTILINE))

def words(text):
    return len(re.findall(r"\b\w+\b", text))

def main():
    failures = []

    if not os.path.isdir(ROOT):
        print("No generated pages yet. Skipping.")
        return

    for slug in os.listdir(ROOT):
        p = os.path.join(ROOT, slug, "index.md")
        if not os.path.isfile(p):
            continue
        txt = open(p, "r", encoding="utf-8").read()

        for k in REQUIRED_FRONTMATTER_KEYS:
            if k not in txt:
                failures.append((slug, f"Missing frontmatter key: {k}"))

        for b in BANNED:
            if re.search(b, txt, flags=re.IGNORECASE):
                failures.append((slug, f"Banned phrase hit: {b}"))

        h2 = count(r"^##\s+", txt)
        if h2 < MIN_H2:
            failures.append((slug, f"Too few H2 sections: {h2} (min {MIN_H2})"))

        faq = count(r"^\*\*Q:\*\*", txt)
        if faq < MIN_FAQ:
            failures.append((slug, f"Too few FAQs: {faq} (min {MIN_FAQ})"))

        if words(txt) < MIN_WORDS:
            failures.append((slug, f"Too few words: {words(txt)} (min {MIN_WORDS})"))

        # Internal links sanity: /pages/<slug>/
        if "/pages/" not in txt:
            failures.append((slug, "No internal links (/pages/<slug>/) detected"))

    if failures:
        for slug, msg in failures[:80]:
            print(f"[FAIL] {slug}: {msg}")
        print(f"\nTotal failures: {len(failures)}")
        sys.exit(1)

    print("Quality gates: PASS")

if __name__ == "__main__":
    main()
