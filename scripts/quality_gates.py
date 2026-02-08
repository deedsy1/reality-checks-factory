import os, re, sys, shutil

ROOT = "content/pages"

AUTO_DELETE = os.getenv("AUTO_DELETE_INVALID", "0") == "1"

BANNED = [
    r"\byou should\b",
    r"\bguarantee(d)?\b",
    r"\blegal advice\b",
    r"\bmedical advice\b",
    r"\bdiagnos(e|is)\b",
    r"\bsue\b",
    r"\bprescribe\b",
]

REQUIRED_FRONTMATTER_KEYS = ["title:", "slug:", "description:", "date:", "hub:", "page_type:"]
MIN_H2 = 6
MIN_FAQ = 6

def count(pattern, text):
    return len(re.findall(pattern, text, flags=re.IGNORECASE | re.MULTILINE))

def page_failures(slug: str, txt: str):
    fails = []
    t = (txt or "").strip()

    if len(t) < 200:
        fails.append("Too short/empty")
        return fails

    if not t.startswith("---"):
        fails.append("Missing frontmatter delimiter")
        return fails

    for k in REQUIRED_FRONTMATTER_KEYS:
        if k not in t:
            fails.append(f"Missing frontmatter key: {k}")

    for b in BANNED:
        if re.search(b, t, flags=re.IGNORECASE):
            fails.append(f"Banned phrase hit: {b}")

    h2 = count(r"^##\s+", t)
    if h2 < MIN_H2:
        fails.append(f"Too few H2 sections: {h2}")

    # Flexible FAQ detection
    faq = 0
    faq += count(r"^##\s+FAQs?\b", t) * 6
    faq += count(r"\*\*Q:\*\*", t)
    faq += count(r"^\s*[-*]\s+Q:", t)

    if faq < MIN_FAQ:
        fails.append(f"Too few FAQs: {faq}")

    return fails

def main():
    failures = []

    if not os.path.isdir(ROOT):
        print("Quality gates: PASS (no pages)")
        return

    for slug in os.listdir(ROOT):
        page_dir = os.path.join(ROOT, slug)
        p = os.path.join(page_dir, "index.md")
        if not os.path.isfile(p):
            continue

        txt = open(p, "r", encoding="utf-8").read()
        fails = page_failures(slug, txt)

        if fails:
            if AUTO_DELETE:
                print(f"[DELETE] {slug}: " + "; ".join(fails[:3]))
                shutil.rmtree(page_dir, ignore_errors=True)
            else:
                for msg in fails:
                    failures.append((slug, msg))

    if failures:
        for slug, msg in failures[:80]:
            print(f"[FAIL] {slug}: {msg}")
        print(f"\nTotal failures: {len(failures)}")
        sys.exit(1)

    print("Quality gates: PASS")

if __name__ == "__main__":
    main()
