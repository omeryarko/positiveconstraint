---
name: publish-idea
description: >-
  Publish a new idea/article to positiveconstraint.com — format it as a site
  page, add the analytics tags (Google Analytics + LinkedIn Insight), place
  it under /ideas/<slug>/, generate its Open Graph link-preview image,
  register it in the knowledge map (node + summary + edges), add it to the
  ideas index, wire it to related ideas in both directions, and recompute all
  link counts — then stage, diff, and deploy via wrangler to the Cloudflare
  Worker. Use this whenever the user wants to add, publish, or post new
  content, an article, a piece, or an "idea" to their Positive Constraint
  site, or mentions updating the map / ideas list / a new /ideas page. Also
  use it when they hand you a draft (markdown or prose) and say "put this on
  the site."
license: MIT
compatibility: >-
  Orchestrates build-page, update-indexes, render-og, and deploy-site.
  See each skill's own compatibility notes.
metadata:
  author: positiveconstraint
  version: "2.0"
---

# Publish an idea to positiveconstraint.com

This skill turns a piece of content into a fully wired page on
positiveconstraint.com by orchestrating four other skills in sequence:
**build-page** → **update-indexes** → **deploy-site** (which in turn calls
**render-og**). It carries no scripts of its own — it's pure workflow: get
the input right, run the three scripts in order, and never let anything ship
without a human seeing the diff first.

The site is hand-built static HTML — no build step, no shared template,
deployed via `wrangler deploy` to the Cloudflare Worker that serves the site
(see `cloudflare-migration-worker` memory). The folder is a git repo (pushed
to github.com/omeryarko/positiveconstraint), and `./site` — the same tree the
Worker serves as static assets — is git-tracked. Git is both version control
and the only source of truth: nothing else can modify what's live, so
`git status` clean means `./site` matches what's actually deployed. **Every
successful deploy must be committed and pushed** (step 7) so GitHub stays in
step with production.

**Transitional note:** until positiveconstraint.com's nameservers actually
move to Cloudflare (a separate, not-yet-done migration step — see
`cloudflare-migration-worker` memory), `wrangler deploy` publishes to the
Worker's `*.workers.dev` URL, which is **not** yet what visitors to
positiveconstraint.com see. Publishing right now updates `./site` and the
Worker correctly, but won't appear on the real domain until cutover
completes.

## The four skills, and what each owns

| Skill | Owns | You run it |
|---|---|---|
| **build-page** | Parses the input file, renders the new page, calls render-og for its share image | Step 3 |
| **render-og** | Renders the 1200×630 OG PNG with headless Chrome | Called by build-page automatically |
| **update-indexes** | Reverse connections, map, homepage mini-map, ideas index, llms.txt, sitemap.xml, the review diff | Step 4 |
| **deploy-site** | Applies the stage onto `./site`, runs `wrangler deploy`, optional verify | Step 6 |

Don't hand-edit any site HTML yourself — between them these scripts keep a
dozen coupled numbers in sync (per-card connection counts, per-category
filter counts, map node/edge arrays, two header counts) that are easy to get
subtly wrong by hand. Your job is judgment: turning the user's content into
clean input, and *proposing which existing ideas it should connect to*.

## Workflow

### 1. Get the content into the input format

One markdown file with YAML front-matter. Full spec:
`../build-page/references/input-format.md`. Minimum required: `slug`,
`title`, `category`, `summary`. Shape:

```yaml
---
slug: altitude-thinking
title: Altitude Thinking
category: concepts            # concepts | services | work | about | frameworks
summary: >
  One-paragraph italic hook. The map node uses the first ~100 characters.
tags: [constraints, abstraction]
read_time: 8 min read
connections: []              # filled in step 2, after the user approves
---
## First heading
Body in the site's lightweight markdown (see build-page's references/input-format.md
for the @youtube / @image / @callout shorthand).
```

If the user gave you raw prose, convert it: pick a `slug` (kebab-case,
matches the URL `/ideas/<slug>/`), write a tight italic `summary`, choose a
`category`, draft `tags`, estimate `read_time`, and translate the body into
the shorthand. Show them the front-matter you inferred before continuing.

By default a piece publishes under `/ideas/<slug>/`. Add `section:
braintail` to publish under `/braintail/<slug>/` instead (used for the
Braintail brand-review series) — it still appears in the `/ideas/` index and
its `llms.txt` entry lands in the "Braintail — Brand Reviews" section.

**Content fidelity — the author's words are the author's.** This is a hard
rule, not a preference (see build-page's SKILL.md for the full statement).
You may wrap their existing words in the site's markup and add metadata they
didn't write (`slug`, `summary`, `tags`, `read_time`, `connections`) — you
may **not** add, remove, rephrase, expand, condense, "tighten," reorder, or
"improve" a single sentence of the body. If you think the text needs an
edit, propose it separately and let the author decide. build-page prints the
final body as plain text under a "verbatim check" header (step 3) so this is
auditable before anything ships.

### 2. Propose connections, let the user approve

This is the judgment step the user asked to keep. Read the existing node
summaries so your suggestions are grounded:

```bash
grep -o '"id": "[^"]*", "title": "[^"]*", "category": "[^"]*", "summary": "[^"]*"' site/map/index.html
```

Then propose a short ranked list of connections — for each: the **target**
slug, a **label** (how the new idea relates to the target, e.g. `builds on`,
`illustrates`, `applies to`), and a **reverse_label** (how the target relates
back, e.g. `applied in`, `illustrated by`). Present them and let the user
add/remove before writing them into the front-matter `connections:` list:

```yaml
connections:
  - {target: abstraction, label: builds on, reverse_label: applied in}
  - {target: core-constraints, label: illustrates, reverse_label: illustrated by}
```

`reverse_label` defaults to `label` if omitted. A piece cannot connect to
itself.

**Labels are no longer shown on the page.** Idea pages render connections as
a single flat "Related Ideas" grid (title + summary cards only). Labels
survive in exactly one place: the "Copy as markdown" / "Download .md" export
(`- Title — label → url`). Keep labels free text, lowercase and verb-like,
and don't spend a round-trip haggling over wording.

### 3. Stage a fresh copy and build the page

```bash
rm -rf .publish-stage
cp -r site .publish-stage
python3 skills/build-page/scripts/build_page.py \
  --input <piece.md> --site ./.publish-stage --output-dir ./.publish-stage
```

This builds the new page (GA + LinkedIn Insight tags baked in from the
template), renders its OG image via render-og, and prints:

- a warning if the body references `/media/...` images not yet in
  `site/media/` (drop them in and re-run if so),
- the new page's body as plain text, under a **verbatim check** header.

**Read the verbatim check back to the author and get an explicit yes** that
the wording is exactly theirs — this is the guard against content drifting
during conversion. (This is the exact failure from the "Innovation" publish:
the body was expanded during conversion before the script ever ran.
build-page is faithful; the risk is in step 1.)

It also writes `.publish-stage/idea.json`, which the next step consumes.

### 4. Wire it into the rest of the site

```bash
python3 skills/update-indexes/scripts/update_indexes.py \
  --idea-json ./.publish-stage/idea.json --site-dir ./.publish-stage --live-site ./site
```

Wires connections both ways, updates the map, the homepage live mini-map,
the ideas index, `llms.txt`, `sitemap.xml`, recomputes every count, and
prints:

- the list of files that will be uploaded (`NEW` vs `edit`),
- unified diffs of every edited file,
- the recomputed map/ideas counts.

### 5. Review the diff with the user

Show the staged summary and diffs from step 4, plus the verbatim check from
step 3. Point out anything notable — especially that the header counts
change (they self-correct a pre-existing stale count: the live "12 ideas ·
34 connections" becomes the true node/edge totals). Get explicit sign-off on
both the diff and the verbatim wording. **This is the only safety gate
before production.**

### 6. Deploy

```bash
set -a; source .claude/secrets/cloudflare.env; set +a
python3 skills/deploy-site/scripts/deploy.py \
  --site-dir ./site --stage-dir ./.publish-stage --cf-worker ./cf-worker \
  --verify --verify-url https://positiveconstraint.omer-2c2.workers.dev/<section>/<slug>/
```

Applies the staged files onto `./site` (the git-tracked source the Worker
reads), then runs `wrangler deploy` from `./cf-worker`, which diffs and
uploads only the new/changed assets itself, and finally checks the new URL
returns a healthy status. If `wrangler deploy` fails, `./site` has already
been updated locally but nothing went live — fix the error and re-run, or
`git checkout` the touched paths to revert before trying again.

Use the `*.workers.dev` URL for `--verify-url` until DNS cutover to
Cloudflare completes (see the transitional note above), then the real domain
afterward. Spot-check the map and ideas index in a browser too if the user
wants.

### 7. Snapshot to git

`./site` now matches the new live state, so commit and push it — this keeps
the GitHub backup in step with production and gives a revertable point.

```bash
git add -A
git commit -m "Publish idea: <slug>"
git push
```

Never commit `.claude/secrets/` (it holds the plaintext Cloudflare API token
and is gitignored — the repo is public). If a deploy later proves bad, roll
back with `git revert` on `./site` plus `wrangler rollback` on the Worker (or
re-run deploy-site from the reverted `./site`).

## Design guarantees (why you can trust the output)

- **Single tree.** Content lives only at `/ideas/<slug>/`. The old `/pieces/`
  tree was deleted; don't recreate it.
- **Content fidelity.** Nothing in build-page or update-indexes touches idea
  prose — build-page renders the input body and wires structure around it.
  The one place content can drift is the human conversion in step 1, which is
  why that step forbids editing the body and build-page prints it verbatim
  for sign-off.
- **Counts are derived, never typed.** Map/index headers = live node/edge
  totals; each card's "N connections" = that page's `RELATED` length;
  filter-pill counts = actual cards per category. Publishing self-heals stale
  live counts.
- **Homepage mini-map stays in lockstep.** update-indexes updates
  `MAP_NODES`/`MAP_EDGES`/`MAP_COLORS`/`MAP_LABELS` and `map-live-meta`
  alongside `/map/` so the two can't diverge. It deliberately leaves the
  curated "Start here" featured cards and the homepage category pills alone.
- **Cards can't drift from export.** A page's connection cards are generated
  from the same `RELATED[]` array the "Copy as markdown" buttons read.
- **Tracking tags.** Every page carries Google Analytics (`<head>`) and the
  LinkedIn Insight Tag (footer, above `</body>`) — both baked into
  build-page's `assets/page-template.html`. The LinkedIn tag must stay in the
  footer, not `<head>` (see build-page's SKILL.md for why), and the "Copy as
  markdown" / "Download .md" button labels are load-bearing for LinkedIn
  Website Actions — don't rename them.
- **Seeding analytics + AI index.** Every page's copy/download buttons fire
  GA events (`idea_copy` / `idea_download`, tagged `idea_slug`). update-indexes
  appends the new idea to `/llms.txt` under the section matching its category
  and updates `/sitemap.xml` (new `<url>`, refreshed `<lastmod>` on touched
  surfaces). Both edits are idempotent. `/robots.txt` is static and needs no
  per-publish update.
- **Minimal, reviewable diffs.** Existing content is edited surgically —
  connections are *appended* to target pages, leaving every existing card
  byte-identical. New content only appears where it should.
- **Category quirk preserved.** Positive Constraint is `frameworks` on the
  map but `concepts` in the index; update-indexes counts each surface by its
  own labels rather than forcing them to agree, so it won't disturb that on
  unrelated pages.

## Adding a genuinely new category

If `category` is one the site hasn't seen, also pass `category_label` and
`category_color` (a hex like `#FF4040` or a `var(--color-...)` token) in the
front-matter. update-indexes will register it in the map's
`COLORS`/`COLORS_LABEL` and add filter pills to both the map and the ideas
index.
