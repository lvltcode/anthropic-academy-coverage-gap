#!/usr/bin/env python3
"""
Build processed Anthropic-only datasets for V1 notebook.

Reads:  data/interim/product_releases.csv, data/interim/learning_content.csv
Writes: data/processed/anthropic_product_releases.csv
        data/processed/anthropic_learning_content.csv
        data/processed/anthropic_release_summary_by_month.csv
        data/processed/anthropic_release_summary_by_topic.csv
        data/processed/topic_coverage_mapping_draft.csv
        data/processed/topic_coverage_mapping_reviewed.csv
        data/processed/coverage_gap_summary.csv
        outputs/tables/release_summary_by_product_area.csv
        outputs/tables/release_summary_by_topic.csv
        outputs/tables/release_summary_by_substance.csv
        outputs/tables/academy_course_catalog_clean.csv
        outputs/tables/coverage_gap_summary.csv
"""

import csv
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INTERIM = PROJECT_ROOT / "data" / "interim"
PROCESSED = PROJECT_ROOT / "data" / "processed"
TABLES = PROJECT_ROOT / "outputs" / "tables"

PROCESSED.mkdir(parents=True, exist_ok=True)
TABLES.mkdir(parents=True, exist_ok=True)


# ── Subcategory classification (Claude Code) ─────────────────────────

SUBCATEGORY_RULES: list[tuple[str, list[str]]] = [
    ("MCP/tooling",          ["mcp", "model context protocol", "tool server",
                              "tool use", "tool_use", "plugin", "lsp",
                              "web search", "search the web"]),
    ("agentic coding",       ["agent", "subagent", "sub-agent", "dispatch",
                              "background session", "autonomous", "worktree",
                              "orchestrat", "multi-agent", "session",
                              "skill", "remote control"]),
    ("IDE integration",      ["vscode", "vs code", "jetbrains", "intellij",
                              "ide ", "editor", "extension"]),
    ("permissions/security", ["permission", "security", "auth", "rbac",
                              "access control", "sandbox", "trust",
                              "allowlist", "blocklist", "disallowedtools"]),
    ("enterprise/admin",     ["enterprise", "admin", "team", "organization",
                              "sso", "workspace", "billing", "license",
                              "usage limit", "opentelemetry", "otel"]),
    ("model support",        ["model", "opus", "sonnet", "haiku", "claude 3",
                              "claude 4", "context window", "token",
                              "thinking", "extended thinking"]),
    ("deprecation",          ["deprecat", "sunset", "end of support",
                              "removed", "migration"]),
    ("docs/tutorial",        ["documentation", "tutorial", "guide",
                              "readme", "changelog", "help text"]),
    ("bug fix",              ["fix", "fixed", "bug", "crash", "regression",
                              "hotfix", "patch", "resolve", "resolved",
                              "internal fixes"]),
    ("cli workflow",         ["cli", "command", "terminal", "shell", "prompt",
                              "config", "hook", "flag", "argument",
                              "slash command", "keyboard", "shortcut",
                              "status line", "compact mode", "theme",
                              "output", "streaming", "diff", "git",
                              "resume", "continue", "cursor", "cjk",
                              "logging", "spinner", "render",
                              "claude.md", "@-mention",
                              "init", "install"]),
]


def classify_subcategory(title: str, description: str) -> str:
    """Classify a Claude Code entry into a topic_subcategory."""
    combined = f"{title} {description}".lower()
    for subcat, keywords in SUBCATEGORY_RULES:
        if any(kw in combined for kw in keywords):
            return subcat
    return "other"


# ── Substance classification ──────────────────────────────────────────

MAINTENANCE_SIGNALS = [
    "fix", "fixed", "bug", "crash", "regression", "hotfix", "patch",
    "typo", "docs only", "internal fixes", "cleanup", "refactor",
    "resolve", "resolved", "stability", "minor",
]

SUBSTANTIVE_SIGNALS = [
    "added", "new ", "launch", "support for", "released", "introduced",
    "enabled", "now available", "generally available", "preview",
    "breaking", "deprecat", "sunset", "removed", "migration",
    "model", "opus", "sonnet", "haiku", "multimodal", "vision",
    "agent", "mcp", "tool use", "enterprise", "sso", "permission",
    "api", "endpoint", "streaming", "embed", "context window",
]


def classify_substance(title: str, description: str, topic_cat: str,
                       subcat: str, is_breaking: bool) -> str:
    """Classify as substantive or maintenance."""
    # Hard rules from consistency constraints
    if subcat == "bug fix":
        return "maintenance"
    if subcat == "docs/tutorial":
        return "maintenance"
    if subcat == "deprecation":
        return "substantive"
    if is_breaking:
        return "substantive"

    combined = f"{title} {description}".lower()

    # Score-based classification
    maint_score = sum(1 for s in MAINTENANCE_SIGNALS if s in combined)
    subst_score = sum(1 for s in SUBSTANTIVE_SIGNALS if s in combined)

    # Fix-dominated entries: if fixes far outnumber additions, classify as
    # maintenance even if topic keywords are present.  This catches changelog
    # versions that are purely bug-fix rounds.
    fix_count = combined.count("fix")
    add_count = combined.count("added") + combined.count("new ")
    if fix_count >= 3 and add_count <= 1:
        return "maintenance"
    if fix_count >= 2 and add_count == 0 and subst_score <= maint_score:
        return "maintenance"

    # If description is very short (< 30 chars), likely maintenance
    if len(description.strip()) < 30 and subst_score == 0:
        return "maintenance"

    if subst_score > maint_score:
        return "substantive"
    if maint_score > 0 and subst_score == 0:
        return "maintenance"

    # Default: if topic suggests capability, lean substantive
    if topic_cat in ("model release", "agent/tooling", "API capability",
                     "multimodal", "enterprise/admin"):
        return "substantive"

    return "maintenance"


# ── Breaking change detection ─────────────────────────────────────────

BREAKING_KEYWORDS = [
    "breaking change", "deprecat", "migration required", "removed support",
    "sunset", "end of support", "end-of-life", "eol",
    "no longer support", "will be removed", "api change",
]


def detect_breaking(title: str, description: str, existing_flag: str) -> bool:
    """Detect breaking changes from text signals."""
    if existing_flag and existing_flag.lower() == "true":
        return True
    combined = f"{title} {description}".lower()
    return any(kw in combined for kw in BREAKING_KEYWORDS)


# ── Claude (non-Code) subcategory ─────────────────────────────────────

CLAUDE_SUBCAT_RULES: list[tuple[str, list[str]]] = [
    ("multimodal",           ["chart", "diagram", "visualization", "image",
                              "vision", "audio", "video"]),
    ("agentic coding",       ["cowork", "agent", "computer use", "dispatch",
                              "tool", "plugin", "mcp"]),
    ("model support",        ["opus", "sonnet", "haiku", "model", "claude 3",
                              "claude 4", "launch"]),
    ("enterprise/admin",     ["enterprise", "team", "admin", "sso",
                              "role-based", "workspace", "organization"]),
    ("permissions/security", ["permission", "security", "trust", "safety"]),
    ("pricing/billing",      ["pricing", "price", "plan", "pro", "max",
                              "free", "credit", "billing"]),
    ("deprecation",          ["deprecat", "sunset", "removed", "migration"]),
    ("multimodal",           ["image", "vision", "audio", "video", "pdf",
                              "file", "multimodal", "interactive app"]),
    ("API capability",       ["api", "sdk", "endpoint", "streaming",
                              "batch", "function call"]),
    ("docs/tutorial",        ["documentation", "tutorial", "guide"]),
    ("cli workflow",         ["cli", "terminal", "command"]),
]


def classify_claude_subcategory(title: str, description: str) -> str:
    combined = f"{title} {description}".lower()
    for subcat, keywords in CLAUDE_SUBCAT_RULES:
        if any(kw in combined for kw in keywords):
            return subcat
    return "other"


# ── Topic-to-course coverage mapping ──────────────────────────────────

def build_coverage_mapping(releases_df: pd.DataFrame,
                           courses_df: pd.DataFrame) -> pd.DataFrame:
    """Build the topic coverage mapping grouped by topic_subcategory.

    Groups releases by subcategory (merging across product areas) for a
    readable ~14-row mapping instead of a 37-row cross-product.
    Uses strict explicit-match rules: a course must mention the topic/feature
    by name in its title or description to count.
    """

    # Group by subcategory, aggregate across product areas
    groups = releases_df.groupby("topic_subcategory")

    mapping_rows = []
    for subcat, group in groups:
        total = len(group)
        substantive = int((group["release_substance"] == "substantive").sum())
        maintenance = total - substantive
        breaking = int(group["is_breaking_change"].sum())

        # Dominant topic_category for context
        dominant_cat = group["topic_category"].mode().iloc[0]

        # Representative titles (up to 5 substantive ones preferred)
        subst_titles = group[
            group["release_substance"] == "substantive"
        ]["title"].head(5).tolist()
        rep_titles = "; ".join(subst_titles) if subst_titles else "; ".join(
            group["title"].head(5).tolist()
        )

        # Match courses using strict explicit rules
        matched_courses, coverage_notes = _match_courses_strict(
            subcat, courses_df
        )

        # Determine coverage status
        if not matched_courses:
            coverage_status = "not visible"
            confidence = "high"
        else:
            # Check if any match is a dedicated/explicit course
            has_dedicated = any(n.startswith("[explicit]") for n in coverage_notes)
            if has_dedicated:
                coverage_status = "covered"
                confidence = "high"
            else:
                coverage_status = "partial"
                confidence = "medium"

        # Clean notes (remove [explicit]/[thematic] prefixes for output)
        clean_notes = [
            n.replace("[explicit] ", "").replace("[thematic] ", "")
            for n in coverage_notes
        ]

        needs_review = (
            confidence != "high"
            or coverage_status in ("partial", "unclear")
        )

        mapping_rows.append({
            "topic_category": dominant_cat,
            "topic_subcategory": subcat,
            "release_count": total,
            "substantive_release_count": substantive,
            "maintenance_release_count": maintenance,
            "representative_release_titles": rep_titles,
            "related_academy_courses": "; ".join(matched_courses),
            "coverage_status": coverage_status,
            "coverage_confidence": confidence,
            "needs_human_review": needs_review,
            "notes": "; ".join(clean_notes),
        })

    return pd.DataFrame(mapping_rows)


# Explicit course-to-topic matching rules.
# Each subcategory has:
#   "explicit": phrases that mean a course DIRECTLY covers the topic
#   "thematic": phrases that mean thematic overlap (partial coverage)
_COVERAGE_RULES: dict[str, dict[str, list[str]]] = {
    "MCP/tooling": {
        "explicit": ["model context protocol", "mcp"],
        "thematic": ["plugin", "tool server"],
    },
    "agentic coding": {
        "explicit": ["agent skill", "sub-agent", "subagent", "cowork"],
        "thematic": ["agent", "autonomous", "delegate task"],
    },
    "cli workflow": {
        "explicit": ["claude code"],
        "thematic": ["command line", "terminal", "development workflow"],
        # Note: "cli" removed from thematic — false-matches on "client" in MCP courses.
        # "claude code" in agent courses matches explicitly but those courses cover
        # agentic topics, not CLI workflow; the _match_courses_strict filter for
        # "ai fluency" does not catch this, so rely on manual audit for edge cases.
    },
    "IDE integration": {
        "explicit": ["vscode", "vs code", "jetbrains", "intellij"],
        "thematic": ["editor integration"],
    },
    "model support": {
        "explicit": ["claude api", "anthropic model", "opus", "sonnet", "haiku"],
        "thematic": ["model", "claude"],
    },
    "permissions/security": {
        "explicit": ["permission", "security", "access control", "rbac"],
        "thematic": ["trust", "safety"],
    },
    "enterprise/admin": {
        "explicit": ["enterprise", "admin", "team management", "sso",
                     "workspace", "role-based"],
        "thematic": [],
    },
    "bug fix": {
        "explicit": [],
        "thematic": [],
    },
    "deprecation": {
        "explicit": ["migration", "deprecat"],
        "thematic": [],
    },
    "docs/tutorial": {
        "explicit": [],
        "thematic": ["tutorial", "guide"],
    },
    "multimodal": {
        "explicit": ["multimodal", "vision", "image generation", "audio", "video"],
        "thematic": [],
    },
    "pricing/billing": {
        "explicit": ["pricing", "billing", "plan"],
        "thematic": [],
    },
    "API capability": {
        "explicit": ["claude api", "api", "sdk"],
        "thematic": ["endpoint"],
    },
    "other": {
        "explicit": [],
        "thematic": [],
    },
}


def _match_courses_strict(subcat: str,
                          courses_df: pd.DataFrame) -> tuple[list, list]:
    """Match courses to a subcategory using strict rules.
    Returns (matched_course_titles, notes_with_evidence).
    """
    rules = _COVERAGE_RULES.get(subcat, {"explicit": [], "thematic": []})
    matched = []
    notes = []

    for _, course in courses_df.iterrows():
        c_title = course["title"]
        c_desc = str(course.get("description", ""))
        c_text = f"{c_title} {c_desc}".lower()

        # Skip AI Fluency / general courses for technical subcategories
        if "ai fluency" in c_title.lower() and subcat not in (
            "other",
        ):
            continue

        # Check explicit match first
        for phrase in rules["explicit"]:
            if phrase in c_text:
                matched.append(c_title)
                notes.append(f"[explicit] '{c_title}' contains '{phrase}'")
                break
        else:
            # Check thematic match
            for phrase in rules["thematic"]:
                if phrase in c_text:
                    matched.append(c_title)
                    notes.append(f"[thematic] '{c_title}' contains '{phrase}'")
                    break

    return matched, notes


def build_gap_summary(mapping_df: pd.DataFrame) -> pd.DataFrame:
    """Build coverage_gap_summary.csv with gap_score calculation."""
    rows = []
    for _, m in mapping_df.iterrows():
        subst = m["substantive_release_count"]
        status = m["coverage_status"]

        if status == "not visible":
            gap_score = subst
        elif status == "partial":
            gap_score = subst / 2
        elif status == "covered":
            gap_score = 0
        else:  # unclear
            gap_score = ""

        rows.append({
            "topic_category": m["topic_category"],
            "topic_subcategory": m["topic_subcategory"],
            "total_releases": m["release_count"],
            "substantive_releases": m["substantive_release_count"],
            "breaking_changes": 0,  # will fill below
            "courses_covering_count": len(
                [c for c in m["related_academy_courses"].split("; ") if c]
            ),
            "courses_covering_titles": m["related_academy_courses"],
            "coverage_status": status,
            "coverage_confidence": m["coverage_confidence"],
            "gap_score": gap_score,
        })

    df = pd.DataFrame(rows)
    # Sort by gap_score descending (blanks last)
    df["_sort"] = pd.to_numeric(df["gap_score"], errors="coerce").fillna(-1)
    df = df.sort_values("_sort", ascending=False).drop(columns=["_sort"])
    return df


# ── Main pipeline ─────────────────────────────────────────────────────

def main():
    print("Loading interim data...")
    releases = pd.read_csv(INTERIM / "product_releases.csv")
    learning = pd.read_csv(INTERIM / "learning_content.csv")

    # ── Filter to Anthropic only ──
    anthro_rel = releases[releases["vendor"] == "Anthropic"].copy()
    anthro_learn = learning[learning["vendor"] == "Anthropic"].copy()

    print(f"Anthropic releases: {len(anthro_rel)}")
    print(f"Anthropic courses: {len(anthro_learn)}")

    # ── Add topic_subcategory ──
    print("\nClassifying topic_subcategory...")
    subcats = []
    for _, row in anthro_rel.iterrows():
        title = str(row["title"])
        desc = str(row["description"])
        if row["product_area"] == "Claude Code":
            subcats.append(classify_subcategory(title, desc))
        else:
            subcats.append(classify_claude_subcategory(title, desc))
    anthro_rel["topic_subcategory"] = subcats

    # ── Add is_breaking_change (clean boolean) ──
    anthro_rel["is_breaking_change"] = anthro_rel.apply(
        lambda r: detect_breaking(
            str(r["title"]), str(r["description"]),
            str(r.get("is_breaking_change", ""))
        ), axis=1
    )

    # ── Add release_substance ──
    print("Classifying release_substance...")
    substances = []
    for _, row in anthro_rel.iterrows():
        substances.append(classify_substance(
            str(row["title"]), str(row["description"]),
            str(row["topic_category"]), str(row["topic_subcategory"]),
            bool(row["is_breaking_change"]),
        ))
    anthro_rel["release_substance"] = substances

    # ── Consistency enforcement ──
    print("Enforcing consistency rules...")
    violations = 0
    for idx, row in anthro_rel.iterrows():
        subcat = row["topic_subcategory"]
        substance = row["release_substance"]
        fixed = False

        if subcat == "bug fix" and substance != "maintenance":
            anthro_rel.at[idx, "release_substance"] = "maintenance"
            fixed = True
        elif subcat == "docs/tutorial" and substance != "maintenance":
            anthro_rel.at[idx, "release_substance"] = "maintenance"
            fixed = True
        elif subcat == "deprecation" and substance != "substantive":
            anthro_rel.at[idx, "release_substance"] = "substantive"
            fixed = True

        if fixed:
            violations += 1

    print(f"  Consistency violations fixed: {violations}")

    # ── Print substance/subcat summaries ──
    print("\n--- Substance by product_area ---")
    subst_summary = anthro_rel.groupby(
        ["product_area", "release_substance"]
    ).size().unstack(fill_value=0)
    print(subst_summary)

    print("\n--- Subcategory distribution ---")
    subcat_dist = anthro_rel.groupby(
        ["product_area", "topic_subcategory"]
    ).size().unstack(fill_value=0)
    for col in subcat_dist.columns:
        vals = subcat_dist[col]
        nonzero = vals[vals > 0]
        if not nonzero.empty:
            for area, count in nonzero.items():
                print(f"  {area} / {col}: {count}")

    # ── Save anthropic_product_releases.csv ──
    out_cols = [
        "vendor", "product_area", "release_date", "title", "description",
        "source_url", "source_type", "topic_category", "topic_subcategory",
        "release_substance", "is_breaking_change", "confidence",
    ]
    anthro_rel[out_cols].to_csv(
        PROCESSED / "anthropic_product_releases.csv", index=False
    )
    print(f"\nSaved: {PROCESSED / 'anthropic_product_releases.csv'}")

    # ── Save anthropic_learning_content.csv ──
    anthro_learn.to_csv(
        PROCESSED / "anthropic_learning_content.csv", index=False
    )
    print(f"Saved: {PROCESSED / 'anthropic_learning_content.csv'}")

    # ── Monthly summary ──
    anthro_rel["release_month"] = pd.to_datetime(
        anthro_rel["release_date"]
    ).dt.to_period("M").astype(str)
    monthly = anthro_rel.groupby(
        ["release_month", "product_area"]
    ).size().reset_index(name="count")
    monthly.to_csv(
        PROCESSED / "anthropic_release_summary_by_month.csv", index=False
    )
    print(f"Saved: {PROCESSED / 'anthropic_release_summary_by_month.csv'}")

    # ── Topic summary ──
    topic_summary = anthro_rel.groupby(
        ["topic_category", "topic_subcategory", "product_area"]
    ).agg(
        total_releases=("title", "size"),
        substantive=("release_substance", lambda x: (x == "substantive").sum()),
        maintenance=("release_substance", lambda x: (x == "maintenance").sum()),
        breaking_changes=("is_breaking_change", "sum"),
    ).reset_index()
    topic_summary.to_csv(
        PROCESSED / "anthropic_release_summary_by_topic.csv", index=False
    )
    print(f"Saved: {PROCESSED / 'anthropic_release_summary_by_topic.csv'}")

    # ── Coverage mapping ──
    print("\nBuilding topic-to-course coverage mapping...")
    mapping_df = build_coverage_mapping(anthro_rel, anthro_learn)
    mapping_df.to_csv(
        PROCESSED / "topic_coverage_mapping_draft.csv", index=False
    )
    print(f"Saved: {PROCESSED / 'topic_coverage_mapping_draft.csv'}")

    # Reviewed copy (same as draft with needs_human_review column)
    mapping_df.to_csv(
        PROCESSED / "topic_coverage_mapping_reviewed.csv", index=False
    )
    print(f"Saved: {PROCESSED / 'topic_coverage_mapping_reviewed.csv'}")

    # ── Coverage gap summary ──
    # Need breaking changes per topic group
    breaking_by_topic = anthro_rel.groupby(
        ["topic_category", "topic_subcategory"]
    )["is_breaking_change"].sum().reset_index()
    breaking_by_topic.columns = [
        "topic_category", "topic_subcategory", "breaking_changes"
    ]

    gap_df = build_gap_summary(mapping_df)
    # Merge breaking changes
    gap_df = gap_df.drop(columns=["breaking_changes"]).merge(
        breaking_by_topic, on=["topic_category", "topic_subcategory"],
        how="left"
    )
    gap_df["breaking_changes"] = gap_df["breaking_changes"].fillna(0).astype(int)
    # Reorder columns
    gap_cols = [
        "topic_category", "topic_subcategory", "total_releases",
        "substantive_releases", "breaking_changes", "courses_covering_count",
        "courses_covering_titles", "coverage_status", "coverage_confidence",
        "gap_score",
    ]
    gap_df = gap_df[gap_cols]
    gap_df.to_csv(PROCESSED / "coverage_gap_summary.csv", index=False)
    print(f"Saved: {PROCESSED / 'coverage_gap_summary.csv'}")

    # ── Output tables ──
    # release_summary_by_product_area
    by_area = anthro_rel.groupby("product_area").agg(
        total_releases=("title", "size"),
        substantive=("release_substance", lambda x: (x == "substantive").sum()),
        maintenance=("release_substance", lambda x: (x == "maintenance").sum()),
        breaking_changes=("is_breaking_change", "sum"),
        date_range_start=("release_date", "min"),
        date_range_end=("release_date", "max"),
    ).reset_index()
    by_area.to_csv(TABLES / "release_summary_by_product_area.csv", index=False)

    # release_summary_by_topic
    topic_summary.to_csv(TABLES / "release_summary_by_topic.csv", index=False)

    # release_summary_by_substance
    by_substance = anthro_rel.groupby(
        ["product_area", "release_substance"]
    ).size().reset_index(name="count")
    by_substance.to_csv(TABLES / "release_summary_by_substance.csv", index=False)

    # academy_course_catalog_clean
    course_clean = anthro_learn[
        ["title", "description", "url", "topic_category"]
    ].copy()
    course_clean["description"] = course_clean["description"].str[:150]
    course_clean.to_csv(TABLES / "academy_course_catalog_clean.csv", index=False)

    # coverage_gap_summary
    gap_df.to_csv(TABLES / "coverage_gap_summary.csv", index=False)

    print(f"\nSaved output tables to: {TABLES}")

    # ── Final summary ──
    print("\n" + "=" * 60)
    print("PROCESSED DATASET SUMMARY")
    print("=" * 60)
    for area in ["Claude", "Claude Code"]:
        subset = anthro_rel[anthro_rel["product_area"] == area]
        s = (subset["release_substance"] == "substantive").sum()
        m = (subset["release_substance"] == "maintenance").sum()
        print(f"  {area}: {s} substantive / {m} maintenance")
    print(f"  Total: {len(anthro_rel)} releases")
    print(f"  Breaking changes: {anthro_rel['is_breaking_change'].sum()}")
    print(f"  Academy courses: {len(anthro_learn)}")
    print()
    print("Coverage mapping:")
    for status in ["covered", "partial", "not visible", "unclear"]:
        count = (mapping_df["coverage_status"] == status).sum()
        if count > 0:
            print(f"  {status}: {count} topic groups")
    review_count = mapping_df["needs_human_review"].sum()
    print(f"  Needs human review: {review_count} rows")
    print()
    print("Top 5 by gap_score:")
    gap_sorted = gap_df[gap_df["gap_score"] != ""].copy()
    gap_sorted["gap_score"] = pd.to_numeric(gap_sorted["gap_score"])
    for _, row in gap_sorted.nlargest(5, "gap_score").iterrows():
        print(f"  {row['topic_category']}/{row['topic_subcategory']}: "
              f"gap={row['gap_score']:.0f} "
              f"(subst={row['substantive_releases']}, "
              f"status={row['coverage_status']})")


if __name__ == "__main__":
    main()
