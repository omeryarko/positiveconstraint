#!/usr/bin/env python3
"""Render a 1200x630 Open Graph card PNG for an idea, using headless Chrome so
the card matches the site's actual web fonts.

Used standalone (CLI below) or imported by build-page's build_page.py, which
calls render_og() directly for the "build a new idea page" workflow. Rendering
is non-fatal in that caller: if Chrome is missing, the page still ships
without a preview card.

CLI:
    python render_og.py --title "..." --category "..." --summary "..." --output path/to/og.png
"""
import argparse
import html as _html
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

# This script is self-contained (no category colors or tracking IDs appear on
# the OG card — it's a fixed-light card per page-template.html's design
# guarantee), so it doesn't need _lib. The sys.path wiring other scripts in
# this skill family use is: sys.path.insert(0, os.path.join(
# os.path.dirname(os.path.abspath(__file__)), '..', '..', '_lib'))

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]


def chrome_bin():
    for c in CHROME_CANDIDATES:
        if c and os.path.exists(c):
            return c
    raise RuntimeError("No Chrome/Chromium found for OG image rendering.")


def render_og(title, category_upper, summary, out_path, template=None):
    tmpl = template or open(os.path.join(ASSETS, "og-template.html"), encoding="utf-8").read()
    filled = (tmpl.replace("{{TITLE}}", _html.escape(title))
                  .replace("{{CATEGORY_UPPER}}", _html.escape(category_upper))
                  .replace("{{SUMMARY}}", _html.escape(summary)))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(filled)
        html_path = f.name
    try:
        # Chrome headless reserves ~80px for virtual UI chrome on Linux;
        # render taller then crop to the target 1200x630.
        subprocess.run([
            chrome_bin(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage",
            "--force-device-scale-factor=1", "--window-size=1200,730",
            "--virtual-time-budget=6000",
            "--screenshot=" + out_path, "file://" + html_path,
        ], check=True, capture_output=True, timeout=30)
    finally:
        os.unlink(html_path)
    img = Image.open(out_path)
    if img.size != (1200, 630):
        img.crop((0, 0, 1200, 630)).save(out_path)
    return out_path


def main():
    ap = argparse.ArgumentParser(description="Render a 1200x630 OG card PNG for an idea.")
    ap.add_argument("--title", required=True)
    ap.add_argument("--category", required=True, help="Category label, e.g. CONCEPTS (uppercase display form).")
    ap.add_argument("--summary", required=True)
    ap.add_argument("--output", required=True, help="Output PNG path, e.g. media/og/my-slug.png")
    args = ap.parse_args()
    out = render_og(args.title, args.category, args.summary, args.output)
    print("wrote", out)


if __name__ == "__main__":
    main()
