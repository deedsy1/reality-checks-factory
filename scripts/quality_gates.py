import os
import json
import shutil

ROOT = "content/pages"
MANIFEST_PATH = "scripts/manifest.json"

def main():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    deleted = 0
    for slug in manifest.get("generated_this_run", []):
        p = os.path.join(ROOT, slug, "index.md")
        if not os.path.isfile(p):
            continue

        txt = open(p, "r", encoding="utf-8").read()
        if not txt.startswith("---") or "## FAQs" not in txt:
            shutil.rmtree(os.path.join(ROOT, slug), ignore_errors=True)
            deleted += 1

    print(f"Quality gates complete. Deleted {deleted} pages.")

if __name__ == "__main__":
    main()
