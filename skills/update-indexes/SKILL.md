---
name: update-indexes
description: >-
  Wire a newly built positiveconstraint.com idea page into the rest of the
  site: reverse connections on every idea it links to, the knowledge map
  (node + edges + counts), the homepage's live mini-map, the ideas index
  (card + counts + filter pill), llms.txt, and sitemap.xml. Use this
  immediately after build-page has written the new page, and before
  deploy-site ships anything — this is also the step that prints the diff
  for human review.
license: MIT
compatibility: >-
  Requires Python 3.6+. No external dependencies beyond the standard library.
metadata:
  author: positiveconstraint
  version: "1.0"
---

# Wire a new idea into the site

`build-page` only writes the one new page. Every *other* file the site keeps
in sync — the map, the homepage mini-map, the ideas index, llms.txt,
sitemap.xml, and the pages this idea connects to — gets updated here,
deterministically, from the `idea.json` manifest `build-page` produced.

**Don't hand-edit any of these files.** Between them they keep a dozen
coupled numbers in sync (per-card connection counts, per-category filter
counts, map node/edge arrays, two header counts) that are easy to get subtly
wrong by hand — that coupling is the entire reason this exists as a script
instead of an editing task.

## Usage

```bash
python3 scripts/update_indexes.py --idea-json ./.publish-stage/idea.json --site-dir ./.publish-stage
```

- `--idea-json` — the `idea.json` that `build-page`'s `build_page.py` just
  wrote.
- `--site-dir` — the tree to edit. This must already contain the new page
  build-page wrote (normally the same staged copy passed as build-page's
  `--output-dir`).
- `--live-site` (default `./site`) — the **pre-edit** tree to diff
  `--site-dir` against, purely for the review printout and `manifest.json`
  that `deploy-site` consumes. Point it at the real live `./site` when
  `--site-dir` is a staged copy (the normal workflow). Pass the same path as
  `--site-dir`, or omit `manifest.json`'s consumer entirely, to skip the diff
  when you're not staging (edits still apply either way).

## What it updates, and how

- **Reverse connections.** For each `{target, reverse_label}` in the new
  idea's `connections`, appends `{title, label: reverse_label, url}` to the
  target page's `RELATED` JS array and re-renders that page's whole
  "Related Ideas" section from the updated array (capped at 4 cards) — never
  splices in a single card, so the visible cards can never drift from the
  array the "Copy as markdown" export reads. Idempotent: re-running against
  an idea that's already wired won't duplicate the reverse link.
- **Knowledge map** (`map/index.html`): adds the new `NODES` entry and any
  new `EDGES`, registers a brand-new category's color/label in
  `COLORS`/`COLORS_LABEL` and adds its filter pill, and rewrites the
  `<div class="map-meta">` header from the live node/edge counts — this
  **self-heals** a stale hardcoded count, it doesn't just increment one.
- **Homepage live mini-map** (`index.html`'s `MAP_NODES`/`MAP_EDGES`/
  `MAP_COLORS`/`MAP_LABELS` + `map-live-meta` count): kept in exact lockstep
  with the map so the two can never diverge. Deliberately leaves the curated
  "Start here" featured cards and homepage category pills alone — those are
  author-picked, not derived.
- **Ideas index** (`ideas/index.html`): appends the new card, bumps the
  `"N connections"` count on every target card this idea connects to (to
  match that target's new `RELATED` length), rewrites the
  `<div class="pieces-meta">` header from live counts, and adds/updates the
  category's filter pill count — counted from the index's own cards, not the
  map's `NODES`, because the two surfaces are allowed to disagree on a node's
  category (see "category quirk" below).
- **llms.txt**: appends one bullet under the section matching the category
  (`concepts`/`frameworks`/`reflections` → "Core ideas",
  `services`/`work` → "Practice & work", `brand-reviews` → "Braintail — Brand
  Reviews", else "Optional"). No-op if the site has no llms.txt; idempotent
  on the slug.
- **sitemap.xml**: appends a `<url>` for the new page (priority `0.7`, or
  `0.6` for `work`) and refreshes `<lastmod>` on the surfaces every publish
  rewrites (home, `/ideas/`, `/map/`, plus `/braintail/` for that section).
  No-op if the site has no sitemap.xml; idempotent on the slug.
  `/robots.txt` (which points crawlers at the sitemap) is static and needs no
  per-publish update.

## Category quirk, preserved on purpose

Positive Constraint is `frameworks` on the map but `concepts` in the ideas
index. This script counts each surface by its own labels rather than forcing
them to agree, so running it on an unrelated idea won't "fix" (i.e. disturb)
that existing mismatch.

## Review output

When `--live-site` points at a different tree than `--site-dir` (the normal
staged workflow), this prints:

- the full list of files that will be uploaded, tagged `NEW` or `edit`,
- unified diffs of every edited file,
- the recomputed map/ideas counts.

Pair this with build-page's **verbatim check** printout (the new page's body,
as plain text) before approving a deploy — that's the one place body-content
drift could have crept in, and this script's own diffs won't show it because
the new page itself is a `NEW` file, not an `edit`.

This step also writes `--site-dir/manifest.json`, the new-vs-edited file list
that `deploy-site` applies onto the live `./site` tree.

## After this

Once the human has reviewed the diff and the verbatim check and approved,
run **deploy-site** pointing `--stage-dir` at the same `--site-dir` used
here.
