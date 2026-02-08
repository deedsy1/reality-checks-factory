# Evergreen Factory (Hugo + Cloudflare Pages)

Single-site factory template for the **"Is this normal?"** reassurance niche.

## What this repo does
- Generates a batch of new evergreen pages using Kimi (Moonshot API)
- Runs quality gates (banned phrases, required structure)
- Commits + pushes automatically (Cloudflare Pages deploys on push)

## Local run (Windows)
1) Install Hugo Extended, Python 3.11+, Git
2) Start local site:
   - `hugo server`
3) Generate pages locally (optional):
   - set `MOONSHOT_API_KEY`
   - `python scripts/generate_pages.py`
   - `python scripts/quality_gates.py`

## Deploy (Cloudflare Pages)
Connect repo using Git integration.
Build command: `hugo --minify`
Output directory: `public`

## Ads (OFF by default)
- Default: `provider: none`
- After approval, set env vars in Cloudflare Pages:
  - `ADS_PROVIDER=adsense`
  - `ADSENSE_CLIENT=ca-pub-...`

## Factory run
- Manual: GitHub Actions → Evergreen Factory → Run workflow
- Scheduled: weekly (see `.github/workflows/factory.yml`)

## Importing existing Kimi ZIP output
See `MIGRATE_FROM_KIMI_ZIP.md`.
