---
name: render-og
description: >-
  Render a 1200x630 Open Graph link-preview PNG for a positiveconstraint.com
  idea page, using headless Chrome against the site's own og-template.html so
  the card matches the site's actual web fonts. Use this whenever a page needs
  its /media/og/<slug>.png share-card image generated or regenerated — most
  often as one step inside publishing a new idea (see the build-page and
  publish-idea skills), but also standalone when re-rendering a card for a
  title/summary that changed after publish.
license: MIT
compatibility: >-
  Requires Python 3.6+, Pillow, and headless Chrome or Chromium on PATH (or at
  a known macOS app path). Non-fatal to the caller if Chrome is missing.
metadata:
  author: positiveconstraint
  version: "1.0"
---

# Render an Open Graph card

Renders the card that unfurls when an idea's URL is shared on X / LinkedIn /
Slack / iMessage: a 1200×630 PNG built from `assets/og-template.html` (a light
card matching the site's typography), screenshotted with headless Chrome so
web fonts render correctly (a plain HTML-to-image conversion without a real
browser would fall back to system fonts and look wrong).

This is a **fixed light card for every viewer** — link previews can't be
theme-aware, so there's no dark-mode variant to generate.

## When to use this standalone vs. via build-page

`build-page`'s `build_page.py` already calls this skill's `render_og()`
function directly when it builds a new idea page, so publishing a new idea
never needs this skill run by hand. Run it standalone only to **re-render** an
existing idea's card — e.g. the title or summary changed after publish and the
share card needs to catch up.

## Usage

```bash
python3 scripts/render_og.py --title "Altitude Thinking" \
  --category "CONCEPTS" \
  --summary "A worked example of finding the one unchanging element..." \
  --output site/media/og/altitude-thinking.png
```

- `--title` — the idea's title, exactly as it appears in `<h1>`.
- `--category` — the category's **display label, uppercased** (e.g.
  `CONCEPTS`, not `concepts`) — this is what's printed on the card, matching
  `{{CATEGORY_UPPER}}` in the page template.
- `--summary` — the idea's summary (front-matter `summary` field, full text —
  the template handles wrapping).
- `--output` — where to write the PNG. Conventionally
  `site/media/og/<slug>.png` (or the equivalent path inside a staged copy of
  the site).

Prints `wrote <path>` on success.

## Prerequisites

**Headless Chrome or Chromium** must be on `PATH` as `google-chrome` /
`chromium`, or (on macOS) installed at the standard `/Applications/Google
Chrome.app` or `/Applications/Chromium.app` path. If none is found,
`render_og()` raises `RuntimeError: No Chrome/Chromium found for OG image
rendering.` — callers (build-page) catch this and continue without an image
rather than fail the whole publish.

**Pillow** (`PIL`) is used to crop the screenshot to exactly 1200×630 — Chrome
headless reserves some vertical space for virtual UI chrome on Linux, so the
script renders at 1200×730 and crops.

## How it works

1. Fill `assets/og-template.html`'s `{{TITLE}}` / `{{CATEGORY_UPPER}}` /
   `{{SUMMARY}}` placeholders (HTML-escaped) and write the result to a temp
   file.
2. Screenshot that temp file with `chrome --headless=new
   --window-size=1200,730 --screenshot=<out> file://<temp>`.
3. Crop to 1200×630 with Pillow if the screenshot came out taller.
4. Delete the temp HTML file.

## Importing this as a library

Other skills call `render_og(title, category_upper, summary, out_path,
template=None)` directly rather than shelling out to the CLI — it's a plain
Python function in `scripts/render_og.py`. Pass `template` to override the
default `assets/og-template.html` if you ever need a variant card.
