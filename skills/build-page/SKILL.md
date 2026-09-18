---
name: build-page
description: >-
  Turn a publish-idea input file (YAML front-matter + lightweight markdown
  body) into a rendered positiveconstraint.com idea page, plus its Open Graph
  share image. Use this as the first mechanical step of publishing a new idea
  — after the input file's front-matter (slug, title, category, summary,
  tags, connections) has been drafted and approved, and before the reverse
  connections / map / homepage / ideas-index / llms.txt / sitemap.xml updates
  that update-indexes handles next.
license: MIT
compatibility: >-
  Requires Python 3.6+. Delegates OG image rendering to the render-og skill
  (Pillow + headless Chrome), which is non-fatal if Chrome is unavailable.
metadata:
  author: positiveconstraint
  version: "1.0"
---

# Build a new idea page

Parses one input file (YAML-ish front-matter + a lightweight markdown
dialect, spec in `references/input-format.md`) and renders it into a full
`assets/page-template.html`-based page: analytics tags, breadcrumb, tags,
the article body converted from markdown, the "Related Ideas" connection
cards, and the `{{PIECE_JSON}}` / `{{RELATED_JSON}}` data the page's
copy/download/share buttons read. It also renders the page's Open Graph
share image via the **render-og** skill.

This script only writes the **new** page. It never touches any other
existing page — no reverse connections, no map, no homepage, no ideas index,
no llms.txt, no sitemap.xml. That's **update-indexes**' job; run it
immediately after this one, before anything ships.

## Content fidelity — read this before drafting the input file

**The author's words are the author's.** This is a hard rule, not a
preference. The body of the idea is theirs; reproduce it *verbatim*. When
converting raw prose/markdown into the input file you may only:

- wrap their existing words in the site's markup (`##`/`###` headings,
  `**bold**`, `*italic*`, blockquotes, the `@youtube`/`@image`/`@callout`
  shorthand), and
- add the *metadata* they didn't write — `slug`, `summary`, `tags`,
  `read_time`, `connections`.

You may **not** add, remove, rephrase, expand, condense, "tighten," reorder,
or "improve" a single sentence of the body — not even a clause. The
`summary` and headings are the only prose you author, and the summary lives
in front-matter, never spliced into the body. If you genuinely think the
text needs an edit, *propose it separately as a suggestion* and let the
author decide — never fold it in silently.

This script prints the finished page's body as plain text under a
**"verbatim check"** header every time it runs, specifically so this is
auditable before update-indexes or deploy-site ever touch anything. Read that
output back to the author and get an explicit yes that the wording is
exactly theirs before continuing.

## Input format

Full spec: `references/input-format.md`. Minimum required front-matter:
`slug`, `title`, `category`, `summary`. Shape:

```yaml
---
slug: altitude-thinking
title: Altitude Thinking
category: concepts            # concepts | services | work | about | frameworks
summary: >
  One-paragraph italic hook. The map node uses the first ~100 characters.
tags: [constraints, abstraction]
read_time: 8 min read
connections: []              # target slugs this idea should link to, both ways
---
## First heading
Body in the site's lightweight markdown (see references/input-format.md for
the @youtube / @image / @callout shorthand).
```

By default a piece publishes under `/ideas/<slug>/`. Add `section:
braintail` to publish under `/braintail/<slug>/` instead (used for the
Braintail brand-review series).

### Connections

```yaml
connections:
  - {target: abstraction, label: builds on, reverse_label: applied in}
  - {target: core-constraints, label: illustrates}   # reverse_label defaults to label
```

`target` must be an existing page's slug — `build_page.py` looks it up (via
`--site`) to get its title for the new page's "Related Ideas" card, and exits
with a clear error if it doesn't exist. A piece cannot connect to itself.
Labels are lowercase verb phrases; they no longer render on the page itself
(the redesigned connections section is a flat, unlabeled grid) — they survive
only in the "Copy as markdown" / "Download .md" export. Don't spend a
round-trip haggling over label wording.

## Usage

```bash
python3 scripts/build_page.py --input piece.md --site ./.publish-stage --output-dir ./.publish-stage
```

- `--input` — the input file described above.
- `--site` — an existing site tree, **read-only** here, used to resolve
  connection targets' titles and summaries so the new page's connection cards
  can render. In the normal publish-idea workflow this is the same path as
  `--output-dir`: a staged copy of `./site` that already has every existing
  page, before this script adds the new one.
- `--output-dir` — where to write the new page. Usually the same staged copy
  as `--site` (so the new page lands right where update-indexes and
  deploy-site expect it), but can be a scratch directory for a dry run.

Produces, under `--output-dir`:

| path | what |
|---|---|
| `{section}/{slug}/index.html` | the new page |
| `media/og/{slug}.png` | its Open Graph share image (skipped, non-fatally, if headless Chrome is unavailable — a `⚠ could not render OG image` warning prints instead) |
| `idea.json` | metadata for **update-indexes**: slug, title, category, category_label, category_color, summary, tags, read_time, section, connections, related (resolved target titles/urls), node_summary (for map/index cards), page_path, og_path |

It also warns about any `/media/...` image the body references that isn't
present yet in `--site` or `--output-dir` — drop the file into the site's
`media/` directory and re-run if so.

## What it does NOT do (see update-indexes)

- Does not add the new node/edge to `map/index.html`.
- Does not touch the homepage's live mini-map.
- Does not add a card to `ideas/index.html` or bump any counts.
- Does not add reverse connections onto the pages this idea links to.
- Does not touch `llms.txt` or `sitemap.xml`.

Run **update-indexes** immediately after this, pointing `--idea-json` at the
`idea.json` this script just wrote and `--site-dir` at the same staged copy,
before anything is diffed for human review or deployed.

## Tracking tags (inherited automatically)

Every page carries two tags, both baked into `assets/page-template.html` so
new pages inherit them with no extra step from this script: Google Analytics
in `<head>`, and the LinkedIn Insight Tag in the **footer**, directly above
`</body>`. The LinkedIn tag must stay in the footer, not `<head>` — LinkedIn's
own instructions specify that placement, its `<noscript>` fallback is an
`<img>` (invalid inside `<head>`), and initializing after the DOM exists is
what lets LinkedIn Website Actions auto-attach to the Copy/Download buttons.
Website Actions groups buttons by their **visible text**, so the labels "Copy
as markdown" and "Download .md" in the template are load-bearing — don't
rename them.

## Adding a genuinely new category

If `category` is one the site hasn't seen, also pass `category_label` and
`category_color` (a hex like `#FF4040` or a `var(--color-...)` token) in the
front-matter. `update-indexes` reads these off `idea.json` to register the
category in the map's `COLORS`/`COLORS_LABEL` and add filter pills to both
the map and the ideas index.
