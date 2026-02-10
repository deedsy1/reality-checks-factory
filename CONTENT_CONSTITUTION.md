# Content Constitution (Factory-Enforced)

This repository is an evergreen content factory. Every generated article **must** satisfy these rules, enforced by automated quality gates.

## Hard prohibitions (never allowed)

- **Dates or recency**: years (e.g., 2024), “recent”, “currently”, “today”, “this year”, “nowadays”.
- **Prices or cost claims**: currency amounts or pricing language.
- **Medical, legal, or financial advice** (including directives that function like advice).
- **Guarantees or promises**: “guarantee”, “promise”, “always works”, “will definitely”.
- **First-person language**: “I”, “we”, “our”, “my”, “us”.
- **Calls to action**: “you should”, “you must”, “do this”, “try to”, “start by”, “make sure”.
- **Affiliate / product review language**: “best”, “top 10”, “review”, “deal”, “discount”, “coupon”, “sponsored”.
- **Unneutral superiority claims**: “better than”, “most effective”, “superior”.

## Required style rules

- Neutral, **encyclopedic** tone (calm, non-judgmental).
- Beginner-friendly: define concepts before comparing them.
- No hype, no fear-based framing.
- Short paragraphs: **2–3 sentences max** per paragraph.
- Headings: **H2 / H3 only** (no H1 inside article body; no H4+).

## Structural requirements (every article)

1. **Intro paragraph** before the first H2 (what the topic is and why it exists).
2. **Definitions** section (neutral definitions of key terms).
3. **Core explanation** (how / why / differences).
4. **Clarifying examples** (non-personal, generic examples).
5. **Neutral summary** (evergreen, non-advice).
6. **FAQs** (4–6 Q&As using H3 headings).

## Internal linking rules

- Minimum **3 internal links** per article.
- Links must be contextual and descriptive (no “click here” / “here”).
- Prefer:
  - Definitions → deeper explanations
  - Comparisons → individual topic pages
  - Hub page links when relevant

## Length & depth

- Minimum **800 words**
- Ideal: **1,000–1,400 words**
- Thin content is forbidden.

## Evergreen filters

Every article must pass:

- Would this still be true in **10 years**?
- Does this avoid trends, brands, and pricing?
- Could it be understood in **any country**?

## Enforcement

- Generator instructions are designed to produce compliant output.
- `scripts/quality_gates.py` enforces:
  - outline + structure
  - forbidden patterns
  - internal links
  - heading levels
  - paragraph sentence limits
  - minimum word count

If an article fails, it must be regenerated or deleted.
