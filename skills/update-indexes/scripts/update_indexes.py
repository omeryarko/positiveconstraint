#!/usr/bin/env python3
"""update_indexes.py — wire a newly built idea page into the rest of the site.

Takes the idea.json manifest that build-page produced and, inside --site-dir
(normally a staged copy of the site that build-page already wrote the new
page into):

  * wires reverse connections onto every connection target's page (RELATED
    array + rendered connections section),
  * updates the knowledge map (map/index.html: NODES/EDGES/COLORS/COLORS_LABEL
    + header count + filter pill for a brand-new category),
  * updates the homepage's live mini-map (index.html: MAP_NODES/MAP_EDGES/
    MAP_COLORS/MAP_LABELS + its own count) so it never drifts from /map/,
  * updates the ideas index (ideas/index.html: new card, bumped connection
    counts on affected targets, header count, filter pill),
  * appends an /llms.txt bullet under the right section,
  * appends a /sitemap.xml <url> and refreshes <lastmod> on always-touched
    surfaces,
  * writes manifest.json (new-vs-edited file list) for deploy-site to apply.

All edits are surgical string/regex edits on top of what's already there, so
existing content stays byte-identical except where it must change. Everything
here is deterministic; the only judgment call (which ideas to connect) already
happened when the input file's front-matter `connections:` list was written.

CLI:
    python update_indexes.py --idea-json idea.json --site-dir ./site [--live-site ./site]

--live-site is optional and only used to print a unified diff / build
manifest.json against the pre-edit tree for human review before deploy. Pass
it when --site-dir is a staged copy (the normal publish-idea workflow); omit
it (or point it at --site-dir) to skip the diff and just apply the edits.
"""
import argparse
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '_lib'))
import config
import site_io


def add_llms_entry(site_dir, slug, title, cat, summary, section="ideas"):
    """Insert one bullet into /llms.txt under the section matching the
    category. Surgical, like the ideas-index card insert: leaves the rest of
    the file untouched. No-op if the site has no llms.txt or the slug is
    already listed."""
    path = os.path.join(site_dir, "llms.txt")
    if not os.path.exists(path):
        return
    section_header = config.LLMS_TXT_CATEGORIES.get(cat, config.LLMS_TXT_DEFAULT_SECTION)
    txt = site_io.read(path)
    if f"/{section}/{slug}/)" in txt:
        return
    desc = " ".join(summary.split())
    line = f"- [{title}](https://positiveconstraint.com/{section}/{slug}/): {desc}\n"
    lines = txt.splitlines(keepends=True)
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == section_header)
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
    site_io.write(path, "".join(lines))


def update_sitemap(site_dir, slug, cat, section="ideas"):
    """Keep /sitemap.xml in step with a publish: append a <url> for the new
    page and refresh <lastmod> on the surfaces every publish rewrites (home,
    ideas index, map). No-op if the site has no sitemap.xml, idempotent on
    the slug."""
    path = os.path.join(site_dir, "sitemap.xml")
    if not os.path.exists(path):
        return
    import datetime
    today = datetime.date.today().isoformat()
    txt = site_io.read(path)

    surfaces = list(config.SITEMAP_ALWAYS_TOUCHED_SURFACES)
    if section == "braintail":
        surfaces.append(config.SITEMAP_BRAINTAIL_SURFACE)
    for surface in surfaces:
        txt = re.sub(
            r'(<loc>%s</loc>\s*<lastmod>)[^<]*(</lastmod>)' % re.escape(surface),
            r'\g<1>%s\g<2>' % today, txt, count=1)

    loc = f"{config.CANONICAL_URL_PREFIX}/{section}/{slug}/"
    if f"<loc>{loc}</loc>" not in txt:
        priority = config.SITEMAP_PRIORITIES.get(cat, config.SITEMAP_PRIORITIES["_default"])
        entry = (f"  <url>\n"
                 f"    <loc>{loc}</loc>\n"
                 f"    <lastmod>{today}</lastmod>\n"
                 f"    <priority>{priority}</priority>\n"
                 f"  </url>\n")
        txt = txt.replace("</urlset>", entry + "</urlset>", 1)

    site_io.write(path, txt)


def bump_card_count(idx, slug, count):
    def repl(m):
        card = m.group(0)
        return re.sub(r'\d+ connections', f'{count} connections', card)
    return re.sub(r'<a href="/(?:ideas|braintail)/%s/".*?</a>' % re.escape(slug), repl, idx, count=1, flags=re.S)


def do_update(args):
    site_dir = os.path.abspath(args.site_dir)
    idea = json.loads(site_io.read(args.idea_json))

    slug, title, cat = idea["slug"], idea["title"], idea["category"]
    cat_label = idea["category_label"]
    section = idea.get("section", config.DEFAULT_SECTION)
    conns = idea.get("connections", [])
    related = idea.get("related", [])
    node_summary = idea["node_summary"]

    page_path = os.path.join(site_dir, section, slug, "index.html")
    if not os.path.exists(page_path):
        sys.exit(f"Expected the new page at {page_path} (run build-page into --site-dir first).")

    # --- reverse connections on targets -----------------------------------
    # The visible cards are always a pure function of a page's RELATED[:N],
    # so we re-render the whole connections section rather than splice one
    # card in.
    target_related_len = {}
    for c in conns:
        tsec = site_io.target_section(site_dir, c["target"])
        tpath = os.path.join(site_dir, tsec, c["target"], "index.html")
        tp = site_io.read(tpath)
        trel = site_io.js_array(tp, "RELATED")
        # idempotent: only add the reverse link if this slug isn't already
        # linked, so a re-run (re-build/re-update/re-deploy) doesn't duplicate it.
        if not any(r.get("url") == f"/{section}/{slug}/" for r in trel):
            trel.append({"title": title, "label": c["reverse_label"], "url": f"/{section}/{slug}/"})
            tp = site_io.set_js(tp, "RELATED", trel)
            tp = site_io.rebuild_connections(tp, trel, site_dir)
            site_io.write(tpath, tp)
        target_related_len[c["target"]] = len(trel)

    # --- map: nodes, edges, colors, counts --------------------------------
    map_path = os.path.join(site_dir, "map", "index.html")
    mp = site_io.read(map_path)
    nodes = site_io.js_array(mp, "NODES")
    edges = site_io.js_array(mp, "EDGES")
    colors = site_io.js_array(mp, "COLORS")
    clabels = site_io.js_array(mp, "COLORS_LABEL")
    for n in nodes:
        n.setdefault("section", "ideas")

    if not any(n.get("id") == slug for n in nodes):
        nodes.append({"id": slug, "title": title, "category": cat,
                      "summary": node_summary, "section": section})
    existing = {tuple(sorted(e)) for e in edges}
    for c in conns:
        key = tuple(sorted([slug, c["target"]]))
        if key not in existing:
            edges.append([slug, c["target"]]); existing.add(key)
    if cat not in colors:
        colors[cat] = idea.get("category_color") or site_io.cat_color(cat, colors)
    if cat not in clabels:
        clabels[cat] = cat_label

    mp = site_io.set_js(mp, "NODES", nodes)
    mp = site_io.set_js(mp, "EDGES", edges)
    mp = site_io.set_js(mp, "COLORS", colors)
    mp = site_io.set_js(mp, "COLORS_LABEL", clabels)
    n_nodes, n_edges = len(nodes), len(edges)
    mp = re.sub(r'(<div class="map-meta">)[^<]*(</div>)',
                rf'\g<1>{n_nodes} ideas · {n_edges} connections\2', mp, count=1)
    # add a map filter pill if this is a brand-new category
    if not re.search(r"setFilter\('%s'" % re.escape(cat), mp):
        pill = (f'<button class="filter-pill" onclick="setFilter(\'{cat}\', this)">'
                f'<span class="filter-dot" style="background:{site_io.cat_color(cat, colors)}"></span>'
                f'{cat_label}</button>')
        mp = mp.replace("</section>", pill + "</section>", 1)
    site_io.write(map_path, mp)

    # --- homepage live mini-map: nodes, edges, colors, counts -------------
    # The homepage (index.html) embeds the same graph under MAP_* var names.
    # Keep it in lockstep with the map so the two never diverge. This only
    # touches the graph data + its meta count — the curated "Start here"
    # featured cards and homepage category pills stay author-controlled.
    home_path = os.path.join(site_dir, "index.html")
    if os.path.exists(home_path):
        hp = site_io.read(home_path)
        if re.search(r'var MAP_NODES = ', hp):
            hnodes = site_io.js_array(hp, "MAP_NODES")
            hedges = site_io.js_array(hp, "MAP_EDGES")
            hcolors = site_io.js_array(hp, "MAP_COLORS")
            hlabels = site_io.js_array(hp, "MAP_LABELS")
            for n in hnodes:
                n.setdefault("section", "ideas")
            if not any(n.get("id") == slug for n in hnodes):
                hnodes.append({"id": slug, "title": title, "category": cat,
                               "summary": node_summary, "section": section})
            hexisting = {tuple(sorted(e)) for e in hedges}
            for c in conns:
                key = tuple(sorted([slug, c["target"]]))
                if key not in hexisting:
                    hedges.append([slug, c["target"]]); hexisting.add(key)
            if cat not in hcolors:
                hcolors[cat] = idea.get("category_color") or site_io.cat_color(cat, hcolors)
            if cat not in hlabels:
                hlabels[cat] = cat_label
            hp = site_io.set_js(hp, "MAP_NODES", hnodes)
            hp = site_io.set_js(hp, "MAP_EDGES", hedges)
            hp = site_io.set_js(hp, "MAP_COLORS", hcolors)
            hp = site_io.set_js(hp, "MAP_LABELS", hlabels)
            hp = re.sub(r'(<div class="map-live-meta">)[^<]*(</div>)',
                        rf'\g<1>{len(hnodes)} ideas · {len(hedges)} connections\2',
                        hp, count=1)
            site_io.write(home_path, hp)

    # --- ideas index: card, counts, filter pill ---------------------------
    idx_path = os.path.join(site_dir, "ideas", "index.html")
    idx = site_io.read(idx_path)
    col = site_io.cat_color(cat, colors)
    # a card's "N connections" mirrors that page's RELATED length (outbound
    # cards), which is how the live site counts them — not graph degree.
    card = (f'<a href="/{section}/{slug}/" class="piece-card" data-category="{cat}">'
            f'<span class="piece-card-tag" style="color:{col}">{cat_label}</span>'
            f'<div class="piece-card-title">{title}</div>'
            f'<div class="piece-card-summary">{node_summary}</div>'
            f'<div class="piece-card-meta"><span class="piece-card-dot" '
            f'style="background:{col}"></span>{len(related)} connections</div></a>')
    # idempotent: don't insert a second card for this slug on a re-run
    if f'href="/{section}/{slug}/" class="piece-card"' not in idx:
        idx = idx.replace("</a>\n  </div>\n</section>", "</a>" + card + "\n  </div>\n</section>", 1)
    idx = re.sub(r'(<div class="pieces-meta">)[^<]*(</div>)',
                 rf'\g<1>{n_nodes} ideas · {n_edges} connections\2', idx, count=1)
    # bump connection counts on the affected target cards to their new
    # RELATED length
    for c in conns:
        idx = bump_card_count(idx, c["target"], target_related_len[c["target"]])
    # per-category filter pill count — counted from the ideas index's own
    # cards, not the map's NODES, because the two can disagree on a node's
    # category (e.g. positive-constraint is "frameworks" on the map but
    # "concepts" here).
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
    site_io.write(idx_path, idx)

    # --- llms.txt: AI-oriented index of ideas -----------------------------
    add_llms_entry(site_dir, slug, title, cat, idea["summary"], section)

    # --- sitemap.xml: add the new page, refresh touched surfaces -----------
    update_sitemap(site_dir, slug, cat, section)

    # --- manifest + diff summary for human review --------------------------
    live_site = os.path.abspath(args.live_site) if args.live_site else None
    manifest = None
    if live_site and os.path.isdir(live_site) and os.path.normpath(live_site) != os.path.normpath(site_dir):
        manifest = site_io.build_manifest(live_site, site_dir)
        site_io.write(os.path.join(site_dir, "manifest.json"), json.dumps(manifest, indent=2))
        print_summary(live_site, site_dir, manifest, n_nodes, n_edges)
    else:
        print(f"\n=== update-indexes: applied edits in {site_dir} ===")
        print(f"map/ideas counts -> {n_nodes} ideas · {n_edges} connections")
        print("(no --live-site given, or it matches --site-dir: skipped diff/manifest.json)")


def print_summary(live_site, site_dir, manifest, n_nodes, n_edges):
    print("\n=== update-indexes: staged changes ===")
    print(f"map/ideas counts -> {n_nodes} ideas · {n_edges} connections")
    print(f"{len(manifest)} file(s) will be uploaded:\n")
    for m in manifest:
        tag = "NEW " if m["new"] else "edit"
        print(f"  [{tag}] /{m['path']}")
    print("\n--- unified diffs (edited files) ---")
    for m in manifest:
        if m["new"]:
            continue
        a = site_io.read(os.path.join(live_site, m["path"])).splitlines()
        b = site_io.read(os.path.join(site_dir, m["path"])).splitlines()
        d = list(difflib.unified_diff(a, b, lineterm="", n=1,
                                      fromfile="live/" + m["path"], tofile="stage/" + m["path"]))
        print("\n".join(d[:80]))
        if len(d) > 80:
            print(f"  ... ({len(d)-80} more diff lines)")
    print("\nReview above (and the build-page verbatim check), then run: deploy.py --stage-dir", site_dir)


def main():
    ap = argparse.ArgumentParser(description="Wire a newly built idea page into the map/homepage/ideas-index/llms.txt/sitemap.xml.")
    ap.add_argument("--idea-json", required=True, help="idea.json produced by build-page.")
    ap.add_argument("--site-dir", required=True, help="Site tree to edit (normally a staged copy that already has the new page from build-page).")
    ap.add_argument("--live-site", default="./site", help="Pre-edit tree to diff --site-dir against for review. Pass the same path as --site-dir (or omit/blank) to skip.")
    args = ap.parse_args()
    do_update(args)


if __name__ == "__main__":
    main()
