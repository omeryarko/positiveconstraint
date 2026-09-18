"""Shared site-reading/writing helpers for the publish-idea skill family.

Extracted from the original monolithic scripts/publish.py. These functions
read and surgically edit the hand-built static HTML tree at ./site — parsing
the embedded JS data arrays (NODES/EDGES/COLORS on the map, MAP_* on the
homepage, RELATED on each idea page), rendering the "Related Ideas" connection
cards, and diffing a staged copy against the live tree.

No subcommand/CLI logic lives here — see build_page.py, update_indexes.py,
render_og.py, and deploy.py for the scripts that call into this module.
"""
import html
import json
import os
import re

import config

# --------------------------------------------------------------- file I/O

def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


# ------------------------------------------------------------- embedded JS

def js_array(content, var):
    """Parse a `var NAME = [...]` or `var NAME = {...};` literal out of a page's
    inline <script> and return it as Python data."""
    m = re.search(r'var %s = (\[.*?\]|\{.*?\});' % var, content, re.S)
    return json.loads(m.group(1))


def set_js(content, var, value):
    """Replace a `var NAME = ...;` literal with new JSON-serialized data."""
    return re.sub(r'(var %s = )(\[.*?\]|\{.*?\})(;)' % var,
                  lambda m: m.group(1) + json.dumps(value) + m.group(3),
                  content, count=1, flags=re.S)


# ------------------------------------------------------------ page summaries

def strip_summary(page_html, limit=140):
    """Plain-text summary from a page's <p class="piece-summary">, truncated on
    a word boundary for use in map nodes and index cards."""
    m = re.search(r'<p class="piece-summary">(.*?)</p>', page_html, re.S)
    if not m:
        return ""
    txt = re.sub(r'<[^>]+>', '', m.group(1))
    txt = html.unescape(re.sub(r'\s+', ' ', txt)).strip()
    if len(txt) <= limit:
        return txt
    cut = txt[:limit].rsplit(" ", 1)[0].rstrip(",.;:—- ")
    return cut + "…"


def cat_color(cat, colors):
    """Resolve a category's display color: the map's own COLORS dict first,
    then the shared config default, then a generic fallback."""
    return colors.get(cat) or config.CATEGORY_COLORS.get(cat) or config.DEFAULT_CATEGORY_COLOR


# ------------------------------------------------------------ slug lookups

def target_section(site_dir, slug):
    """Determine which section (ideas/braintail) an existing slug lives in."""
    for sec in ("ideas", "braintail"):
        if os.path.exists(os.path.join(site_dir, sec, slug, "index.html")):
            return sec
    return "ideas"


def byid_title(site_dir, slug):
    """Look up an existing page's <h1> title by slug. Exits with a clear error
    if the connection target doesn't exist — a connection can't point nowhere."""
    p = None
    for sec in ("ideas", "braintail"):
        candidate = os.path.join(site_dir, sec, slug, "index.html")
        if os.path.exists(candidate):
            p = candidate
            break
    if p is None:
        raise FileNotFoundError(
            f"Connection target '{slug}' has no page at /ideas/{slug}/ or /braintail/{slug}/.")
    m = re.search(r'<h1>(.*?)</h1>', read(p), re.S)
    return re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else slug


# ---------------------------------------------------- connection card render

def render_connections(related, site_dir, self_slug=None):
    """Render the <section class="connections"> inner HTML from a RELATED list:
    one flat "Related Ideas" group, up to MAX_RELATED_CARDS cards, no
    relationship labels (those only survive in the markdown export)."""
    if not related:
        return ""
    cards = []
    for r in related[:config.MAX_RELATED_CARDS]:
        parts = r["url"].strip("/").split("/")
        sec, slug = (parts[0], parts[1]) if len(parts) > 1 else ("ideas", parts[-1])
        summ = strip_summary(read(os.path.join(site_dir, sec, slug, "index.html")))
        cards.append(
            f'      <a href="{r["url"]}" class="conn-item">\n'
            f'        <span class="conn-title">{r["title"]}</span>\n'
            f'        <span class="conn-summary">{summ}</span>\n'
            f'      </a>')
    return ('    <h4>Related Ideas</h4>\n'
            '    <div class="conn-grid">\n' + "\n".join(cards) + "\n    </div>")


def set_connections(page_html, inner):
    """Replace the connections section's inner HTML. If there are no related
    ideas, drop the whole <section> so the page has no empty gap."""
    if not inner:
        return re.sub(r'\s*<section class="connections">.*?</section>', '',
                      page_html, count=1, flags=re.S)
    if '<section class="connections">' in page_html:
        return re.sub(r'(<section class="connections">).*?(</section>)',
                      lambda m: m.group(1) + "\n" + inner + "\n  " + m.group(2),
                      page_html, count=1, flags=re.S)
    # no section present (e.g. a page that had no related ideas) — add one
    # back right before the closing </main>.
    section = '\n  <section class="connections">\n' + inner + '\n  </section>\n'
    return page_html.replace("</main>", section + "</main>", 1)


def rebuild_connections(page, related, site_dir):
    """Set a page's connections section to the flat, capped render of its
    RELATED array."""
    return set_connections(page, render_connections(related, site_dir))


# ---------------------------------------------------------------- diffing

# Build metadata files that live alongside a stage's content but are never
# part of the site itself — never included in a deploy manifest.
NON_CONTENT_FILES = {"manifest.json", "idea.json"}


def build_manifest(old_dir, new_dir):
    """Walk new_dir and report every file that's new or changed relative to
    old_dir, for the stage/deploy manifest."""
    changed = []
    for root, _, files in os.walk(new_dir):
        for f in files:
            if f in NON_CONTENT_FILES:
                continue
            sp = os.path.join(root, f)
            rel = os.path.relpath(sp, new_dir)
            op = os.path.join(old_dir, rel)
            new = not os.path.exists(op)
            if new or read_bytes(sp) != read_bytes(op):
                changed.append({"path": rel.replace(os.sep, "/"), "new": new})
    return changed
