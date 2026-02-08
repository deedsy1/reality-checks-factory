import os
import json
import re
import shutil

ROOT = "content/pages"
MANIFEST_PATH = "scripts/manifest.json"

REQUIRED_KEYS = ["title:", "slug:", "description:", "date:", "hub:", "page_type:"]
FIXED_HEADINGS = [
    "What this feeling usually means",
    "Common reasons",
    "What makes it worse",
    "What helps (non-advice)",
    "When it might signal a bigger issue",
    "FAQs",
]

BANNED_RE = re.compile(r"\bdiagnos(e|is)\b|\bguarantee(d)?\b|\bsue\b|\bprescribe(d)?\b", re.I)

def count(pattern, text):
    return len(re.findall(pattern, text, flags=re.IGNORECASE | re.MULTILINE))

def valid_page(txt: str) -> bool:
    if not txt.strip().startswith("---"):
        return False
    for k in REQUIRED_KEYS:
        if k not in txt:
            return False
    if BANNED_RE.search(txt):
        return False
    for h in FIXED_HEADINGS:
        if f"## {h}" not in txt:
            return False
    if count(r"\]\(/pages/[^)]+/\)", txt) < 4:
        return False
    return True

def main():
    if not os.path.exists(MANIFEST_PATH):
        print("No manifest.json found; skipping gates.")
        return

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    deleted = 0
    checked = 0
    for slug in manifest.get("generated_this_run", []):
        page_dir = os.path.join(ROOT, slug)
        p = os.path.join(page_dir, "index.md")
        if not os.path.isfile(p):
            continue

        checked += 1
        txt = open(p, "r", encoding="utf-8").read()
        if not valid_page(txt):
            shutil.rmtree(page_dir, ignore_errors=True)
            deleted += 1
            print("[DELETE]", slug)

    print(f"Quality gates: checked={checked}, deleted={deleted}")
    if deleted > 0:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
