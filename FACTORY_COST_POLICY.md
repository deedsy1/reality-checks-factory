# Factory Cost & Safety Policy (Single-site)

## Defaults (keep these)
- PAGES_PER_RUN: 10
- Schedule: weekly
- MAX_OUTPUT_TOKENS: 1800
- TEMPERATURE: 1 (Moonshot constraint)
- KIMI_MODEL: kimi-k2.5
- No web research/browsing by default

## Hard rules
- Do not enable internet search / tool browsing for routine pages.
- Generate in batches (weekly) to avoid excessive deploys.
- Keep n=1, and avoid multi-pass rewrites unless a page fails validation.

## Auto-cleanup
- AUTO_DELETE_INVALID=1 deletes invalid generated pages in `content/pages/*` so one bad output won't block the deploy.

## When to scale
- Increase PAGES_PER_RUN only if:
  - Quality gates pass consistently
  - Indexing is healthy
  - You are not seeing repeated skip rates > 20%
