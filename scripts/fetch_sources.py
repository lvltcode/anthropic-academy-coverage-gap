#!/usr/bin/env python3
"""
Fetch and cache raw pages from product release and learning content sources.
Output: data/interim/source_status.csv
"""

import csv
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

SOURCES = [
    # --- Product release sources ---
    {
        "source_id": "anthropic_release_notes",
        "vendor": "Anthropic",
        "source_type": "product_release",
        "url": "https://support.claude.com/en/articles/12138966-release-notes",
    },
    {
        "source_id": "claude_code_changelog",
        "vendor": "Anthropic",
        "source_type": "product_release",
        "url": "https://code.claude.com/docs/en/changelog",
    },
    {
        "source_id": "google_gemini_changelog",
        "vendor": "Google",
        "source_type": "product_release",
        "url": "https://ai.google.dev/gemini-api/docs/changelog",
    },
    {
        "source_id": "openai_changelog",
        "vendor": "OpenAI",
        "source_type": "product_release",
        "url": "https://platform.openai.com/docs/changelog",
    },
    {
        "source_id": "openai_index",
        "vendor": "OpenAI",
        "source_type": "product_release",
        "url": "https://openai.com/index/",
    },
    # --- Learning content sources ---
    {
        "source_id": "anthropic_academy",
        "vendor": "Anthropic",
        "source_type": "learning_content",
        "url": "https://anthropic.skilljar.com/",
    },
    {
        "source_id": "openai_academy",
        "vendor": "OpenAI",
        "source_type": "learning_content",
        "url": "https://academy.openai.com/",
    },
    {
        "source_id": "google_ai_tutorials",
        "vendor": "Google",
        "source_type": "learning_content",
        "url": "https://ai.google.dev/gemini-api/docs/quickstart",
    },
]

REQUEST_DELAY = 2.5  # seconds between requests


def is_js_shell(html: str) -> bool:
    """Check if HTML is a JS-rendered shell with no real content."""
    lower_html = html.lower()
    shell_markers = [
        '<div id="root"></div>',
        '<div id="app"></div>',
        '<div id="__next"></div>',
        "window.__INITIAL_STATE__",
    ]
    has_shell_marker = any(m in lower_html for m in shell_markers)
    if not has_shell_marker:
        return False

    soup = BeautifulSoup(html, "lxml")
    body = soup.find("body")
    if body is None:
        return True
    text = body.get_text(separator=" ", strip=True)
    return len(text) < 300


def fetch_with_playwright(url: str) -> tuple:
    """Fetch a page using Playwright for JS-rendered content.
    Returns (html, method_note, http_status).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ("", "playwright_not_installed", 0)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            resp = page.goto(url, wait_until="networkidle", timeout=30000)
            status = resp.status if resp else 0
            html = page.content()
            browser.close()
            return (html, "playwright", status)
    except Exception as e:
        return ("", f"playwright_error: {str(e)[:120]}", 0)


def fetch_source(source: dict) -> dict:
    """Fetch a single source and return status dict."""
    source_id = source["source_id"]
    url = source["url"]
    now = datetime.now(timezone.utc)
    fetched_at = now.isoformat()

    result = {
        "source_id": source_id,
        "vendor": source["vendor"],
        "source_type": source["source_type"],
        "url": url,
        "fetch_method": "requests",
        "fetch_status": "unknown",
        "http_status": 0,
        "fetched_at": fetched_at,
        "notes": "",
    }

    # ---- Step 1: try requests ----
    html = ""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        result["http_status"] = resp.status_code

        if resp.status_code == 200:
            html = resp.text
            result["fetch_status"] = "success"
        elif resp.status_code == 403:
            result["fetch_status"] = "forbidden"
            result["notes"] = "Access forbidden - may require auth or block bots"
        elif resp.status_code == 404:
            result["fetch_status"] = "not_found"
            result["notes"] = "Page not found"
        else:
            result["fetch_status"] = f"http_{resp.status_code}"
            result["notes"] = f"HTTP {resp.status_code}"

    except requests.exceptions.Timeout:
        result["fetch_status"] = "timeout"
        result["notes"] = "Request timed out after 30s"
    except requests.exceptions.ConnectionError as e:
        result["fetch_status"] = "connection_error"
        result["notes"] = str(e)[:200]
    except Exception as e:
        result["fetch_status"] = "error"
        result["notes"] = str(e)[:200]

    # ---- Step 2: JS-shell check for learning_content sources ----
    if html and source["source_type"] == "learning_content" and is_js_shell(html):
        result["notes"] = "JS shell detected via requests, retrying with Playwright"
        pw_html, pw_note, pw_status = fetch_with_playwright(url)
        if pw_html and not is_js_shell(pw_html):
            html = pw_html
            result["fetch_method"] = "playwright"
            result["http_status"] = pw_status
            result["fetch_status"] = "success_playwright"
            result["notes"] = "Required Playwright for JS rendering"
        else:
            result["fetch_status"] = "js_shell"
            result["notes"] = f"JS shell; Playwright result: {pw_note}"

    # ---- Step 3: save raw HTML ----
    if html and result["fetch_status"].startswith("success"):
        timestamp = now.strftime("%Y%m%dT%H%M%SZ")
        filename = f"{source_id}_{timestamp}.html"
        (RAW_DIR / filename).write_text(html, encoding="utf-8")

        # Also save a "latest" copy for easy parser access
        (RAW_DIR / f"{source_id}_latest.html").write_text(html, encoding="utf-8")

    return result


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    INTERIM_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Fetching {len(SOURCES)} sources...")
    print(f"  Raw HTML -> {RAW_DIR}")
    print(f"  Status   -> {INTERIM_DIR / 'source_status.csv'}")
    print()

    results = []
    for i, source in enumerate(SOURCES):
        label = f"[{i + 1}/{len(SOURCES)}]"
        print(f"{label} {source['source_id']}")
        print(f"      {source['url']}")

        result = fetch_source(source)
        results.append(result)

        status_icon = "OK" if result["fetch_status"].startswith("success") else "FAIL"
        print(f"      {status_icon}  {result['fetch_status']}  HTTP {result['http_status']}")
        if result["notes"]:
            print(f"      {result['notes']}")
        print()

        if i < len(SOURCES) - 1:
            time.sleep(REQUEST_DELAY)

    # ---- Write source_status.csv ----
    fieldnames = [
        "source_id", "vendor", "source_type", "url",
        "fetch_method", "fetch_status", "http_status",
        "fetched_at", "notes",
    ]
    status_path = INTERIM_DIR / "source_status.csv"
    with open(status_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    print(f"Saved: {status_path}")
    ok = sum(1 for r in results if r["fetch_status"].startswith("success"))
    print(f"Summary: {ok}/{len(results)} sources fetched successfully")


if __name__ == "__main__":
    main()
