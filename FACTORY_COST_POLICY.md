# Factory cost-control policy

**Goal:** predictable spend, minimal wasted tokens, no web research unless explicitly enabled.

## Defaults (recommended)
- Model: `kimi-k2.5`
- Temperature: `1` (API constraint observed for this model on your account)
- `PAGES_PER_RUN`: 10–15
- `MAX_OUTPUT_TOKENS`: 1800 (raise to 2200 only if needed)
- `SLEEP_SECONDS`: 0.6

## Rules
1. No web browsing by default (prompt forbids it).
2. Batch publish weekly (avoid too many builds).
3. Repair before retry:
   - If output format is invalid, run a **repair** prompt (cheaper than full regeneration).
4. Skip stubborn pages rather than fail the entire run.
5. If you increase batch size, do it slowly:
   - 10 → 15 → 20, only if quality gates pass consistently.
