"""Visual smoke test — captures 4 dashboard screenshots via Playwright.

Run: ./venv/bin/python tests/capture_screenshots.py
Requires the dashboard to be running at http://127.0.0.1:9300.
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

BASE = "http://127.0.0.1:9300"

PAGES = [
    ("home.png", "/"),
    ("clusters.png", "/clusters"),
    ("cluster_detail.png", "/clusters/finance"),
    ("audit.png", "/audit?days=30"),
]


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        for fname, path in PAGES:
            url = BASE + path
            print(f"-> {url}")
            page.goto(url, wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=4000)
            except Exception:
                pass
            # Give chart.js a moment to render
            page.wait_for_timeout(600)
            out = OUT / fname
            page.screenshot(path=str(out), full_page=True)
            print(f"   saved {out} ({out.stat().st_size} bytes)")
        browser.close()
    print(f"OK 4 screenshots in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
