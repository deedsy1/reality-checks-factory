# Importing an existing Kimi ZIP bundle

If you already have a Kimi-generated ZIP with pages in `pages/.../*.md`, you can import them into Hugo page bundles.

## Run
```bash
python scripts/import_kimi_zip.py "Kimi_Output.zip"
```

This will create:
`content/pages/<slug>/index.md`

Notes:
- Existing YAML frontmatter is preserved when possible.
- If `url:` exists, Hugo will respect it as `url` in frontmatter.
- For missing fields, defaults are added (`hub`, `page_type`, `slug`).
