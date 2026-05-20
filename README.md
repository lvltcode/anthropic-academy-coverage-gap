# AI Content Decay Analysis

Measuring the gap between AI product release velocity and public learning content coverage — starting with Anthropic.

This is the evidence layer for [*Anthropic Academy and the Skill Formation Gap*](https://craftmindship.com/analysis/anthropic-academy-skill-formation).

## V1 Notebook

**[Measuring the AI Learning Content Coverage Gap: A Case Study of Anthropic Academy](notebooks/01_anthropic_content_coverage_gap.ipynb)**

329 Anthropic product release entries (225 substantive, 104 maintenance) from Claude release notes and Claude Code changelog, mapped against 18 public Anthropic Academy courses. No course update timestamps were visible on any learning platform, so the metric is **topic-level coverage gap**, not update lag.

## Key Findings

- Anthropic shipped 225 substantive releases over April 2025–May 2026, with Claude Code as the dominant velocity surface.
- Of 12 release topic areas, 3 are covered by dedicated Academy courses, 1 partially covered, and 8 have no visible coverage.
- The highest-pressure uncovered topics: **permissions/security** (21 substantive releases) and **IDE integration** (14 substantive releases).
- MCP/tooling (85 substantive releases) and agentic coding (54) are well-covered by dedicated courses.

## Charts

| Chart | Description |
|-------|-------------|
| [Monthly velocity](outputs/charts/anthropic_release_velocity_monthly.png) | Release entries per month by product area |
| [Substance split](outputs/charts/anthropic_release_velocity_substance.png) | Substantive vs maintenance releases per month |
| [Topic distribution](outputs/charts/anthropic_release_topics.png) | Release count by topic subcategory |
| [Claude Code subcategories](outputs/charts/anthropic_claude_code_subcategories.png) | Claude Code changelog by subcategory |
| [Coverage gap](outputs/charts/anthropic_coverage_gap_by_topic.png) | Substantive releases vs Academy coverage by topic |

## Tables

| Table | Description |
|-------|-------------|
| [Release summary by product area](outputs/tables/release_summary_by_product_area.csv) | Total, substantive, maintenance, breaking counts |
| [Release summary by topic](outputs/tables/release_summary_by_topic.csv) | Topic-level breakdown with substance classification |
| [Release summary by substance](outputs/tables/release_summary_by_substance.csv) | Substantive vs maintenance by product area |
| [Academy course catalog](outputs/tables/academy_course_catalog_clean.csv) | All 18 Anthropic Academy courses |
| [Coverage gap summary](outputs/tables/coverage_gap_summary.csv) | Gap scores by topic |

## Limitations

- **Single vendor.** This is an Anthropic case study. OpenAI and Google were excluded due to source access issues.
- **No course update timestamps.** Metric is coverage gap, not update lag.
- **Title/description matching only.** Courses may cover topics not mentioned in visible public text.
- **Snapshot.** Data collected 2026-05-20. May be outdated.

## Next Steps

1. Multi-vendor comparison (retry OpenAI with Playwright, curate Google learning catalog)
2. Sub-item categorization for Claude Code entries
3. Temporal tracking via periodic re-collection
4. Community learning proxies (GitHub Discussions, Discord)

## Project Structure

```
notebooks/         Jupyter notebooks
  00_data_reconnaissance.ipynb     Source feasibility assessment
  01_anthropic_content_coverage_gap.ipynb   V1 analysis
scripts/           Data pipeline
  fetch_sources.py                 Fetch and cache raw HTML
  parse_release_notes.py           Extract release entries
  parse_learning_catalogs.py       Extract course catalog
  build_processed_datasets.py      Topic/substance cleanup + coverage mapping
  generate_notebook.py             Generate V1 notebook + charts
data/raw/          Cached HTML (gitignored)
data/interim/      Intermediate CSVs
data/processed/    Analysis-ready datasets
outputs/charts/    PNG charts
outputs/tables/    Summary CSV tables
docs/              Source feasibility report
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Pipeline

```bash
python scripts/fetch_sources.py
python scripts/parse_release_notes.py
python scripts/parse_learning_catalogs.py
python scripts/build_processed_datasets.py
python scripts/generate_notebook.py
```

## Part of

Portfolio series: *Anthropic Academy and the Skill Formation Gap*
