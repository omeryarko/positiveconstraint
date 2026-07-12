#!/usr/bin/env python3
"""
publish.py — deterministic site surgery for publishing a new idea to
positiveconstraint.com. Driven by SKILL.md; see references/input-format.md.

Two subcommands:
  stage  --input piece.md --site ./site --stage ./.publish-stage
         Builds the new page + all edits into a *copy* of the site (the stage),
         writes manifest.json, and prints a diff summary. Nothing goes live.
  deploy --stage ./.publish-stage --site ./site
         Backs up every remote file it will overwrite, then FTP-uploads the
         manifest. Reads FTP creds from env (PC_FTP_HOST/USER/PASS).

Design notes
------------
* Single content tree: /ideas/<slug>/index.html. (/pieces was deleted.)
* Map + ideas-index counts are always recomputed from NODES/EDGES so the
  currently-stale "12 ideas / 34 connections" header self-corrects.
* A page's connection cards are rendered from its RELATED[] JS array, which is
  the same data the markdown-export buttons use — so the visible cards and the
  export can never disagree.
* Edits are surgical: we only rewrite the specific nodes/edges/cards that
  actually change, leaving the rest of each file byte-identical for a clean diff.
"""
import argparse, json, os, re, shutil, sys, html, ftplib, datetime, difflib

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
        if b.startswith("### "):
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
            blk = ["    <blockquote>", f"      <p>{inline(' '.join(quote))}</p>"]
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

# ------------------------------------------------------------------- helpers

def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)

def js_array(content, var):
    m = re.search(r'var %s = (\[.*?\]|\{.*?\});' % var, content, re.S)
    return json.loads(m.group(1))

def set_js(content, var, value):
    return re.sub(r'(var %s = )(\[.*?\]|\{.*?\})(;)' % var,
                  lambda m: m.group(1) + json.dumps(value) + m.group(3),
                  content, count=1, flags=re.S)

def strip_summary(page_html, limit=140):
    m = re.search(r'<p class="piece-summary">(.*?)</p>', page_html, re.S)
    if not m:
        return ""
    txt = re.sub(r'<[^>]+>', '', m.group(1))
    txt = html.unescape(re.sub(r'\s+', ' ', txt)).strip()
    if len(txt) <= limit:
        return txt
    # cut on a word boundary and add an ellipsis, never mid-word
    cut = txt[:limit].rsplit(" ", 1)[0].rstrip(",.;:—- ")
    return cut + "…"

CAT_COLORS = {"concepts": "#FF4040", "frameworks": "#FF4040",
              "services": "var(--color-text-primary)",
              "work": "var(--color-text-secondary)",
              "about": "var(--color-text-tertiary)"}

def cat_color(cat, colors):
    return colors.get(cat) or CAT_COLORS.get(cat) or "var(--color-text-secondary)"

# ---------------------------------------------------- connection card render

# How many related-idea cards a standalone page shows. The map/graph keeps every
# edge; the page just caps the visible cards to stay clean.
MAX_CARDS = 4

def render_connections(related, stage, self_slug=None):
    """Render the <section class="connections"> inner HTML from a RELATED list:
    one flat "Related Ideas" group, up to MAX_CARDS cards, no relationship labels."""
    if not related:
        return ""
    cards = []
    for r in related[:MAX_CARDS]:
        slug = r["url"].strip("/").split("/")[-1]
        summ = strip_summary(read(os.path.join(stage, "ideas", slug, "index.html")))
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
    # no section present (e.g. a page that had no related ideas) — add one back
    # right before the closing </main>.
    section = '\n  <section class="connections">\n' + inner + '\n  </section>\n'
    return page_html.replace("</main>", section + "</main>", 1)

def rebuild_connections(page, related, stage):
    """Set a page's connections section to the flat, capped render of its RELATED."""
    return set_connections(page, render_connections(related, stage))

# --------------------------------------------------------------------- stage

def add_llms_entry(stage, slug, title, cat, summary):
    """Insert one bullet into /llms.txt under the section matching the category.
    Surgical, like the ideas-index card insert: leaves the rest of the file
    untouched. No-op if the site has no llms.txt or the slug is already listed."""
    path = os.path.join(stage, "llms.txt")
    if not os.path.exists(path):
        return
    section = {
        "concepts": "## Core ideas",
        "frameworks": "## Core ideas",
        "reflections": "## Core ideas",
        "services": "## Practice & work",
        "work": "## Practice & work",
    }.get(cat, "## Optional")
    txt = read(path)
    if f"/ideas/{slug}/)" in txt:
        return
    desc = " ".join(summary.split())
    line = f"- [{title}](https://positiveconstraint.com/ideas/{slug}/): {desc}\n"
    lines = txt.splitlines(keepends=True)
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == section)
    except StopIteration:
        return
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    ins = end
    while ins > start + 1 and lines[ins - 1].strip() == "":
        ins -= 1
    lines.insert(ins, line)
    write(path, "".join(lines))


def update_sitemap(stage, slug, cat):
    """Keep /sitemap.xml in step with a publish: append a <url> for the new page
    and refresh <lastmod> on the surfaces every publish rewrites (home, ideas
    index, map). Surgical string edits in the same spirit as add_llms_entry;
    no-op if the site has no sitemap.xml, idempotent on the slug."""
    path = os.path.join(stage, "sitemap.xml")
    if not os.path.exists(path):
        return
    today = datetime.date.today().isoformat()
    txt = read(path)

    # bump lastmod on the always-touched surfaces
    for surface in ("https://positiveconstraint.com/",
                    "https://positiveconstraint.com/ideas/",
                    "https://positiveconstraint.com/map/"):
        txt = re.sub(
            r'(<loc>%s</loc>\s*<lastmod>)[^<]*(</lastmod>)' % re.escape(surface),
            r'\g<1>%s\g<2>' % today, txt, count=1)

    # add the new page's <url> once, just before </urlset>
    loc = f"https://positiveconstraint.com/ideas/{slug}/"
    if f"<loc>{loc}</loc>" not in txt:
        priority = "0.6" if cat == "work" else "0.7"
        entry = (f"  <url>\n"
                 f"    <loc>{loc}</loc>\n"
                 f"    <lastmod>{today}</lastmod>\n"
                 f"    <priority>{priority}</priority>\n"
                 f"  </url>\n")
        txt = txt.replace("</urlset>", entry + "</urlset>", 1)

    write(path, txt)


def do_stage(args):
    site, stage = os.path.abspath(args.site), os.path.abspath(args.stage)
    assets = args.assets or os.path.join(os.path.dirname(__file__), "..", "assets")
    template = read(os.path.join(assets, "page-template.html"))

    data, body = parse_front_matter(read(args.input))
    for req in ("slug", "title", "category", "summary"):
        if not data.get(req):
            sys.exit(f"Missing required front-matter field: {req}")
    slug, title, cat = data["slug"], data["title"], data["category"]
    conns = data.get("connections", [])
    for c in conns:
        c.setdefault("label", "related to")
        c.setdefault("reverse_label", c["label"])
        if c["target"] == slug:
            sys.exit("A piece cannot connect to itself.")

    # fresh stage as a copy of the live mirror
    if os.path.exists(stage):
        shutil.rmtree(stage)
    shutil.copytree(site, stage)

    cat_label = data.get("category_label", cat.capitalize())
    read_time = data.get("read_time", "")
    tags = data.get("tags", [])
    meta = "".join(f'      <span class="tag-label">{t}</span>\n' for t in tags)
    if read_time:
        meta += f'      <span class="meta-item">{read_time}</span>'
    related = [{"title": byid_title(stage, c["target"]), "label": c["label"],
                "url": f'/ideas/{c["target"]}/'} for c in conns]

    # --- build the new page ------------------------------------------------
    page = template
    page = page.replace("{{TITLE}}", title)
    page = page.replace("{{DESCRIPTION}}", html.escape(data["summary"][:200], quote=True))
    page = page.replace("{{CATEGORY_LABEL}}", cat_label)
    page = page.replace("{{CATEGORY_UPPER}}", cat_label.upper())
    page = page.replace("{{SUMMARY}}", data["summary"])
    page = page.replace("{{META}}", meta.rstrip("\n"))
    page = page.replace("{{ARTICLE}}", render_body(body))
    page = page.replace("{{PIECE_JSON}}", json.dumps({"title": title, "slug": slug}))
    page = page.replace("{{RELATED_JSON}}", json.dumps(related))
    page = page.replace("{{CONNECTIONS}}", "")                       # clear placeholder
    write(os.path.join(stage, "ideas", slug, "index.html"), page)   # summary now readable
    page = set_connections(page, render_connections(related, stage, slug))
    write(os.path.join(stage, "ideas", slug, "index.html"), page)

    # --- reverse connections on targets -----------------------------------
    # The visible cards are always a pure function of a page's RELATED[:4], so we
    # re-render the whole connections section rather than splice one card in.
    target_related_len = {}
    for c in conns:
        tpath = os.path.join(stage, "ideas", c["target"], "index.html")
        tp = read(tpath)
        trel = js_array(tp, "RELATED")
        # idempotent: only add the reverse link if this slug isn't already linked,
        # so a re-run (re-stage/re-deploy) doesn't duplicate it.
        if not any(r.get("url") == f"/ideas/{slug}/" for r in trel):
            trel.append({"title": title, "label": c["reverse_label"], "url": f"/ideas/{slug}/"})
            tp = set_js(tp, "RELATED", trel)
            tp = rebuild_connections(tp, trel, stage)
            write(tpath, tp)
        target_related_len[c["target"]] = len(trel)

    # --- map: nodes, edges, colors, counts --------------------------------
    map_path = os.path.join(stage, "map", "index.html")
    mp = read(map_path)
    nodes = js_array(mp, "NODES")
    edges = js_array(mp, "EDGES")
    colors = js_array(mp, "COLORS")
    clabels = js_array(mp, "COLORS_LABEL")

    if not any(n.get("id") == slug for n in nodes):
        nodes.append({"id": slug, "title": title, "category": cat,
                      "summary": strip_summary(page)})
    existing = {tuple(sorted(e)) for e in edges}
    for c in conns:
        key = tuple(sorted([slug, c["target"]]))
        if key not in existing:
            edges.append([slug, c["target"]]); existing.add(key)
    if cat not in colors:
        colors[cat] = data.get("category_color", cat_color(cat, colors))
    if cat not in clabels:
        clabels[cat] = cat_label

    mp = set_js(mp, "NODES", nodes)
    mp = set_js(mp, "EDGES", edges)
    mp = set_js(mp, "COLORS", colors)
    mp = set_js(mp, "COLORS_LABEL", clabels)
    n_nodes, n_edges = len(nodes), len(edges)
    mp = re.sub(r'(<div class="map-meta">)[^<]*(</div>)',
                rf'\g<1>{n_nodes} ideas · {n_edges} connections\2', mp, count=1)
    # add a map filter pill if this is a brand-new category
    if not re.search(r"setFilter\('%s'" % re.escape(cat), mp):
        pill = (f'<button class="filter-pill" onclick="setFilter(\'{cat}\', this)">'
                f'<span class="filter-dot" style="background:{cat_color(cat, colors)}"></span>'
                f'{cat_label}</button>')
        mp = mp.replace("</section>", pill + "</section>", 1)
    write(map_path, mp)

    # --- homepage live mini-map: nodes, edges, colors, counts -------------
    # The homepage (index.html) embeds the same graph under MAP_* var names.
    # Keep it in lockstep with the map so the two never diverge. This only
    # touches the graph data + its meta count — the curated "Start here"
    # featured cards and homepage category pills stay author-controlled.
    home_path = os.path.join(stage, "index.html")
    if os.path.exists(home_path):
        hp = read(home_path)
        if re.search(r'var MAP_NODES = ', hp):
            hnodes = js_array(hp, "MAP_NODES")
            hedges = js_array(hp, "MAP_EDGES")
            hcolors = js_array(hp, "MAP_COLORS")
            hlabels = js_array(hp, "MAP_LABELS")
            if not any(n.get("id") == slug for n in hnodes):
                hnodes.append({"id": slug, "title": title, "category": cat,
                               "summary": strip_summary(page)})
            hexisting = {tuple(sorted(e)) for e in hedges}
            for c in conns:
                key = tuple(sorted([slug, c["target"]]))
                if key not in hexisting:
                    hedges.append([slug, c["target"]]); hexisting.add(key)
            if cat not in hcolors:
                hcolors[cat] = data.get("category_color", cat_color(cat, hcolors))
            if cat not in hlabels:
                hlabels[cat] = cat_label
            hp = set_js(hp, "MAP_NODES", hnodes)
            hp = set_js(hp, "MAP_EDGES", hedges)
            hp = set_js(hp, "MAP_COLORS", hcolors)
            hp = set_js(hp, "MAP_LABELS", hlabels)
            hp = re.sub(r'(<div class="map-live-meta">)[^<]*(</div>)',
                        rf'\g<1>{len(hnodes)} ideas · {len(hedges)} connections\2',
                        hp, count=1)
            write(home_path, hp)

    # --- ideas index: card, counts, filter pill ---------------------------
    idx_path = os.path.join(stage, "ideas", "index.html")
    idx = read(idx_path)
    col = cat_color(cat, colors)
    # a card's "N connections" mirrors that page's RELATED length (outbound cards),
    # which is how the live site counts them — not graph degree.
    card = (f'<a href="/ideas/{slug}/" class="piece-card" data-category="{cat}">'
            f'<span class="piece-card-tag" style="color:{col}">{cat_label}</span>'
            f'<div class="piece-card-title">{title}</div>'
            f'<div class="piece-card-summary">{strip_summary(page)}</div>'
            f'<div class="piece-card-meta"><span class="piece-card-dot" '
            f'style="background:{col}"></span>{len(related)} connections</div></a>')
    # idempotent: don't insert a second card for this slug on a re-run
    if f'href="/ideas/{slug}/" class="piece-card"' not in idx:
        idx = idx.replace("</a>\n  </div>\n</section>", "</a>" + card + "\n  </div>\n</section>", 1)
    idx = re.sub(r'(<div class="pieces-meta">)[^<]*(</div>)',
                 rf'\g<1>{n_nodes} ideas · {n_edges} connections\2', idx, count=1)
    # bump connection counts on the affected target cards to their new RELATED length
    for c in conns:
        idx = bump_card_count(idx, c["target"], target_related_len[c["target"]])
    # per-category filter pill count — counted from the ideas index's own cards,
    # not the map's NODES, because the two can disagree on a node's category
    # (e.g. positive-constraint is "frameworks" on the map but "concepts" here).
    cat_count = idx.count('data-category="%s"' % cat)
    if re.search(r"data-cat=\"%s\"" % re.escape(cat), idx):
        idx = re.sub(r'(data-cat="%s".*?</span>)[^<·]*·\s*\d+' % re.escape(cat),
                     rf'\g<1>{cat_label} · {cat_count}', idx, count=1, flags=re.S)
    else:
        pill = (f'<button class="filter-pill" data-cat="{cat}" '
                f'onclick="filterByCategory(\'{cat}\', this)">'
                f'<span class="filter-dot" style="background:{col}"></span>'
                f'{cat_label} · {cat_count}</button>')
        idx = idx.replace('</section>\n\n<section class="pieces-list">',
                          pill + '</section>\n\n<section class="pieces-list">', 1)
    write(idx_path, idx)

    # --- llms.txt: AI-oriented index of ideas -----------------------------
    add_llms_entry(stage, slug, title, cat, data["summary"])

    # --- sitemap.xml: add the new page, refresh touched surfaces -----------
    update_sitemap(stage, slug, cat)

    # --- media presence check ---------------------------------------------
    missing = []
    for src in re.findall(r'src="(/media/[^"]+)"', page):
        if not os.path.exists(os.path.join(stage, src.lstrip("/"))):
            missing.append(src)

    manifest = build_manifest(site, stage)
    write(os.path.join(stage, "manifest.json"), json.dumps(manifest, indent=2))
    print_summary(site, stage, manifest, missing, n_nodes, n_edges, article_text(page))

def article_text(page_html):
    """Plain-text of the new page's <article> body, for a verbatim content check.
    The script never edits idea prose; printing it lets the author confirm that
    what goes live is exactly what they wrote — no added or reworded sentences."""
    m = re.search(r'<article[^>]*>(.*?)</article>', page_html, re.S)
    body = m.group(1) if m else ""
    body = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', body, flags=re.S)
    txt = re.sub(r'<[^>]+>', '', body)
    return html.unescape(re.sub(r'\n{3,}', '\n\n', txt)).strip()

def byid_title(stage, slug):
    p = os.path.join(stage, "ideas", slug, "index.html")
    if not os.path.exists(p):
        sys.exit(f"Connection target '{slug}' has no page at /ideas/{slug}/.")
    m = re.search(r'<h1>(.*?)</h1>', read(p), re.S)
    return re.sub(r'<[^>]+>', '', m.group(1)).strip() if m else slug

def bump_card_count(idx, slug, count):
    def repl(m):
        card = m.group(0)
        return re.sub(r'\d+ connections', f'{count} connections', card)
    return re.sub(r'<a href="/ideas/%s/".*?</a>' % re.escape(slug), repl, idx, count=1, flags=re.S)

def build_manifest(site, stage):
    changed = []
    for root, _, files in os.walk(stage):
        for f in files:
            if f == "manifest.json":
                continue
            sp = os.path.join(root, f)
            rel = os.path.relpath(sp, stage)
            op = os.path.join(site, rel)
            new = not os.path.exists(op)
            if new or read_bytes(sp) != read_bytes(op):
                changed.append({"path": rel.replace(os.sep, "/"), "new": new})
    return changed

def read_bytes(p):
    with open(p, "rb") as f:
        return f.read()

def print_summary(site, stage, manifest, missing, n_nodes, n_edges, new_body=None):
    print("\n=== publish-idea: staged changes ===")
    print(f"map/ideas counts -> {n_nodes} ideas · {n_edges} connections")
    print(f"{len(manifest)} file(s) will be uploaded:\n")
    for m in manifest:
        tag = "NEW " if m["new"] else "edit"
        print(f"  [{tag}] /{m['path']}")
    if missing:
        print("\n  ⚠ referenced media not found in stage (add to site/media/ first):")
        for x in missing:
            print(f"      {x}")
    print("\n--- unified diffs (edited files) ---")
    for m in manifest:
        if m["new"]:
            continue
        a = read(os.path.join(site, m["path"])).splitlines()
        b = read(os.path.join(stage, m["path"])).splitlines()
        d = list(difflib.unified_diff(a, b, lineterm="", n=1,
                                      fromfile="live/" + m["path"], tofile="stage/" + m["path"]))
        print("\n".join(d[:80]))
        if len(d) > 80:
            print(f"  ... ({len(d)-80} more diff lines)")
    if new_body is not None:
        print("\n--- new page body, exactly as it will publish (verbatim check) ---")
        print("Confirm this is word-for-word the author's text — no added or")
        print("reworded sentences — before deploying.\n")
        print(new_body)
    print("\nReview above, then run:  publish.py deploy --stage", stage)

# -------------------------------------------------------------------- deploy

def do_deploy(args):
    stage, site = os.path.abspath(args.stage), os.path.abspath(args.site)
    manifest = json.loads(read(os.path.join(stage, "manifest.json")))
    host = os.environ.get("PC_FTP_HOST", "198.177.120.17")
    user = os.environ.get("PC_FTP_USER"); pw = os.environ.get("PC_FTP_PASS")
    if not (user and pw):
        sys.exit("Set PC_FTP_USER and PC_FTP_PASS in the environment before deploy.")
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = os.path.join(stage, "backup-" + stamp)

    ftp = ftplib.FTP(); ftp.connect(host, 21, timeout=60); ftp.login(user, pw); ftp.set_pasv(True)
    rollback = {"new": [], "overwritten": []}
    for m in manifest:
        remote = "/" + m["path"]
        ensure_dirs(ftp, remote)
        if not m["new"]:                       # back up the live copy first
            bpath = os.path.join(backup, m["path"])
            os.makedirs(os.path.dirname(bpath), exist_ok=True)
            try:
                with open(bpath, "wb") as f:
                    ftp.retrbinary("RETR " + remote, f.write)
                rollback["overwritten"].append(m["path"])
            except ftplib.error_perm:
                pass
        else:
            rollback["new"].append(m["path"])
        with open(os.path.join(stage, m["path"]), "rb") as f:
            ftp.storbinary("STOR " + remote, f)
        print("uploaded", remote)
    ftp.quit()
    write(os.path.join(backup, "rollback.json"), json.dumps(rollback, indent=2))
    # refresh the local mirror so future runs diff against the new live state
    for m in manifest:
        dst = os.path.join(site, m["path"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(stage, m["path"]), dst)
    print(f"\nDone. Backup of overwritten files: {backup}")

def ensure_dirs(ftp, remote):
    parts = remote.strip("/").split("/")[:-1]
    path = ""
    for p in parts:
        path += "/" + p
        try:
            ftp.mkd(path)
        except ftplib.error_perm:
            pass

# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="Publish a new idea to positiveconstraint.com")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("stage"); s.add_argument("--input", required=True)
    s.add_argument("--site", default="./site"); s.add_argument("--stage", default="./.publish-stage")
    s.add_argument("--assets", default=None); s.set_defaults(func=do_stage)
    d = sub.add_parser("deploy"); d.add_argument("--stage", default="./.publish-stage")
    d.add_argument("--site", default="./site"); d.set_defaults(func=do_deploy)
    args = ap.parse_args(); args.func(args)

if __name__ == "__main__":
    main()
