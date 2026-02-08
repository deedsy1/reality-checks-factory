import os
import json
import re
import shutil

ROOT = "content/pages"
MANIFEST_PATH = "scripts/manifest.json"

REQUIRED_KEYS = ["title:", "slug:", "description:", "date:", "hub:", "page_type:"]

def count(pattern, text):
    return len(re.findall(pattern, text, flags=re.IGNORECASE | re.MULTILINE))

def main():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    bad = 0

    for slug in manifest.get("generated_this_run", []):
        page_dir = os.path.join(ROOT, slug)
        p = os.path.join(page_dir, "index.md")
        if not os.path.isfile(p):
            continue

        txt = open(p, "r", encoding="utf-8").read()

        failed = False
        for k in REQUIRED_KEYS:
            if k not in txt:
                failed = True

        if count(r"^##\s+", txt) < 5:
            failed = True

        if "FAQ" not in txt:
            failed = True

        if re.search(r"\bdiagnos(e|is)\b", txt, re.I):
            failed = True

        if failed:
            shutil.rmtree(page_dir, ignore_errors=True)
            bad += 1
            print("[DELETE]", slug)

    print(f"Quality gates complete. Deleted {bad} pages.")

if __name__ == "__main__":
    main()
