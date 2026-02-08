# Importing an existing Kimi ZIP output

Your uploaded ZIP (`Kimi_Agent_Evergreen Site Blueprint.zip`) contains Markdown pages like:
`pages/compare/...md`, `pages/checklists/...md`, etc with YAML frontmatter including `url:`.

## Will those pages work with this Hugo repo?
Yes — Hugo supports YAML frontmatter and a `url` field for permalinks.
However, this repo expects **page bundles** under `content/pages/<slug>/index.md`
and expects `hub` + `page_type` params for hub listing.

So you have two options:

### Option A (quick): import "as-is"
- Put those `.md` files under `content/legacy/...`
- They will render, but won't show in the hub lists unless you add `hub:`.

### Option B (recommended): convert into this repo's structure
Run:
- `python scripts/import_kimi_zip.py "/path/to/Kimi_Agent_Evergreen Site Blueprint.zip"`

It will:
- extract `pages/**.md`
- create `content/pages/<slug>/index.md` bundles
- keep `title` + `description`
- convert `url:` to Hugo's `url:` if present
- add default `hub: "social-norms"` and `page_type: "explainer"` (you can adjust later)

Note: your ZIP appears to be an emergency-preparedness niche, not the reassurance niche.
So you *can* import it, but for the reassurance site you likely want to generate fresh pages with the factory prompt.
