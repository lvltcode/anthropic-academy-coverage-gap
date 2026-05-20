#!/usr/bin/env python3
"""
Generate the V1 Anthropic content coverage gap notebook.

Produces:
  notebooks/01_anthropic_content_coverage_gap.ipynb  (executable notebook)
  outputs/charts/*.png                                (pre-generated for GitHub)

The notebook contains both narrative markdown and executable code cells
that reproduce the full analysis from processed CSVs.

Run AFTER build_processed_datasets.py.
"""

import json
import textwrap
from pathlib import Path

# Pre-generate chart PNGs so they're available even without notebook execution
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED = PROJECT_ROOT / "data" / "processed"
CHARTS = PROJECT_ROOT / "outputs" / "charts"
CHARTS.mkdir(parents=True, exist_ok=True)

# ── Pre-generate chart PNGs ───────────────────────────────────────────

releases = pd.read_csv(PROCESSED / "anthropic_product_releases.csv")
releases["release_date"] = pd.to_datetime(releases["release_date"])
releases["release_month"] = releases["release_date"].dt.to_period("M")
courses = pd.read_csv(PROCESSED / "anthropic_learning_content.csv")
gap_summary = pd.read_csv(PROCESSED / "coverage_gap_summary.csv")
mapping = pd.read_csv(PROCESSED / "topic_coverage_mapping_reviewed.csv")
source_status = pd.read_csv(PROJECT_ROOT / "data" / "interim" / "source_status.csv")

# Computed values for summary text
total_releases = len(releases)
substantive = int((releases["release_substance"] == "substantive").sum())
maintenance = total_releases - substantive
total_courses = len(courses)
date_min = releases["release_date"].min().strftime("%B %Y")
date_max = releases["release_date"].max().strftime("%B %Y")

claude_subst = int(((releases["product_area"] == "Claude") &
                (releases["release_substance"] == "substantive")).sum())
claude_maint = int(((releases["product_area"] == "Claude") &
                (releases["release_substance"] == "maintenance")).sum())
cc_subst = int(((releases["product_area"] == "Claude Code") &
            (releases["release_substance"] == "substantive")).sum())
cc_maint = int(((releases["product_area"] == "Claude Code") &
            (releases["release_substance"] == "maintenance")).sum())

covered_count = int((gap_summary["coverage_status"] == "covered").sum())
partial_count = int((gap_summary["coverage_status"] == "partial").sum())
not_visible_count = int((gap_summary["coverage_status"] == "not visible").sum())

top_gaps = gap_summary.copy()
top_gaps["_s"] = pd.to_numeric(top_gaps["gap_score"], errors="coerce").fillna(-1)
top_gaps = top_gaps[top_gaps["_s"] > 0].sort_values("_s", ascending=False)

COLORS = {
    "Claude": "#D97706",
    "Claude Code": "#2563EB",
    "substantive": "#2563EB",
    "maintenance": "#94A3B8",
    "covered": "#16A34A",
    "partial": "#EAB308",
    "not visible": "#DC2626",
}


def style_ax(ax, title, xlabel, ylabel, source_note=None):
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if source_note:
        ax.annotate(source_note, xy=(0, -0.15), xycoords="axes fraction",
                    fontsize=7, color="#6B7280", style="italic")


def gen_chart_velocity():
    monthly = releases.groupby(["release_month", "product_area"]).size().unstack(fill_value=0)
    monthly.index = monthly.index.astype(str)
    fig, ax = plt.subplots(figsize=(12, 5))
    x = range(len(monthly))
    w = 0.4
    cv = monthly.get("Claude", pd.Series(0, index=monthly.index)).values
    ccv = monthly.get("Claude Code", pd.Series(0, index=monthly.index)).values
    ax.bar([i - w/2 for i in x], cv, w, label="Claude", color=COLORS["Claude"], zorder=3)
    ax.bar([i + w/2 for i in x], ccv, w, label="Claude Code", color=COLORS["Claude Code"], zorder=3)
    ax.set_xticks(list(x))
    ax.set_xticklabels(monthly.index, rotation=45, ha="right", fontsize=8)
    for i, lb in enumerate(ax.get_xticklabels()):
        if i % 2 != 0:
            lb.set_visible(False)
    ax.legend(loc="upper left", frameon=False)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.grid(axis="y", alpha=0.3, zorder=0)
    style_ax(ax, "Anthropic Product Release Velocity by Month", "Month", "Release entries",
             f"Source: support.claude.com, code.claude.com · {date_min}–{date_max}")
    plt.tight_layout()
    fig.savefig(CHARTS / "anthropic_release_velocity_monthly.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def gen_chart_substance():
    releases["substance_label"] = releases["release_substance"].map(
        {"substantive": "Substantive", "maintenance": "Maintenance"})
    monthly = releases.groupby(["release_month", "substance_label"]).size().unstack(fill_value=0)
    monthly.index = monthly.index.astype(str)
    fig, ax = plt.subplots(figsize=(12, 5))
    x = range(len(monthly))
    w = 0.4
    sv = monthly.get("Substantive", pd.Series(0, index=monthly.index)).values
    mv = monthly.get("Maintenance", pd.Series(0, index=monthly.index)).values
    ax.bar([i - w/2 for i in x], sv, w, label="Substantive", color=COLORS["substantive"], zorder=3)
    ax.bar([i + w/2 for i in x], mv, w, label="Maintenance", color=COLORS["maintenance"], zorder=3)
    ax.set_xticks(list(x))
    ax.set_xticklabels(monthly.index, rotation=45, ha="right", fontsize=8)
    for i, lb in enumerate(ax.get_xticklabels()):
        if i % 2 != 0:
            lb.set_visible(False)
    ax.legend(loc="upper left", frameon=False)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.grid(axis="y", alpha=0.3, zorder=0)
    style_ax(ax, "Anthropic Releases: Substantive vs Maintenance", "Month", "Release entries",
             "Substantive = user-visible capability/behavior change · Maintenance = bug fix, docs, minor patch")
    plt.tight_layout()
    fig.savefig(CHARTS / "anthropic_release_velocity_substance.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def gen_chart_topics():
    tc = releases.groupby("topic_subcategory").size().sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ["#2563EB" if tc[t] > 10 else "#94A3B8" for t in tc.index]
    tc.plot(kind="barh", ax=ax, color=colors, zorder=3)
    ax.grid(axis="x", alpha=0.3, zorder=0)
    style_ax(ax, "Anthropic Release Count by Topic", "Number of release entries", "",
             f"Across Claude and Claude Code · {date_min}–{date_max}")
    plt.tight_layout()
    fig.savefig(CHARTS / "anthropic_release_topics.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def gen_chart_cc_subcats():
    cc = releases[releases["product_area"] == "Claude Code"]
    sc = cc.groupby("topic_subcategory").size().sort_values(ascending=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    sc.plot(kind="barh", ax=ax, color="#2563EB", zorder=3)
    ax.grid(axis="x", alpha=0.3, zorder=0)
    style_ax(ax, "Claude Code: Release Count by Subcategory", "Number of changelog entries", "",
             f"Source: code.claude.com changelog · {date_min}–{date_max}")
    plt.tight_layout()
    fig.savefig(CHARTS / "anthropic_claude_code_subcategories.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def gen_chart_gap():
    df = gap_summary.copy()
    df["gap_score_num"] = pd.to_numeric(df["gap_score"], errors="coerce").fillna(0)
    df = df[df["substantive_releases"] > 0].copy()
    df = df.sort_values("gap_score_num", ascending=True)
    fig, ax = plt.subplots(figsize=(10, 6))
    bar_colors = [COLORS.get(s, "#94A3B8") for s in df["coverage_status"]]
    ax.barh(df["topic_subcategory"], df["substantive_releases"], color=bar_colors, zorder=3, alpha=0.85)
    for i, (_, row) in enumerate(df.iterrows()):
        status = row["coverage_status"]
        label = status.upper()
        color = COLORS.get(status, "#6B7280")
        ax.text(row["substantive_releases"] + 0.5, i, label, va="center", fontsize=7, color=color, fontweight="bold")
    ax.grid(axis="x", alpha=0.3, zorder=0)
    style_ax(ax, "Coverage Gap: Substantive Releases vs Academy Coverage",
             "Substantive release entries", "",
             f"Green = covered · Yellow = partial · Red = not visibly covered · As of {date_max}")
    ax.set_xlim(right=ax.get_xlim()[1] * 1.25)
    plt.tight_layout()
    fig.savefig(CHARTS / "anthropic_coverage_gap_by_topic.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


print("Generating chart PNGs...")
gen_chart_velocity()
gen_chart_substance()
gen_chart_topics()
gen_chart_cc_subcats()
gen_chart_gap()
print("All charts saved.")

# ── Build notebook ────────────────────────────────────────────────────

# Build course-to-topic lookup for section 8
course_topics = {}
for _, m in mapping.iterrows():
    courses_str = str(m["related_academy_courses"]) if pd.notna(m["related_academy_courses"]) else ""
    for c in courses_str.split("; "):
        c = c.strip()
        if c and c != "nan":
            course_topics.setdefault(c, set()).add(m["topic_subcategory"])

course_table_lines = [
    "| # | Course | Description | Assigned Topics |",
    "|---|--------|-------------|-----------------|",
]
for i, (_, c) in enumerate(courses.iterrows(), 1):
    title = c["title"]
    desc = str(c["description"])[:120].replace("|", "\\|")
    topics = ", ".join(sorted(course_topics.get(title, {"—"})))
    course_table_lines.append(f"| {i} | {title} | {desc} | {topics} |")
course_table = "\n".join(course_table_lines)

# Source status table
src_table_lines = [
    "| Source | Vendor | Type | Status | HTTP |",
    "|--------|--------|------|--------|------|",
]
for _, s in source_status.iterrows():
    src_table_lines.append(
        f"| {s['source_id']} | {s['vendor']} | {s['source_type']} | {s['fetch_status']} | {s['http_status']} |"
    )
src_table = "\n".join(src_table_lines)


def md(source: str) -> dict:
    lines = textwrap.dedent(source).strip().split("\n")
    return {"cell_type": "markdown", "metadata": {},
            "source": [l + "\n" for l in lines[:-1]] + [lines[-1]]}


def code(source: str) -> dict:
    lines = textwrap.dedent(source).strip().split("\n")
    return {"cell_type": "code", "execution_count": None, "metadata": {},
            "outputs": [],
            "source": [l + "\n" for l in lines[:-1]] + [lines[-1]]}


cells = [
    # ── Title ──
    md(f"""
    # Measuring the AI Learning Content Coverage Gap
    ## A Case Study of Anthropic Academy

    *Research notebook · Data collected 2026-05-20 · [Craftmindship analysis](https://craftmindship.com/analysis/anthropic-academy-skill-formation)*
    """),

    # ── 60-second summary ──
    md(f"""
    ## 60-Second Summary

    **Dataset:** {total_releases} Anthropic product release entries ({substantive} substantive, {maintenance} maintenance) from Claude release notes and Claude Code changelog, plus {total_courses} Anthropic Academy courses from the public Skilljar catalog.

    **Observed period:** {date_min} to {date_max}

    **Key constraint:** No public course update timestamps were visible on any learning platform examined (Anthropic Academy, OpenAI Academy, Google AI). This notebook uses **topic-level coverage gap** as the metric, not update lag.

    **Headline findings:**

    1. Anthropic shipped {substantive} substantive releases over the observed period — {cc_subst} from Claude Code alone.
    2. Claude Code is a high-velocity surface: {len(releases[releases['product_area'] == 'Claude Code'])} changelog entries across 12 topic subcategories.
    3. Of 12 topic areas, {covered_count} are visibly covered by dedicated Academy courses, {partial_count} partially covered, and {not_visible_count} have no visible coverage.
    4. The highest-pressure uncovered topics are **permissions/security** ({int(top_gaps.iloc[0]['substantive_releases'])} substantive releases) and **IDE integration** ({int(top_gaps.iloc[1]['substantive_releases'])} substantive releases).

    **Limitation:** This is a single-vendor case study of Anthropic. It is not a cross-vendor benchmark. OpenAI and Google data sources were attempted in reconnaissance but encountered access restrictions or quality issues.
    """),

    # ── Why this notebook exists ──
    md("""
    ## Why This Notebook Exists

    AI products ship faster than course catalogs can track. But "faster" is a feeling — this notebook puts numbers on it.

    The goal is narrow: measure what is publicly visible about the gap between Anthropic's product release velocity and Anthropic Academy's public course coverage, using only publicly available data.

    This is the evidence layer for the Craftmindship article [*Anthropic Academy and the Skill Formation Gap*](https://craftmindship.com/analysis/anthropic-academy-skill-formation).
    """),

    # ── Setup code cell ──
    code("""
    import pandas as pd
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    from pathlib import Path

    PROCESSED = Path('../data/processed')
    CHARTS = Path('../outputs/charts')
    CHARTS.mkdir(parents=True, exist_ok=True)

    # Chart style
    COLORS = {
        "Claude": "#D97706", "Claude Code": "#2563EB",
        "substantive": "#2563EB", "maintenance": "#94A3B8",
        "covered": "#16A34A", "partial": "#EAB308", "not visible": "#DC2626",
    }

    def style_ax(ax, title, xlabel, ylabel, note=None):
        ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
        ax.set_xlabel(xlabel, fontsize=10)
        ax.set_ylabel(ylabel, fontsize=10)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        if note:
            ax.annotate(note, xy=(0, -0.15), xycoords="axes fraction",
                        fontsize=7, color="#6B7280", style="italic")
    """),

    # ── Data sources ──
    md(f"""
    ## Data Sources and Feasibility Recap

    Data collected 2026-05-20. A prior reconnaissance phase ([00_data_reconnaissance.ipynb](00_data_reconnaissance.ipynb)) assessed all sources.

    {src_table}

    **Key decisions:**
    - **Anthropic (primary):** Clean release data + clean course catalog → included in V1
    - **OpenAI (excluded):** Changelog and index return HTTP 403
    - **Google (excluded from V1):** Release data is clean, learning content source needs manual curation
    """),

    # ── Why coverage gap ──
    md("""
    ## Why the Metric Is Coverage Gap, Not Update Lag

    The natural metric would be: *days from product release to course update*. This requires two timestamps:
    1. Product release date (available)
    2. Course update date (**not available**)

    **No learning platform examined exposes course update timestamps publicly.**

    | Platform | Update date visible? |
    |----------|---------------------|
    | Anthropic Academy (Skilljar) | No |
    | OpenAI Academy | No |
    | Google AI Dev | No |

    The defensible alternative: **topic-level coverage gap as of the collection date.**
    """),

    # ── Load data ──
    code("""
    # Load processed datasets
    releases = pd.read_csv(PROCESSED / 'anthropic_product_releases.csv')
    releases['release_date'] = pd.to_datetime(releases['release_date'])
    releases['release_month'] = releases['release_date'].dt.to_period('M')

    courses = pd.read_csv(PROCESSED / 'anthropic_learning_content.csv')
    gap_summary = pd.read_csv(PROCESSED / 'coverage_gap_summary.csv')
    mapping = pd.read_csv(PROCESSED / 'topic_coverage_mapping_reviewed.csv')

    print(f"Releases: {len(releases)} ({(releases['release_substance']=='substantive').sum()} substantive, "
          f"{(releases['release_substance']=='maintenance').sum()} maintenance)")
    print(f"Academy courses: {len(courses)}")
    print(f"Date range: {releases['release_date'].min().date()} to {releases['release_date'].max().date()}")
    """),

    # ── Release velocity section ──
    md("""
    ## Anthropic Product Release Velocity

    ### Overall monthly velocity
    """),

    code("""
    # Release counts by product area
    area_summary = releases.groupby('product_area').agg(
        total=('title', 'size'),
        substantive=('release_substance', lambda x: (x == 'substantive').sum()),
        maintenance=('release_substance', lambda x: (x == 'maintenance').sum()),
    )
    area_summary
    """),

    code("""
    # Chart 1: Monthly release velocity by product area
    monthly = releases.groupby(['release_month', 'product_area']).size().unstack(fill_value=0)
    monthly.index = monthly.index.astype(str)

    fig, ax = plt.subplots(figsize=(12, 5))
    x = range(len(monthly))
    w = 0.4
    ax.bar([i - w/2 for i in x], monthly.get('Claude', 0).values, w,
           label='Claude', color=COLORS['Claude'], zorder=3)
    ax.bar([i + w/2 for i in x], monthly.get('Claude Code', 0).values, w,
           label='Claude Code', color=COLORS['Claude Code'], zorder=3)
    ax.set_xticks(list(x))
    ax.set_xticklabels(monthly.index, rotation=45, ha='right', fontsize=8)
    for i, lb in enumerate(ax.get_xticklabels()):
        if i % 2 != 0: lb.set_visible(False)
    ax.legend(loc='upper left', frameon=False)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.grid(axis='y', alpha=0.3, zorder=0)
    style_ax(ax, 'Anthropic Product Release Velocity by Month', 'Month', 'Release entries',
             'Source: support.claude.com, code.claude.com')
    plt.tight_layout()
    plt.savefig(CHARTS / 'anthropic_release_velocity_monthly.png', dpi=150, bbox_inches='tight')
    plt.show()
    """),

    md("""
    ### Substantive vs maintenance split

    Not all releases create learning-content decay pressure. Bug fixes and docs-only patches do not require course updates.
    """),

    code("""
    # Chart 2: Monthly velocity by substance
    releases['substance_label'] = releases['release_substance'].map(
        {'substantive': 'Substantive', 'maintenance': 'Maintenance'})
    monthly_s = releases.groupby(['release_month', 'substance_label']).size().unstack(fill_value=0)
    monthly_s.index = monthly_s.index.astype(str)

    fig, ax = plt.subplots(figsize=(12, 5))
    x = range(len(monthly_s))
    w = 0.4
    ax.bar([i - w/2 for i in x], monthly_s.get('Substantive', 0).values, w,
           label='Substantive', color=COLORS['substantive'], zorder=3)
    ax.bar([i + w/2 for i in x], monthly_s.get('Maintenance', 0).values, w,
           label='Maintenance', color=COLORS['maintenance'], zorder=3)
    ax.set_xticks(list(x))
    ax.set_xticklabels(monthly_s.index, rotation=45, ha='right', fontsize=8)
    for i, lb in enumerate(ax.get_xticklabels()):
        if i % 2 != 0: lb.set_visible(False)
    ax.legend(loc='upper left', frameon=False)
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    ax.grid(axis='y', alpha=0.3, zorder=0)
    style_ax(ax, 'Anthropic Releases: Substantive vs Maintenance', 'Month', 'Release entries',
             'Substantive = user-visible capability change · Maintenance = bug fix, docs, minor patch')
    plt.tight_layout()
    plt.savefig(CHARTS / 'anthropic_release_velocity_substance.png', dpi=150, bbox_inches='tight')
    plt.show()
    """),

    md(f"""
    **{substantive}** of {total_releases} releases ({substantive/total_releases:.0%}) are classified as substantive — meaning they introduce a user-visible capability or behavior change.

    Classification rule: "substantive" if it adds a new feature, changes API behavior, introduces a new model, modifies permissions, or deprecates functionality. Bug fixes, doc updates, and minor patches are "maintenance." Entries where fix-related signals dominate the description are classified as maintenance even if topic keywords are present.
    """),

    # ── Topic mix ──
    md("## Release Topic Mix"),

    code("""
    # Chart 3: Release count by topic
    tc = releases.groupby('topic_subcategory').size().sort_values(ascending=True)

    fig, ax = plt.subplots(figsize=(10, 6))
    colors = ['#2563EB' if tc[t] > 10 else '#94A3B8' for t in tc.index]
    tc.plot(kind='barh', ax=ax, color=colors, zorder=3)
    ax.grid(axis='x', alpha=0.3, zorder=0)
    style_ax(ax, 'Anthropic Release Count by Topic', 'Number of release entries', '',
             'Across Claude and Claude Code')
    plt.tight_layout()
    plt.savefig(CHARTS / 'anthropic_release_topics.png', dpi=150, bbox_inches='tight')
    plt.show()
    """),

    code("""
    # Chart 4: Claude Code subcategories
    cc = releases[releases['product_area'] == 'Claude Code']
    sc = cc.groupby('topic_subcategory').size().sort_values(ascending=True)

    fig, ax = plt.subplots(figsize=(10, 5))
    sc.plot(kind='barh', ax=ax, color='#2563EB', zorder=3)
    ax.grid(axis='x', alpha=0.3, zorder=0)
    style_ax(ax, 'Claude Code: Release Count by Subcategory', 'Changelog entries', '',
             'Source: code.claude.com changelog')
    plt.tight_layout()
    plt.savefig(CHARTS / 'anthropic_claude_code_subcategories.png', dpi=150, bbox_inches='tight')
    plt.show()
    """),

    # ── Course catalog ──
    md(f"""
    ## Anthropic Academy Course Catalog

    Anthropic Academy lists **{total_courses} public courses** on its Skilljar catalog. No course update timestamps are publicly visible.

    {course_table}
    """),

    code("""
    # Full course catalog with first 150 chars of description
    course_display = courses[['title', 'description', 'url', 'topic_category']].copy()
    course_display['description'] = course_display['description'].str[:150]
    course_display
    """),

    # ── Coverage mapping ──
    md("""
    ## Topic-to-Course Coverage Mapping

    Each topic was matched against Academy courses using strict rules:
    - **Covered:** Course title or description explicitly mentions the topic or feature name.
    - **Partial:** Thematic overlap exists but no dedicated course for the topic.
    - **Not visible:** No course title or description visibly mentions the topic.

    Only public text from course titles and descriptions was used. Matching evidence is in `data/processed/topic_coverage_mapping_reviewed.csv`.
    """),

    code("""
    # Coverage mapping summary
    mapping_display = mapping[['topic_subcategory', 'release_count', 'substantive_release_count',
                                'coverage_status', 'coverage_confidence', 'related_academy_courses',
                                'needs_human_review']].copy()
    mapping_display['related_academy_courses'] = mapping_display['related_academy_courses'].fillna('').str[:60]
    mapping_display.sort_values('substantive_release_count', ascending=False)
    """),

    # ── Coverage gap findings ──
    md("## Coverage Gap Findings"),

    code("""
    # Chart 5: Coverage gap by topic
    df = gap_summary.copy()
    df['gap_score_num'] = pd.to_numeric(df['gap_score'], errors='coerce').fillna(0)
    df = df[df['substantive_releases'] > 0].sort_values('gap_score_num', ascending=True)

    fig, ax = plt.subplots(figsize=(10, 6))
    bar_colors = [COLORS.get(s, '#94A3B8') for s in df['coverage_status']]
    ax.barh(df['topic_subcategory'], df['substantive_releases'], color=bar_colors, zorder=3, alpha=0.85)
    for i, (_, row) in enumerate(df.iterrows()):
        status = row['coverage_status']
        color = COLORS.get(status, '#6B7280')
        ax.text(row['substantive_releases'] + 0.5, i, status.upper(),
                va='center', fontsize=7, color=color, fontweight='bold')
    ax.grid(axis='x', alpha=0.3, zorder=0)
    style_ax(ax, 'Coverage Gap: Substantive Releases vs Academy Coverage',
             'Substantive release entries', '',
             'Green = covered · Yellow = partial · Red = not visibly covered')
    ax.set_xlim(right=ax.get_xlim()[1] * 1.25)
    plt.tight_layout()
    plt.savefig(CHARTS / 'anthropic_coverage_gap_by_topic.png', dpi=150, bbox_inches='tight')
    plt.show()
    """),

    code("""
    # Gap score calculation: not visible = substantive_releases, partial = half, covered = 0
    gap_display = gap_summary[['topic_subcategory', 'total_releases', 'substantive_releases',
                                'breaking_changes', 'courses_covering_count',
                                'coverage_status', 'gap_score']].copy()
    gap_display = gap_display.sort_values('gap_score', ascending=False,
                                          key=lambda x: pd.to_numeric(x, errors='coerce').fillna(-1))
    gap_display
    """),

    md(f"""
    ### Key observations

    1. **MCP/tooling** ({int(gap_summary[gap_summary['topic_subcategory']=='MCP/tooling']['substantive_releases'].values[0])} substantive releases) and **agentic coding** ({int(gap_summary[gap_summary['topic_subcategory']=='agentic coding']['substantive_releases'].values[0])}) are the highest-velocity areas and are **covered** by dedicated courses.

    2. **Permissions/security** ({int(top_gaps.iloc[0]['substantive_releases'])} substantive releases) is the largest **uncovered** topic — no Academy course visibly addresses permissions, security, or access control in Claude Code.

    3. **IDE integration** ({int(top_gaps.iloc[1]['substantive_releases'])} substantive releases) and **enterprise/admin** ({int(top_gaps.iloc[2]['substantive_releases'])}) are also uncovered.

    4. **Model support** ({int(gap_summary[gap_summary['topic_subcategory']=='model support']['substantive_releases'].values[0])} substantive releases) is **partially** covered — "Building with the Claude API" mentions models but no course is dedicated to model selection or capabilities.

    5. Bug fix and other maintenance topics correctly show gap_score = 0.
    """),

    # ── What this proves ──
    md("""
    ## What This Proves and Does Not Prove

    | This notebook supports | This notebook does NOT support |
    |----------------------|-------------------------------|
    | Anthropic public product surfaces changed frequently over the observed period | Any claim about Anthropic's internal education efforts |
    | Claude Code creates a high-velocity learning surface | Any claim that Anthropic Academy is "bad" or "neglected" |
    | Some fast-moving topics are not visibly covered in the public Academy catalog | Any claim about course quality or depth |
    | Course update timestamps are not publicly visible | Exact content decay days or update lag |
    | Topic-level coverage gap is a defensible V1 metric | Any comparative claim across AI vendors |
    | The release velocity should be interpreted carefully (substantive vs maintenance) | Any claim about internal automation or investment |
    """),

    # ── Implications ──
    md("""
    ## Implications for Living Learning Infrastructure

    If the coverage gap pattern holds — and this V1 can only measure one vendor's public surface — it suggests:

    1. **Release velocity outpaces static catalogs.** Even with 18 courses, fast-moving technical subcategories (permissions, IDE, enterprise admin) are not visibly covered.
    2. **The substance split matters.** Raw release counts overstate the learning load. Filtering to substantive releases gives a more honest picture.
    3. **Coverage ≠ currency.** Without update timestamps, we cannot distinguish "covered and current" from "covered but stale."
    4. **Living learning infrastructure** — continuously updated content tied to release pipelines — may be more appropriate than periodic course releases for high-velocity product surfaces.

    These are directional observations from a single vendor's public surface, not general conclusions about AI education infrastructure.
    """),

    # ── Limitations ──
    md("""
    ## Limitations

    1. **Single vendor.** Anthropic-only case study. OpenAI and Google excluded due to source access/quality issues.
    2. **No course update timestamps.** Metric is coverage gap, not update lag.
    3. **Title/description matching only.** Courses may cover topics not in their visible public text.
    4. **Keyword-based topic classification.** Substance audit showed ~7% false-positive rate (substantive entries that should be maintenance).
    5. **Claude Code changelog volume.** Each entry may represent varying levels of user-facing change.
    6. **No enrollment or completion data.** We measure catalog presence, not learning effectiveness.
    7. **Snapshot in time.** Data collected 2026-05-20.
    """),

    # ── Next steps ──
    md("""
    ## Next Research Steps

    1. **Multi-vendor comparison.** Retry OpenAI with Playwright or manual methods.
    2. **Sub-item categorization.** Classify Claude Code at the bullet-point level.
    3. **Temporal tracking.** Re-run periodically to detect catalog changes.
    4. **Course content depth.** Enrolled-user assessment of whether content covers specific features.
    5. **Community learning proxy.** Stack Overflow, GitHub Discussions, or Discord as informal coverage signals.

    ---

    *Notebook generated 2026-05-20 · Source: [github.com/.../ai-content-decay-analysis](https://github.com/)*
    """),
]

notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.10.4"},
    },
    "nbformat": 4,
    "nbformat_minor": 4,
}

nb_path = PROJECT_ROOT / "notebooks" / "01_anthropic_content_coverage_gap.ipynb"
with open(nb_path, "w", encoding="utf-8") as f:
    json.dump(notebook, f, indent=1, ensure_ascii=False)

md_count = sum(1 for c in cells if c["cell_type"] == "markdown")
code_count = sum(1 for c in cells if c["cell_type"] == "code")
print(f"\nNotebook saved: {nb_path}")
print(f"  Markdown cells: {md_count}")
print(f"  Code cells: {code_count}")
print(f"  Total cells: {len(cells)}")
