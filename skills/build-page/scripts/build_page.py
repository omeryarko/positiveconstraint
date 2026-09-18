#!/usr/bin/env python3
"""build_page.py — parse a publish-idea input file (YAML front-matter +
lightweight markdown body) and render it into a new site page.

Extracted from the "build the new page" half of the original monolithic
scripts/publish.py. This script only produces the new page + its OG image +
a small idea.json manifest describing what was built — it never touches any
*other* existing page (reverse connections, map, homepage, ideas index,
llms.txt, sitemap.xml). That surgery is update-indexes' job; run it next.

CLI:
    python build_page.py --input idea.yaml --site ./site --output-dir ./output/

--site is the existing site tree (read-only here) used to look up connection
targets' titles/summaries so the new page's "Related Ideas" cards can render.
It is usually the same path as --output-dir when this is run against a
working stage copy (the normal publish-idea workflow), but doesn't have to be.

Produces, under --output-dir:
    {section}/{slug}/index.html   — the new page
    media/og/{slug}.png           — its Open Graph link-preview image (non-fatal
                                     if headless Chrome isn't available)
    idea.json                     — metadata for update-indexes' stage
"""
import argparse
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '_lib'))
import config
import site_io

# ---------------------------------------------------------------- front matter

def parse_front_matter(text):
    if not text.startswith("---"):
        sys.exit("Input must start with a '---' YAML front-matter block.")
    _, fm, body = text.split("---", 2)
    data, lines, i = {}, fm.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1; continue
        m = re.match(r'^(\w+):\s*(.*)$', line)
        if not m:
            i += 1; continue
        key, val = m.group(1), m.group(2).strip()
        if key == "connections":
            conns = []
            i += 1
            while i < len(lines) and lines[i].lstrip().startswith("-"):
                item = lines[i].lstrip()[1:].strip().strip("{}")
                d = {}
                for part in re.split(r',\s*(?=\w+\s*:)', item):
                    if ":" in part:
                        k, v = part.split(":", 1)
                        d[k.strip()] = v.strip()
                if d.get("target"):
                    conns.append(d)
                i += 1
            data["connections"] = conns
            continue
        if val == ">" or val == "|":            # folded/literal block scalar
            buf, i = [], i + 1
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                buf.append(lines[i].strip()); i += 1
            data[key] = " ".join(x for x in buf if x).strip()
            continue
        if val.startswith("[") and val.endswith("]"):
            data[key] = [x.strip() for x in val[1:-1].split(",") if x.strip()]
            i += 1; continue
        data[key] = val.strip().strip('"')
        i += 1
    return data, body.lstrip("\n")

# ------------------------------------------------------------ markdown -> html

def inline(t):
    t = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', t)
    t = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', t)
    t = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', t)
    return t

def render_body(md):
    blocks = re.split(r'\n\s*\n', md.strip())
    out = []
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        if b.strip() == "ⵙ":
            out.append('    <p style="text-align:center">ⵙ</p>')
        elif b.startswith("### "):
            out.append(f"    <h3>{inline(b[4:].strip())}</h3>")
        elif b.startswith("## "):
            out.append(f"    <h2>{inline(b[3:].strip())}</h2>")
        elif b.startswith(">"):
            quote, cite = [], None
            for ln in b.splitlines():
                ln = ln.lstrip(">").strip()
                if ln.startswith("—") or ln.startswith("--"):
                    cite = ln.replace("--", "—")
                elif ln:
                    quote.append(ln)
            qtext = "<br>\n      ".join(inline(q) for q in quote)
            blk = ["    <blockquote>", f"      <p>{qtext}</p>"]
            if cite:
                blk.append(f"      <cite>{inline(cite)}</cite>")
            blk.append("    </blockquote>")
            out.append("\n".join(blk))
        elif b.startswith("@youtube"):
            m = re.match(r'@youtube\[([^\]]+)\]', b)
            parts = [p.strip() for p in m.group(1).split("|")]
            vid = parts[0]; title = parts[1] if len(parts) > 1 else ""
            ratio = parts[2] if len(parts) > 2 else "16-9"
            flags = [p.lower() for p in parts[3:]]
            src = f"https://www.youtube.com/embed/{vid}"
            if "autoplay" in flags:
                # muted autoplay + loop (mute is required for browsers to honor autoplay)
                src += f"?autoplay=1&mute=1&loop=1&playlist={vid}&playsinline=1"
            out.append(
                f'    <div class="media-video media-{ratio}">\n'
                f'      <iframe src="{src}" title="{title}" '
                f'allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
                f'gyroscope; picture-in-picture" allowfullscreen></iframe>\n    </div>')
        elif re.match(r'^[*\-]\s+', b):
            items = [re.sub(r'^[*\-]\s+', '', ln.strip())
                     for ln in b.splitlines() if ln.strip()]
            lis = "\n".join(f"      <li>{inline(it)}</li>" for it in items)
            out.append(f"    <ul>\n{lis}\n    </ul>")
        elif b.startswith("@callout"):
            m = re.match(r'@callout\[([^\]]+)\]', b)
            parts = [p.strip() for p in m.group(1).split("|")]
            label = parts[0]; ctext = parts[1] if len(parts) > 1 else ""
            out.append(
                f'    <div class="callout">\n'
                f'      <span class="callout-label">{label}</span>\n'
                f'      <p>{inline(ctext)}</p>\n    </div>')
        elif b.startswith("@image"):
            m = re.match(r'@image\[([^\]]+)\]', b)
            parts = [p.strip() for p in m.group(1).split("|")]
            src = parts[0]; alt = parts[1] if len(parts) > 1 else ""
            cap = parts[2] if len(parts) > 2 else ""
            if cap:
                out.append(
                    f'    <figure class="media-figure">\n'
                    f'      <img class="media-img" src="{src}" alt="{alt}" />\n'
                    f'      <figcaption>{cap}</figcaption>\n    </figure>')
            else:
                out.append(f'    <img class="media-img" src="{src}" alt="{alt}" />')
        else:
            out.append(f"    <p>{inline(b)}</p>")
    return "\n\n".join(out)

# --------------------------------------------------------------------- build

def article_text(page_html):
    """Plain-text of the new page's <article> body, for a verbatim content
    check. This script never edits idea prose; printing it lets the author
    confirm that what goes live is exactly what they wrote — no added or
    reworded sentences."""
    m = re.search(r'<article[^>]*>(.*?)</article>', page_html, re.S)
    body = m.group(1) if m else ""
    body = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', body, flags=re.S)
    txt = re.sub(r'<[^>]+>', '', body)
    return html.unescape(re.sub(r'\n{3,}', '\n\n', txt)).strip()


def do_build(args):
    site_dir = os.path.abspath(args.site)
    output_dir = os.path.abspath(args.output_dir)
    assets = args.assets or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
    template = site_io.read(os.path.join(assets, "page-template.html"))

    data, body = parse_front_matter(site_io.read(args.input))
    for req in ("slug", "title", "category", "summary"):
        if not data.get(req):
            sys.exit(f"Missing required front-matter field: {req}")
    slug, title, cat = data["slug"], data["title"], data["category"]
    section = data.get("section", config.DEFAULT_SECTION)
    conns = data.get("connections", [])
    for c in conns:
        c.setdefault("label", "related to")
        c.setdefault("reverse_label", c["label"])
        if c["target"] == slug:
            sys.exit("A piece cannot connect to itself.")

    cat_label = data.get("category_label", cat.capitalize())
    read_time = data.get("read_time", "")
    tags = data.get("tags", [])
    meta = "".join(f'      <span class="tag-label">{t}</span>\n' for t in tags)
    if read_time:
        meta += f'      <span class="meta-item">{read_time}</span>'
    related = [{"title": site_io.byid_title(site_dir, c["target"]), "label": c["label"],
                "url": f'/{site_io.target_section(site_dir, c["target"])}/{c["target"]}/'} for c in conns]

    section_meta = config.SECTION_DEFAULTS.get(section, config.SECTION_DEFAULTS[config.DEFAULT_SECTION])

    # --- build the new page ------------------------------------------------
    page = template
    page = page.replace("{{TITLE}}", title)
    page = page.replace("{{DESCRIPTION}}", html.escape(data["summary"][:200], quote=True))
    page = page.replace("{{CATEGORY_LABEL}}", cat_label)
    page = page.replace("{{CATEGORY_UPPER}}", cat_label.upper())
    page = page.replace("{{SUMMARY}}", data["summary"])
    page = page.replace("{{SLUG}}", slug)
    page = page.replace("{{SECTION}}", section)
    page = page.replace("{{SECTION_LINK}}", section_meta["link"])
    page = page.replace("{{SECTION_LABEL}}", section_meta["label"])
    page = page.replace("{{META}}", meta.rstrip("\n"))
    page = page.replace("{{ARTICLE}}", render_body(body))
    page = page.replace("{{PIECE_JSON}}", json.dumps({"title": title, "slug": slug}))
    page = page.replace("{{RELATED_JSON}}", json.dumps(related))
    page = page.replace("{{CONNECTIONS}}", "")                       # clear placeholder
    page_path = os.path.join(output_dir, section, slug, "index.html")
    site_io.write(page_path, page)                                   # summary now readable
    page = site_io.set_connections(page, site_io.render_connections(related, site_dir, slug))
    site_io.write(page_path, page)

    # --- Open Graph share image (link-unfurl preview) ---------------------
    # Rendered with headless Chrome so the card matches the site's web fonts.
    # Non-fatal: a publish still succeeds if rendering is unavailable.
    og_path = os.path.join(output_dir, "media", "og", f"{slug}.png")
    og_rendered = False
    og_error = None
    try:
        render_og_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "render-og", "scripts")
        sys.path.insert(0, render_og_dir)
        from render_og import render_og
        render_og(title, cat_label.upper(), data["summary"], og_path)
        og_rendered = True
    except Exception as e:
        og_error = str(e)
        print(f"  ⚠ could not render OG image for {slug}: {e}")

    node_summary = site_io.strip_summary(page)

    manifest = {
        "slug": slug,
        "title": title,
        "category": cat,
        "category_label": cat_label,
        "category_color": data.get("category_color"),
        "summary": data["summary"],
        "tags": tags,
        "read_time": read_time,
        "section": section,
        "connections": conns,
        "related": related,
        "node_summary": node_summary,
        "page_path": os.path.relpath(page_path, output_dir).replace(os.sep, "/"),
        "og_path": os.path.relpath(og_path, output_dir).replace(os.sep, "/") if og_rendered else None,
        "og_error": og_error,
    }
    site_io.write(os.path.join(output_dir, "idea.json"), json.dumps(manifest, indent=2))

    # --- media presence check ---------------------------------------------
    missing = []
    for src in re.findall(r'src="(/media/[^"]+)"', page):
        if not os.path.exists(os.path.join(output_dir, src.lstrip("/"))) and \
           not os.path.exists(os.path.join(site_dir, src.lstrip("/"))):
            missing.append(src)

    print(f"\n=== build-page: built /{section}/{slug}/ ===")
    print(f"  page   -> {manifest['page_path']}")
    print(f"  og     -> {manifest['og_path'] or '(not rendered: ' + str(og_error) + ')'}")
    print(f"  idea.json -> idea.json")
    if missing:
        print("\n  ⚠ referenced media not found (add to site/media/ first):")
        for x in missing:
            print(f"      {x}")
    print("\n--- new page body, exactly as it will publish (verbatim check) ---")
    print("Confirm this is word-for-word the author's text — no added or")
    print("reworded sentences — before running update-indexes.\n")
    print(article_text(page))


def main():
    ap = argparse.ArgumentParser(description="Build a new idea page from a publish-idea input file.")
    ap.add_argument("--input", required=True)
    ap.add_argument("--site", default="./site", help="Existing site tree, read-only, used to resolve connection target titles/summaries.")
    ap.add_argument("--output-dir", default="./.publish-stage", help="Where to write the new page + OG image + idea.json.")
    ap.add_argument("--assets", default=None)
    args = ap.parse_args()
    do_build(args)


if __name__ == "__main__":
    main()
