# Turn this repo into a Site Template (GitHub + Cloudflare)

## 1) Make the repo a GitHub Template
In GitHub:
- Repo → **Settings**
- Check **Template repository**
- Save

Now you can create a new site repo via:
- Repo page → **Use this template**

## 2) Create a new site (fast checklist)
After using the template:

### A) Edit config
- `scripts/site_config.yaml`:
  - `site.title`
  - `site.brand`
  - `site.base_url`
  - `taxonomy.hubs` (optional)

### B) Edit Hugo config
- `hugo.yaml`:
  - `title`
  - `baseURL`

### C) Replace titles
- `scripts/titles_pool.txt` (new niche prompts/titles)

### D) Reset factory state
- `scripts/manifest.json` → keep file but set to:
  - `{"used_titles": [], "generated_this_run": []}`
- Optionally delete:
  - `content/pages/*` (start clean)

### E) Cloudflare Pages
- Create new Pages project from the new repo
- Build command: `hugo --minify`
- Output dir: `public`

## 3) Optional safety mode (recommended later)
Switch your factory workflow to open PRs instead of pushing to main.
