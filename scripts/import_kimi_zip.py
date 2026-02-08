import os, sys, zipfile, re
from pathlib import Path

def slugify(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'\s+', '-', s)
    s = re.sub(r'-+', '-', s)
    return s[:90].strip('-')

def parse_frontmatter(md: str):
    # Expect YAML frontmatter between --- ... ---
    if not md.startswith('---'):
        return {}, md
    parts = md.split('---', 2)
    if len(parts) < 3:
        return {}, md
    fm = parts[1].strip()
    body = parts[2].lstrip()
    return fm, body

def main(zip_path: str):
    z = zipfile.ZipFile(zip_path)
    md_files = [n for n in z.namelist() if n.startswith('pages/') and n.endswith('.md')]
    out_root = Path('content/pages')
    out_root.mkdir(parents=True, exist_ok=True)

    imported = 0
    for name in md_files:
        md = z.read(name).decode('utf-8', errors='ignore')
        fm_raw, body = parse_frontmatter(md)
        title = None
        desc = None
        url = None
        # crude field extraction
        m = re.search(r'^title:\s*"?(.+?)"?\s*$', fm_raw, flags=re.MULTILINE)
        if m: title = m.group(1).strip().strip('"')
        m = re.search(r'^description:\s*"?(.+?)"?\s*$', fm_raw, flags=re.MULTILINE)
        if m: desc = m.group(1).strip().strip('"')
        m = re.search(r'^url:\s*"?(.+?)"?\s*$', fm_raw, flags=re.MULTILINE)
        if m: url = m.group(1).strip().strip('"')

        if not title:
            # fallback from filename
            title = Path(name).stem.replace('-', ' ').title()

        slug = slugify(title)
        page_dir = out_root / slug
        page_dir.mkdir(parents=True, exist_ok=True)

        # Build new frontmatter compatible with factory
        new_fm = [
            '---',
            f'title: "{title}"',
            f'slug: "{slug}"',
            f'description: "{desc or ""}"',
            'date: 2026-02-08',
            'hub: "social-norms"',
            'page_type: "explainer"',
        ]
        if url:
            new_fm.append(f'url: "{url}"')
        new_fm.append('---\n')

        out = '\n'.join(new_fm) + body.strip() + '\n'
        (page_dir / 'index.md').write_text(out, encoding='utf-8')
        imported += 1

    print(f"Imported {imported} pages into content/pages/<slug>/index.md")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python scripts/import_kimi_zip.py "/path/to/zip"')
        sys.exit(2)
    main(sys.argv[1])
