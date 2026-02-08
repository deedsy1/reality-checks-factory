# Evergreen Factory (Hugo + Cloudflare Pages)

Single-site factory template for the **"Is this normal?"** reassurance niche.

## What this repo does
- Generates a batch of new evergreen pages using Kimi (Moonshot API)
- Runs quality gates (banned phrases, required structure)
- Commits + pushes automatically (Cloudflare Pages deploys on push)

## Quick start (local)
1. Install Hugo and Python 3.11+
2. Run a local build:
   - `hugo server`
3. (Optional) Run generator locally:
   - `export MOONSHOT_API_KEY="..."`
   - `export KIMI_MODEL="..."` (optional)
   - `export PAGES_PER_RUN=5`
   - `python scripts/generate_pages.py`
   - `python scripts/quality_gates.py`
   - `hugo`

## Deploy (Cloudflare Pages)
- Connect this GitHub repo to Cloudflare Pages (Git integration).
- Build command: `hugo --minify`
- Output dir: `public`

## Ads (OFF by default)
- `params.ads.provider` is `none` by default.
- When approved, set:
  - `ADS_PROVIDER=adsense`
  - `ADSENSE_CLIENT=ca-pub-xxxxxxxxxxxx`
  (either in Cloudflare Pages env vars or GitHub Actions env)

## Factory runs
- Manual: GitHub Actions → "Evergreen Factory" → Run workflow
- Scheduled: weekly (see `.github/workflows/factory.yml`)

## Importing an existing Kimi ZIP output
See `MIGRATE_FROM_KIMI_ZIP.md`.
