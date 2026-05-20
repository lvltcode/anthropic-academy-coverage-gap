#!/usr/bin/env python3
"""
Parse cached release-note HTML into structured CSV.
Input:  data/raw/*_latest.html
Output: data/interim/product_releases.csv
"""

import csv
import re
import sys
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

# ── Topic categorisation ──────────────────────────────────────────────
TOPIC_RULES: list[tuple[str, list[str]]] = [
    ("deprecation",     ["deprecat", "sunset", "end of support", "end-of-life",
                         "eol", "removed", "discontinued", "shutdown"]),
    ("model release",   ["model", "opus", "sonnet", "haiku", "flash", "gemini",
                         "gpt", "claude 3", "claude 4", "launch", "generally available"]),
    ("agent/tooling",   ["agent", "mcp", "tool use", "tool_use", "computer use",
                         "plugin", "extension", "cowork", "dispatch", "subagent"]),
    ("coding",          ["code", "coding", "ide", "vscode", "jetbrains",
                         "editor", "terminal", "cli", "sdk"]),
    ("multimodal",      ["image", "vision", "audio", "video", "pdf", "file",
                         "multimodal", "speech", "tts", "text-to-speech"]),
    ("API capability",  ["api", "endpoint", "function call", "structured output",
                         "batch", "rate limit", "token", "context window",
                         "streaming", "embed"]),
    ("safety/policy",   ["safety", "policy", "trust", "responsible", "guardrail",
                         "filter", "moderation", "alignment"]),
    ("enterprise/admin",["enterprise", "admin", "team", "organization", "sso",
                         "workspace", "permission"]),
    ("pricing/billing", ["pricing", "price", "cost", "billing", "plan", "tier",
                         "credit", "free"]),
    ("docs/tutorial",   ["documentation", "tutorial", "guide", "example",
                         "cookbook", "quickstart"]),
]

BREAKING_KEYWORDS = [
    "breaking change", "deprecat", "migration required", "removed support",
    "api change", "sunset", "end of support", "end-of-life", "eol",
    "no longer support", "will be removed", "shutdown",
]


def categorise(text: str) -> str:
    low = text.lower()
    for cat, keywords in TOPIC_RULES:
        if any(kw in low for kw in keywords):
            return cat
    return "other"


def is_breaking(text: str) -> bool:
    low = text.lower()
    return any(kw in low for kw in BREAKING_KEYWORDS)


def try_parse_date(text: str):
    """Return ISO date string or None."""
    text = text.strip().rstrip(":")
    # Remove markdown/HTML artefacts
    text = re.sub(r"[#*`]", "", text).strip()
    if not text or len(text) < 4:
        return None
    try:
        dt = dateparser.parse(text, fuzzy=True)
        if dt and 2020 <= dt.year <= 2030:
            return dt.strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        pass
    return None


# ── Source-specific parsers ────────────────────────────────────────────

def parse_anthropic_releases(html: str, source_url: str) -> list[dict]:
    """Parse support.claude.com release notes.
    Intercom-rendered: div.intercom-interblocks-subheading3 (dates),
    div.intercom-interblocks-paragraph (title + description),
    div.intercom-interblocks-unordered-nested-list (bullet details).
    """
    soup = BeautifulSoup(html, "lxml")
    entries = []

    date_divs = soup.select("div.intercom-interblocks-subheading3")
    for date_div in date_divs:
        date_text = date_div.get_text(strip=True)
        release_date = try_parse_date(date_text)
        if not release_date:
            continue

        title = ""
        desc_parts = []
        sib = date_div.find_next_sibling()
        while sib:
            classes = sib.get("class", [])
            class_str = " ".join(classes)
            # Stop at next date heading or month heading
            if "intercom-interblocks-subheading3" in class_str:
                break
            if "intercom-interblocks-subheading" in class_str and "subheading3" not in class_str:
                break

            text = sib.get_text(strip=True)
            if "intercom-interblocks-paragraph" in class_str:
                if text:
                    if not title:
                        title = text
                    else:
                        desc_parts.append(text)
            elif "intercom-interblocks-unordered" in class_str:
                for li in sib.find_all("li"):
                    li_text = li.get_text(strip=True)
                    if li_text:
                        desc_parts.append(f"- {li_text}")

            sib = sib.find_next_sibling()

        description = "\n".join(desc_parts)[:500]
        combined = f"{title} {description}"

        entries.append({
            "vendor": "Anthropic",
            "product_area": "Claude",
            "release_date": release_date,
            "title": title or date_text,
            "description": description,
            "source_url": source_url,
            "source_type": "release_notes",
            "topic_category": categorise(combined),
            "is_breaking_change": is_breaking(combined),
            "confidence": "high",
        })

    return entries


def parse_claude_code_changelog(html: str, source_url: str) -> list[dict]:
    """Parse code.claude.com changelog.
    May contain MDX <Update> components in source or rendered HTML.
    """
    entries = []

    # Strategy 1: raw MDX <Update label="VER" description="DATE">
    update_re = re.compile(
        r'<Update\s+label="([^"]+)"\s+description="([^"]+)">(.*?)</Update>',
        re.DOTALL,
    )
    matches = update_re.findall(html)
    if matches:
        for version, date_str, content in matches:
            release_date = try_parse_date(date_str)
            if not release_date:
                continue
            items = re.findall(r"\*\s+(.+?)(?=\n\*|\Z)", content, re.DOTALL)
            description = "\n".join(
                f"- {item.strip()}" for item in items[:15]
            )[:500]
            title = f"Claude Code {version}"
            combined = f"{title} {description}"
            entries.append({
                "vendor": "Anthropic",
                "product_area": "Claude Code",
                "release_date": release_date,
                "title": title,
                "description": description,
                "source_url": source_url,
                "source_type": "changelog",
                "topic_category": categorise(combined),
                "is_breaking_change": is_breaking(combined),
                "confidence": "high",
            })
        return entries

    # Strategy 2: rendered HTML with headings containing versions / dates
    soup = BeautifulSoup(html, "lxml")

    # Look for elements that contain version-like text near dates
    version_re = re.compile(r"(\d+\.\d+\.\d+)")
    date_re = re.compile(
        r"((?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},?\s+\d{4})",
        re.IGNORECASE,
    )

    # Try headings first
    for hdr in soup.find_all(["h2", "h3", "h4"]):
        hdr_text = hdr.get_text(strip=True)
        ver_m = version_re.search(hdr_text)
        if not ver_m:
            continue
        version = ver_m.group(1)

        # Date may be in header itself or in next sibling
        date_m = date_re.search(hdr_text)
        if not date_m:
            nxt = hdr.find_next_sibling()
            if nxt:
                date_m = date_re.search(nxt.get_text(strip=True))
        if not date_m:
            continue

        release_date = try_parse_date(date_m.group(1))
        if not release_date:
            continue

        desc_parts = []
        sib = hdr.find_next_sibling()
        while sib and sib.name not in ("h2", "h3", "h4"):
            if sib.name in ("ul", "ol"):
                for li in sib.find_all("li", recursive=False):
                    desc_parts.append(f"- {li.get_text(strip=True)}")
            elif sib.name == "p":
                desc_parts.append(sib.get_text(strip=True))
            sib = sib.find_next_sibling()

        description = "\n".join(desc_parts)[:500]
        title = f"Claude Code {version}"
        combined = f"{title} {description}"

        entries.append({
            "vendor": "Anthropic",
            "product_area": "Claude Code",
            "release_date": release_date,
            "title": title,
            "description": description,
            "source_url": source_url,
            "source_type": "changelog",
            "topic_category": categorise(combined),
            "is_breaking_change": is_breaking(combined),
            "confidence": "medium",
        })

    # Strategy 3: plain-text fallback – scan full text for version + date pairs
    if not entries:
        full_text = soup.get_text(separator="\n")
        blocks = re.split(r"\n{2,}", full_text)
        for block in blocks:
            ver_m = version_re.search(block)
            date_m = date_re.search(block)
            if ver_m and date_m:
                release_date = try_parse_date(date_m.group(1))
                if not release_date:
                    continue
                version = ver_m.group(1)
                lines = [l.strip() for l in block.split("\n") if l.strip()]
                description = "\n".join(lines[:10])[:500]
                title = f"Claude Code {version}"
                combined = f"{title} {description}"
                entries.append({
                    "vendor": "Anthropic",
                    "product_area": "Claude Code",
                    "release_date": release_date,
                    "title": title,
                    "description": description,
                    "source_url": source_url,
                    "source_type": "changelog",
                    "topic_category": categorise(combined),
                    "is_breaking_change": is_breaking(combined),
                    "confidence": "low",
                })

    return entries


def parse_google_gemini_changelog(html: str, source_url: str) -> list[dict]:
    """Parse ai.google.dev Gemini API changelog.
    Structure: date headers followed by bullet lists.
    """
    soup = BeautifulSoup(html, "lxml")
    entries = []

    date_re = re.compile(
        r"((?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},?\s+\d{4})",
        re.IGNORECASE,
    )

    # Try headings (h2, h3, h4) with dates
    for hdr in soup.find_all(["h2", "h3", "h4"]):
        hdr_text = hdr.get_text(strip=True)
        date_m = date_re.search(hdr_text)
        if not date_m:
            continue

        release_date = try_parse_date(date_m.group(1))
        if not release_date:
            continue

        desc_parts = []
        sib = hdr.find_next_sibling()
        while sib and sib.name not in ("h2", "h3", "h4"):
            if sib.name in ("ul", "ol"):
                for li in sib.find_all("li", recursive=False):
                    desc_parts.append(li.get_text(strip=True))
            elif sib.name == "p":
                desc_parts.append(sib.get_text(strip=True))
            sib = sib.find_next_sibling()

        # Each bullet point could be a separate release entry
        if desc_parts:
            for item in desc_parts:
                combined = item
                entries.append({
                    "vendor": "Google",
                    "product_area": "Gemini API",
                    "release_date": release_date,
                    "title": item[:120],
                    "description": item[:500],
                    "source_url": source_url,
                    "source_type": "changelog",
                    "topic_category": categorise(combined),
                    "is_breaking_change": is_breaking(combined),
                    "confidence": "high",
                })
        else:
            entries.append({
                "vendor": "Google",
                "product_area": "Gemini API",
                "release_date": release_date,
                "title": hdr_text,
                "description": "",
                "source_url": source_url,
                "source_type": "changelog",
                "topic_category": "other",
                "is_breaking_change": False,
                "confidence": "medium",
            })

    # Fallback: scan full text for date-delimited blocks
    if not entries:
        full_text = soup.get_text(separator="\n")
        parts = date_re.split(full_text)
        # parts alternates between non-date text and date matches
        i = 1
        while i < len(parts) - 1:
            date_str = parts[i]
            content = parts[i + 1] if i + 1 < len(parts) else ""
            release_date = try_parse_date(date_str)
            if release_date:
                lines = [l.strip() for l in content.split("\n") if l.strip()]
                for line in lines[:20]:
                    if len(line) > 10:
                        entries.append({
                            "vendor": "Google",
                            "product_area": "Gemini API",
                            "release_date": release_date,
                            "title": line[:120],
                            "description": line[:500],
                            "source_url": source_url,
                            "source_type": "changelog",
                            "topic_category": categorise(line),
                            "is_breaking_change": is_breaking(line),
                            "confidence": "low",
                        })
            i += 2

    return entries


def parse_openai_changelog(html: str, source_url: str) -> list[dict]:
    """Best-effort parse of OpenAI changelog or index page."""
    soup = BeautifulSoup(html, "lxml")
    entries = []

    date_re = re.compile(
        r"((?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},?\s+\d{4})",
        re.IGNORECASE,
    )
    iso_date_re = re.compile(r"(\d{4}-\d{2}-\d{2})")

    # Try headings with dates
    for hdr in soup.find_all(["h1", "h2", "h3", "h4"]):
        hdr_text = hdr.get_text(strip=True)
        date_m = date_re.search(hdr_text) or iso_date_re.search(hdr_text)
        if not date_m:
            # Check sibling/parent for date
            parent = hdr.parent
            if parent:
                parent_text = parent.get_text(strip=True)
                date_m = date_re.search(parent_text) or iso_date_re.search(parent_text)
        if not date_m:
            continue

        release_date = try_parse_date(date_m.group(1))
        if not release_date:
            continue

        desc_parts = []
        sib = hdr.find_next_sibling()
        while sib and sib.name not in ("h1", "h2", "h3", "h4"):
            text = sib.get_text(strip=True)
            if text:
                desc_parts.append(text)
            sib = sib.find_next_sibling()

        description = "\n".join(desc_parts)[:500]
        title = hdr_text[:120]
        combined = f"{title} {description}"

        entries.append({
            "vendor": "OpenAI",
            "product_area": "Platform",
            "release_date": release_date,
            "title": title,
            "description": description,
            "source_url": source_url,
            "source_type": "changelog",
            "topic_category": categorise(combined),
            "is_breaking_change": is_breaking(combined),
            "confidence": "medium",
        })

    return entries


# ── Main pipeline ─────────────────────────────────────────────────────

PARSERS = {
    "anthropic_release_notes": (
        parse_anthropic_releases,
        "https://support.claude.com/en/articles/12138966-release-notes",
    ),
    "claude_code_changelog": (
        parse_claude_code_changelog,
        "https://code.claude.com/docs/en/changelog",
    ),
    "google_gemini_changelog": (
        parse_google_gemini_changelog,
        "https://ai.google.dev/gemini-api/docs/changelog",
    ),
    "openai_changelog": (
        parse_openai_changelog,
        "https://platform.openai.com/docs/changelog",
    ),
    "openai_index": (
        parse_openai_changelog,
        "https://openai.com/index/",
    ),
}

FIELDNAMES = [
    "vendor", "product_area", "release_date", "title", "description",
    "source_url", "source_type", "topic_category", "is_breaking_change",
    "confidence",
]


def main():
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)

    all_entries = []
    for source_id, (parser_fn, source_url) in PARSERS.items():
        html_path = RAW_DIR / f"{source_id}_latest.html"
        if not html_path.exists():
            print(f"SKIP  {source_id} — no cached HTML at {html_path}")
            continue

        print(f"PARSE {source_id}...")
        html = html_path.read_text(encoding="utf-8")
        entries = parser_fn(html, source_url)
        print(f"      {len(entries)} entries extracted")

        # Per-vendor summary
        cats = {}
        for e in entries:
            cats[e["topic_category"]] = cats.get(e["topic_category"], 0) + 1
        if cats:
            print(f"      categories: {cats}")

        all_entries.extend(entries)

    # Sort by date descending
    all_entries.sort(key=lambda e: e["release_date"], reverse=True)

    out_path = INTERIM_DIR / "product_releases.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(all_entries)

    print(f"\nSaved: {out_path}  ({len(all_entries)} total rows)")

    # Vendor summary
    vendor_counts = {}
    for e in all_entries:
        vendor_counts[e["vendor"]] = vendor_counts.get(e["vendor"], 0) + 1
    print("By vendor:", vendor_counts)


if __name__ == "__main__":
    main()
