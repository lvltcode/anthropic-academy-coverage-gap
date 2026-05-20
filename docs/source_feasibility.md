# Source Feasibility Report

**Date:** 2026-05-20
**Purpose:** Assess whether public data sources can support measuring AI product release velocity vs. learning content coverage.

---

## Source-by-Source Verdicts

### Product Release Sources

#### 1. Anthropic Claude Release Notes — USABLE

- **URL:** `https://support.claude.com/en/articles/12138966-release-notes`
- **Available data:** Dated release entries with titles and descriptions
- **Missing fields:** None critical
- **Playwright required:** No (server-rendered Intercom article)
- **Parsing difficulty:** Low — Intercom div blocks with consistent class naming
- **Reliability risk:** Low
- **Entries extracted:** 37
- **Date range:** 2024-03 to 2026-04
- **Categories found:** model release (11), agent/tooling (8), coding (6), enterprise/admin (4), other (4), pricing/billing (3), deprecation (1)

#### 2. Claude Code Changelog — USABLE

- **URL:** `https://code.claude.com/docs/en/changelog`
- **Available data:** Versioned entries with dates and bullet-point changes
- **Missing fields:** None critical
- **Playwright required:** No (MDX source with parseable `<Update>` tags)
- **Parsing difficulty:** Low — regex extraction from MDX source
- **Reliability risk:** Low
- **Entries extracted:** 292
- **Date range:** 2024-12 to 2026-05
- **Note:** All entries categorize as "coding" since they're CLI updates. Sub-item categorization possible in v2.

#### 3. Google Gemini API Changelog — USABLE

- **URL:** `https://ai.google.dev/gemini-api/docs/changelog`
- **Available data:** Dated entries with detailed descriptions of API changes
- **Missing fields:** None critical
- **Playwright required:** No (server-rendered)
- **Parsing difficulty:** Low — standard heading + bullet list structure
- **Reliability risk:** Low
- **Entries extracted:** 243
- **Date range:** 2023-12 to 2026-05
- **Categories found:** model release (159), API capability (23), deprecation (21), other (14), coding (13), multimodal (6), pricing/billing (4), agent/tooling (2), safety/policy (1)

#### 4. OpenAI Changelog — NOT USABLE

- **URL:** `https://platform.openai.com/docs/changelog`
- **Available data:** None — HTTP 403 (Forbidden)
- **Missing fields:** All
- **Playwright required:** Unknown (blocked at HTTP level)
- **Parsing difficulty:** N/A
- **Reliability risk:** High — actively blocked
- **Entries extracted:** 0
- **Note:** Returns 403 to standard requests. May require API key or authenticated session. Documented as source gap.

#### 5. OpenAI Index/Blog — NOT USABLE

- **URL:** `https://openai.com/index/`
- **Available data:** None — HTTP 403 (Forbidden)
- **Missing fields:** All
- **Playwright required:** Unknown (blocked at HTTP level)
- **Parsing difficulty:** N/A
- **Reliability risk:** High — actively blocked
- **Entries extracted:** 0
- **Note:** Also returns 403. OpenAI aggressively blocks automated access. Not viable for automated collection.

---

### Learning Content Sources

#### 6. Anthropic Academy (Skilljar) — USABLE

- **URL:** `https://anthropic.skilljar.com/`
- **Available data:** Course titles, descriptions, URLs, topic categories
- **Missing fields:** `visible_last_updated`, `visible_created_at` — **NOT publicly visible**
- **Playwright required:** No (server-rendered HTML with full course content)
- **Parsing difficulty:** Low — `a.coursebox-container` elements with `div.coursebox-text` / `div.coursebox-text-description`
- **Reliability risk:** Low
- **Entries extracted:** 18 courses
- **Date visibility:** 0/18 courses have visible update dates

#### 7. OpenAI Academy — NEEDS MANUAL REVIEW

- **URL:** `https://academy.openai.com/`
- **Available data:** Page titles/links
- **Missing fields:** `visible_last_updated`, descriptions, clean course list
- **Playwright required:** No (server-rendered)
- **Parsing difficulty:** Medium — generic parser captures navigation items mixed with actual content
- **Reliability risk:** Medium — extracted entries include nav items ("Communities", "What's new", "Small business")
- **Entries extracted:** 19 (includes non-course items)
- **Date visibility:** 0/19

#### 8. Google AI Tutorials — NEEDS MANUAL REVIEW

- **URL:** `https://ai.google.dev/gemini-api/docs/quickstart`
- **Available data:** Tutorial/doc page links
- **Missing fields:** `visible_last_updated`, clean tutorial list
- **Playwright required:** No
- **Parsing difficulty:** High — quickstart page, not a catalog; parser captures nav elements and language selectors
- **Reliability risk:** High — 122 entries mostly noise (language selectors, nav links)
- **Entries extracted:** 122 (mostly noise)
- **Date visibility:** 1/122 (false positive from page metadata)
- **Note:** Need a dedicated Google AI learning catalog URL, not the quickstart page

---

## Critical Finding: No Course Update Timestamps

**None of the three learning platforms expose course update dates publicly.**

| Platform | Update date visible? |
|----------|---------------------|
| Anthropic Academy (Skilljar) | No |
| OpenAI Academy | No |
| Google AI Dev | No |

**Decision:** The metric CANNOT be `release date → course update date` (update lag).

The honest alternative is: `release date → course coverage exists / does not exist as of collection date` (coverage gap).

---

## Summary Table

| Source | Verdict | Rows | Dates | Quality |
|--------|---------|------|-------|---------|
| Anthropic Release Notes | Usable | 37 | Exact | High |
| Claude Code Changelog | Usable | 292 | Exact | High |
| Google Gemini Changelog | Usable | 243 | Exact | High |
| OpenAI Changelog | Not usable | 0 | N/A | N/A |
| OpenAI Index | Not usable | 0 | N/A | N/A |
| Anthropic Academy | Usable | 18 | None | High |
| OpenAI Academy | Needs review | 19 | None | Low |
| Google AI Tutorials | Needs review | 122 | None | Low |

---

## Final Recommendation

### Should the full notebook proceed?

**Yes**, with scoped constraints.

### Metric

**Coverage gap** — not update lag.

> *AI product release velocity vs. public learning-content coverage as of collection date*

This is defensible, measurable, and does not require invented timestamps.

### Vendors for v1

| Vendor | Include? | Reason |
|--------|----------|--------|
| Anthropic | **Yes (primary)** | Clean release data + clean course catalog |
| Google | **Yes (secondary)** | Clean release data; learning content needs different source URL or manual curation |
| OpenAI | **No (v1 exclusion)** | Both release and learning sources blocked (403) |

### Possible v1 metrics

1. **Release count per month** — Anthropic + Google
2. **Release-to-coverage status** — does a course exist for a given topic?
3. **Uncovered major feature count** — releases with no matching content
4. **Topic category coverage** — which categories have courses vs. which don't
5. **Content decay risk by topic** — high-velocity release categories with low coverage
6. **Stale-risk score** — composite of release velocity + missing/partial coverage

### Effort estimate

- **3 days:** Anthropic-only analysis (clean data, straightforward)
- **5 days:** Anthropic + Google with manual learning content cleanup
- **7 days:** Include OpenAI workaround attempts (Playwright, manual collection)

### Risks before final notebook

1. **OpenAI exclusion** reduces the comparative story — document as known limitation
2. **Google learning content** needs a proper catalog URL or manual curation
3. **Claude Code entries all categorize as "coding"** — consider sub-item categorization in v2
4. **Topic-to-course matching** requires manual mapping logic (not just keyword overlap)
5. **Skilljar may change HTML structure** — parser is version-specific
