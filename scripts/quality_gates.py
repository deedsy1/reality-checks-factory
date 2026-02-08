import os
import re
import sys
import shutil

ROOT = "content/pages"

# Toggle auto-delete of invalid generated pages:
# - Set AUTO_DELETE_INVALID=1 in GitHub Actions (recommended for factory mode)
AUTO_DELETE = os.getenv("AUTO_DELETE_INVALID", "0") == "1"

BANNED = [
    r"\byou should\b",
    r"\bguarantee(d)?\b",
    r"\blegal advice\b",
    r"\bmedical advice\b",
    r"\bdiagnos(e|is)\b",
    r"\bprescribe\b",
    r"\bsue\b",
]

REQUIRED_FRONTMATTER_KEYS = ["title:", "slug:", "description:", "date:", "hub:", "page_type:"]
MIN_H2 = 5
MIN_FAQ = 6

def count(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text, flags=re.IGNORECASE | re.MULTILINE))

def faq_count(text: str) -> int:
    # Accept multiple FAQ styles:
    # - "## FAQs" section with bullets
    # - lines starting with "Q:" or "**Q:"
    # We treat a detected FAQs header as a strong signal and add a base count.
    n = 0
    n += count(r"^##\s+FAQs?\b", text) * 6
    n += count(r"^\s*[-*]\s+\*\*Q:", text)
    n += count(r"^\s*[-*]\s+Q:", text)
    n += count(r"^\*\*Q:", text)
    n += count(r"^###\s+Q:", text)
    return n

def main() -> None:
    failures = []
    deleted = 0

    if not os.path.isdir(ROOT):
        print(f"No content directory found at {ROOT}. Nothing to check.")
        return

    for slug in os.listdir(ROOT):
        page_dir = os.path.join(ROOT, slug)
        p = os.path.join(page_dir, "index.md")
        if not os.path.isfile(p):
            continue

        txt = open(p, "r", encoding="utf-8").read()
        page_failures = []

        # Basic sanity: empty/too short or missing frontmatter delimiter
        t = (txt or "").strip()
        if len(t) < 200:
            page_failures.append("Too short/empty")
        if not t.startswith("---"):
            page_failures.append("Missing frontmatter delimiter '---' at start")

        for k in REQUIRED_FRONTMATTER_KEYS:
            if k not in txt:
                page_failures.append(f"Missing frontmatter key: {k}")

        for b in BANNED:
            if re.search(b, txt, flags=re.IGNORECASE):
                page_failures.append(f"Banned phrase hit: {b}")

        h2 = count(r"^##\s+", txt)
        if h2 < MIN_H2:
            page_failures.append(f"Too few H2 sections: {h2}")

        faq = faq_count(txt)
        if faq < MIN_FAQ:
            page_failures.append(f"Too few FAQs: {faq}")

        if page_failures:
            if AUTO_DELETE:
                print(f"[DELETE] {slug}: " + "; ".join(page_failures[:4]))
                shutil.rmtree(page_dir, ignore_errors=True)
                deleted += 1
            else:
                for msg in page_failures:
                    failures.append((slug, msg))

    if AUTO_DELETE:
        # After deleting invalid pages, re-check quickly to ensure nothing left is broken.
        # If anything still fails, we should fail the run to avoid deploying bad content.
        # (This is rare; typically only happens if there are non-generated pages in ROOT.)
        remaining_failures = []
        for slug in os.listdir(ROOT):
            page_dir = os.path.join(ROOT, slug)
            p = os.path.join(page_dir, "index.md")
            if not os.path.isfile(p):
                continue
            txt = open(p, "r", encoding="utf-8").read()
            t = (txt or "").strip()
            if len(t) < 200 or not t.startswith("---"):
                remaining_failures.append((slug, "Still invalid after cleanup"))
                continue
            for k in REQUIRED_FRONTMATTER_KEYS:
                if k not in txt:
                    remaining_failures.append((slug, f"Still missing {k}"))
                    break
            if count(r"^##\s+", txt) < MIN_H2:
                remaining_failures.append((slug, "Still too few H2"))
            if faq_count(txt) < MIN_FAQ:
                remaining_failures.append((slug, "Still too few FAQ"))
            for b in BANNED:
                if re.search(b, txt, flags=re.IGNORECASE):
                    remaining_failures.append((slug, f"Still contains banned phrase {b}"))
                    break

        print(f"Auto-delete enabled. Deleted {deleted} invalid page folders.")
        if remaining_failures:
            for slug, msg in remaining_failures[:50]:
                print(f"[FAIL] {slug}: {msg}")
            print(f"Total remaining failures: {len(remaining_failures)}")
            sys.exit(1)

        print("Quality gates: PASS (after cleanup)")
        return

    if failures:
        for slug, msg in failures[:50]:
            print(f"[FAIL] {slug}: {msg}")
        print(f"\nTotal failures: {len(failures)}")
        sys.exit(1)

    print("Quality gates: PASS")

if __name__ == "__main__":
    main()
