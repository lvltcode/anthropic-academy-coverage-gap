#!/usr/bin/env python3
"""
Parse cached learning-catalog HTML into structured CSV.
Input:  data/raw/*_latest.html  (learning_content sources)
Output: data/interim/learning_content.csv
"""

import csv
import re
from pathlib import Path

from bs4 import BeautifulSoup
from dateutil import parser as dateparser

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

TOPIC_RULES: list[tuple[str, list[str]]] = [
    ("agent/tooling",    ["agent", "mcp", "tool", "subagent", "cowork",
                          "dispatch", "model context protocol", "skills"]),
    ("coding",           ["code", "coding", "ide", "developer", "cli",
                          "claude code"]),
    ("model release",    ["model", "opus", "sonnet", "haiku", "flash",
                          "gemini", "gpt"]),
    ("API capability",   ["api", "sdk", "bedrock", "vertex", "endpoint",
                          "function call"]),
    ("multimodal",       ["image", "vision", "audio", "video", "multimodal"]),
    ("enterprise/admin", ["enterprise", "admin", "team", "organization"]),
    ("safety/policy",    ["safety", "responsible", "alignment", "capabilities",
                          "limitations"]),
    ("docs/tutorial",    ["tutorial", "guide", "introduction", "101",
                          "foundations", "essentials", "quickstart"]),
]


def categorise(text: str) -> str:
    low = text.lower()
    for cat, keywords in TOPIC_RULES:
        if any(kw in low for kw in keywords):
            return cat
    return "other"


def try_find_date(el) -> str:
    """Try to find a visible date in or near an element. Returns '' if none."""
    date_re = re.compile(
        r"((?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},?\s+\d{4})",
        re.IGNORECASE,
    )
    iso_re = re.compile(r"(\d{4}-\d{2}-\d{2})")
    text = el.get_text(strip=True) if el else ""
    m = date_re.search(text) or iso_re.search(text)
    if m:
        try:
            dt = dateparser.parse(m.group(1), fuzzy=True)
            if dt and 2020 <= dt.year <= 2030:
                return dt.strftime("%Y-%m-%d")
        except (ValueError, OverflowError):
            pass
    return ""


# ── Source-specific parsers ────────────────────────────────────────────

def parse_skilljar(html: str, vendor: str, source_url: str) -> list[dict]:
    """Parse Skilljar-based catalog (e.g., anthropic.skilljar.com).
    Courses appear as card elements with title + description.
    """
    soup = BeautifulSoup(html, "lxml")
    entries = []

    # Strategy 1: Skilljar coursebox-container links
    # Structure: a.coursebox-container > div.coursebox-text (title)
    #                                  > div.coursebox-text-description (desc)
    cards = soup.select("a.coursebox-container")

    if cards:
        for card in cards:
            title_el = card.select_one(".coursebox-text")
            title = title_el.get_text(strip=True) if title_el else ""
            if not title:
                continue

            desc_el = card.select_one(".coursebox-text-description")
            description = desc_el.get_text(strip=True) if desc_el else ""

            href = card.get("href", "")
            url = href if href.startswith("http") else source_url.rstrip("/") + href

            updated = try_find_date(card)
            notes = "" if updated else "No public last-updated date visible"

            entries.append({
                "vendor": vendor,
                "content_platform": "Skilljar",
                "title": title,
                "description": description[:500],
                "url": url,
                "visible_last_updated": updated,
                "visible_created_at": "",
                "topic_category": categorise(f"{title} {description}"),
                "source_url": source_url,
                "confidence": "high",
                "notes": notes,
            })
        return entries

    # Strategy 2: fallback — any link with a course-like slug
    seen_titles = set()
    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if not re.search(r"^/[\w-]{5,}", href):
            continue
        title = a_tag.get_text(strip=True)
        if not title or len(title) < 4 or title in seen_titles:
            continue
        seen_titles.add(title)

        parent = a_tag.parent
        desc_el = parent.find("p") if parent else None
        description = desc_el.get_text(strip=True) if desc_el else ""

        url = href if href.startswith("http") else source_url.rstrip("/") + href

        entries.append({
            "vendor": vendor,
            "content_platform": "Skilljar",
            "title": title,
            "description": description[:500],
            "url": url,
            "visible_last_updated": "",
            "visible_created_at": "",
            "topic_category": categorise(f"{title} {description}"),
            "source_url": source_url,
            "confidence": "medium",
            "notes": "No public last-updated date visible",
        })

    return entries


def parse_generic_learning(html: str, vendor: str, platform: str,
                           source_url: str) -> list[dict]:
    """Generic parser for learning/tutorial pages."""
    soup = BeautifulSoup(html, "lxml")
    entries = []

    # Look for tutorial/course-like links and cards
    seen = set()
    for el in soup.find_all(["h2", "h3", "h4", "a"]):
        title = el.get_text(strip=True)
        if not title or len(title) < 8 or title in seen:
            continue
        if el.name == "a" and el.get("href"):
            url = el["href"]
            if not url.startswith("http"):
                url = source_url.rstrip("/") + "/" + url.lstrip("/")
        else:
            link = el.find("a", href=True)
            url = ""
            if link:
                url = link["href"]
                if not url.startswith("http"):
                    url = source_url.rstrip("/") + "/" + url.lstrip("/")

        # Filter out navigation/footer links
        if any(skip in title.lower() for skip in
               ["sign in", "log in", "cookie", "privacy", "terms",
                "footer", "header", "menu", "nav", "search"]):
            continue

        seen.add(title)
        updated = try_find_date(el.parent) if el.parent else ""

        entries.append({
            "vendor": vendor,
            "content_platform": platform,
            "title": title[:200],
            "description": "",
            "url": url,
            "visible_last_updated": updated,
            "visible_created_at": "",
            "topic_category": categorise(title),
            "source_url": source_url,
            "confidence": "low",
            "notes": "No public last-updated date visible" if not updated else "",
        })

    return entries


# ── Main pipeline ─────────────────────────────────────────────────────

SOURCES = [
    {
        "source_id": "anthropic_academy",
        "vendor": "Anthropic",
        "platform": "Skilljar",
        "parser": "skilljar",
        "url": "https://anthropic.skilljar.com/",
    },
    {
        "source_id": "openai_academy",
        "vendor": "OpenAI",
        "platform": "OpenAI Academy",
        "parser": "generic",
        "url": "https://academy.openai.com/",
    },
    {
        "source_id": "google_ai_tutorials",
        "vendor": "Google",
        "platform": "Google AI Dev",
        "parser": "generic",
        "url": "https://ai.google.dev/gemini-api/docs/quickstart",
    },
]

FIELDNAMES = [
    "vendor", "content_platform", "title", "description", "url",
    "visible_last_updated", "visible_created_at", "topic_category",
    "source_url", "confidence", "notes",
]


def main():
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)

    all_entries = []
    for src in SOURCES:
        html_path = RAW_DIR / f"{src['source_id']}_latest.html"
        if not html_path.exists():
            print(f"SKIP  {src['source_id']} — no cached HTML")
            continue

        print(f"PARSE {src['source_id']}...")
        html = html_path.read_text(encoding="utf-8")

        if src["parser"] == "skilljar":
            entries = parse_skilljar(html, src["vendor"], src["url"])
        else:
            entries = parse_generic_learning(
                html, src["vendor"], src["platform"], src["url"]
            )

        print(f"      {len(entries)} entries extracted")

        # Date visibility report
        with_dates = sum(1 for e in entries if e["visible_last_updated"])
        without_dates = len(entries) - with_dates
        print(f"      dates visible: {with_dates}  |  no dates: {without_dates}")

        all_entries.extend(entries)

    out_path = INTERIM_DIR / "learning_content.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(all_entries)

    print(f"\nSaved: {out_path}  ({len(all_entries)} total rows)")

    vendor_counts = {}
    for e in all_entries:
        vendor_counts[e["vendor"]] = vendor_counts.get(e["vendor"], 0) + 1
    print("By vendor:", vendor_counts)


if __name__ == "__main__":
    main()
