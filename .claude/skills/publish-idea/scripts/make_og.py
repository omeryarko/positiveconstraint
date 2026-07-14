#!/usr/bin/env python3
"""Render a 1200x630 Open Graph card PNG for an idea, using headless Chrome so
the card matches the site's actual web fonts. Used by publish.py (new ideas)
and the one-time migration (existing ideas)."""
import os, subprocess, tempfile, html as _html, shutil

ASSETS = os.path.join(os.path.dirname(__file__), "..", "assets")

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
        subprocess.run([
            chrome_bin(), "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--force-device-scale-factor=1", "--window-size=1200,630",
            "--virtual-time-budget=6000",
            "--screenshot=" + out_path, "file://" + html_path,
        ], check=True, capture_output=True)
    finally:
        os.unlink(html_path)
    return out_path


if __name__ == "__main__":
    import sys
    # test: render_og.py "Title" "CATEGORY" "summary" out.png
    render_og(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
    print("wrote", sys.argv[4])
