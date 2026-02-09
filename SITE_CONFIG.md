# Per-site config system (v1)

This repo now supports a per-site config file so you can clone the factory and change only configuration.

## Files
- `scripts/site_config.yaml` (active config)
- `scripts/site_config.example.yaml` (starting point)

## How it works
`scripts/generate_pages.py` loads `scripts/site_config.yaml` (or `SITE_CONFIG` env var path) and uses it to:
- Define valid hubs and page types
- Define forbidden words
- Define the fixed H2 outline (reduces failures)
- Add a `closing_reassurance` line to the end of each page

## For a new website
1. Clone this repo
2. Edit:
   - `scripts/site_config.yaml` (brand, hubs, tone)
   - `scripts/titles_pool.txt` (new titles)
   - `hugo.yaml` (baseURL + title)
3. Deploy to a new Cloudflare Pages project

That's it.
