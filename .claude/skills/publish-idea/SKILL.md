---
name: publish-idea
description: >
  Publish a new idea/article to positiveconstraint.com — format it as a site
  page, add the analytics tags (Google Analytics + LinkedIn Insight), place it
  under /ideas/<slug>/, generate its
  Open Graph link-preview image, register it
  in the knowledge map (node + summary + edges), add it to the ideas index, wire
  it to related ideas in both directions, and recompute all link counts — then
  stage, diff, and deploy via wrangler to the Cloudflare Worker. Use this
  whenever the user wants to add,
  publish, or post new content, an article, a piece, or an "idea" to their
  Positive Constraint site, or mentions updating the map / ideas list / a new
  /ideas page. Also use it when they hand you a draft (markdown or prose) and say
  "put this on the site."
---

# Publish an idea to positiveconstraint.com

This skill turns a piece of content into a fully wired page on
positiveconstraint.com. The site is hand-built static HTML — no build step, no
shared template, deployed via `wrangler deploy` to the Cloudflare Worker that
serves the site (see `cloudflare-migration-worker` memory). So the whole point
here is to make every derived thing (map counts, index counts, reverse
connections) update consistently and to never push to production without a
human seeing the diff first.

The folder is a git repo (pushed to github.com/omeryarko/positiveconstraint,
see `project-git-version-control` memory), and `./site` — the same tree the
Worker serves as static assets — is git-tracked. Git is both version control
and the only source of truth `stage` reads from: nothing else can modify what's
live, so there's no separate "pull the live site" step. **Every successful
deploy must be committed and pushed** (step 7) so GitHub stays in step with
production and `git revert` is always a working undo.

**Transitional note:** until positiveconstraint.com's nameservers actually move
to Cloudflare (a separate, not-yet-done migration step — see
`cloudflare-migration-worker` memory), `wrangler deploy` publishes to the
Worker's `*.workers.dev` URL, which is **not** yet what visitors to
positiveconstraint.com see (that's still the old Namecheap host). Publishing an
idea right now updates `./site` and the Worker correctly, but won't appear on
the real domain until cutover completes.

## The one script does the mechanical work

`scripts/publish.py` handles all the deterministic surgery. You handle judgment:
turning the user's content into clean input, and *proposing which existing ideas
it should connect to*. Don't hand-edit the HTML files — the script keeps a dozen
coupled numbers in sync (per-card connection counts, per-category filter counts,
map node/edge arrays, two header counts) that are easy to get subtly wrong by
hand.

It also renders the page's **Open Graph link-preview image** — the card that
unfurls when the URL is shared on X / LinkedIn / Slack / iMessage. Each idea gets
a 1200×630 PNG at `/media/og/<slug>.png` (from `assets/og-template.html`, a light
card matching the site) plus the `og:*` / `twitter:*` meta tags in the page head.
This is one static image per URL — link previews can't be theme-aware — so the
card is fixed light for every viewer.

## Prerequisites

**Headless Chrome** must be present to render the OG image (it uses the site's
web fonts). The step is non-fatal: if Chrome isn't found, `stage` still succeeds
but prints `⚠ could not render OG image for <slug>` and that page ships without a
preview card until re-staged where Chrome is available. On macOS the script finds
Google Chrome automatically.

The script edits a **copy** of `./site` and diffs against it. `git status` is
the freshness check: a clean tree means `./site` matches what's actually
deployed (there's nothing else that can have changed it — see the transitional
note above for the one exception during migration). If it's dirty in a way you
can't account for, resolve that first; there's no FTP mirror-pull step anymore.

**Node/wrangler:** if `node`/`npm`/`wrangler` aren't on `PATH`, they're
installed via nvm — run `export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"`
first (see `cloudflare-migration-worker` memory).

## Workflow

### 1. Get the content into the input format

The script reads one markdown file with YAML front-matter. Full spec:
`references/input-format.md`. Minimum required: `slug`, `title`, `category`,
`summary`. Shape:

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
Body in the site's lightweight markdown (see references/input-format.md for the
@youtube / @image / blockquote shorthand).
```

If the user gave you raw prose, convert it: pick a `slug` (kebab-case, matches
the URL `/ideas/<slug>/`), write a tight italic `summary`, choose a `category`,
draft `tags`, estimate `read_time`, and translate the body into the shorthand.
Show them the front-matter you inferred before continuing.

**Content fidelity — the author's words are the author's.** This is a hard rule,
not a preference. The body of the idea is theirs; reproduce it *verbatim*. When
you build the input file you may only:

- wrap their existing words in the site's markup (`##`/`###` headings, `**bold**`,
  `*italic*`, blockquotes, the `@youtube`/`@image` shorthand), and
- add the *metadata* they didn't write — `slug`, `summary`, `tags`, `read_time`,
  `connections`.

You may **not** add, remove, rephrase, expand, condense, "tighten," reorder, or
"improve" a single sentence of the body — not even a clause. The `summary` and
headings are the only prose you author, and the summary lives in front-matter,
never spliced into the body. If you genuinely think the text needs an edit,
*propose it separately as a suggestion* and let the author decide — never fold it
in silently. (This is the exact failure from the "Innovation" publish: the body
was expanded during this conversion step before the script ever ran. The script
is faithful; the risk is here.) `stage` prints the final body as plain text under
a "verbatim check" header (step 4) so this is auditable before anything ships.

### 2. Propose connections, let the user approve

This is the judgment step the user asked to keep. Read the existing node
summaries so your suggestions are grounded:

```
grep -o '"id": "[^"]*", "title": "[^"]*", "category": "[^"]*", "summary": "[^"]*"' site/map/index.html
```

Then propose a short ranked list of connections — for each: the **target** slug,
a **label** (how the new idea relates to the target, e.g. `builds on`,
`illustrates`, `applies to`), and a **reverse_label** (how the target relates
back, e.g. `applied in`, `illustrated by`). Present them and let the user
add/remove before you write them into the front-matter `connections:` list:

**Note on labels: they are no longer shown on the page.** The redesigned idea
pages render connections as a single flat **"Related Ideas"** grid (title +
summary cards only) — the old per-label groupings and `conn-type`/`conn-label`
displays are gone. Labels now survive in exactly one place: the "Copy as
markdown" / "Download .md" export (`- Title — label → url`). So the real judgment
is *which* ideas to connect and in what order; the label text is minor
export-only metadata. Don't spend a round-trip haggling over label wording — pick
sensible lowercase verb phrases (`illustrates`, `builds on`) and move on. Keep
labels free text, lowercase and verb-like.

```yaml
connections:
  - {target: abstraction, label: builds on, reverse_label: applied in}
  - {target: core-constraints, label: illustrates, reverse_label: illustrated by}
```

`reverse_label` defaults to `label` if omitted. A piece cannot connect to itself.

### 3. Stage

```
python3 scripts/publish.py stage --input <piece.md> --site ./site --stage ./.publish-stage
```

This builds the new page (with the GA and LinkedIn Insight tags baked in from
the template — see "Tracking tags" below), wires
connections both ways, updates the map, the homepage live mini-map, and the
ideas index, recomputes every count, and prints:
- the list of files that will be uploaded (NEW vs edit),
- a warning if the body references `/media/...` images not yet in `site/media/`,
- unified diffs of every edited file,
- the new page's body as plain text, under a **verbatim check** header.

If media is missing, drop the image files into `site/media/` and re-run stage.

### 4. Review the diff with the user

Show the staged summary and diffs. Point out anything notable — especially that
the header counts change (they self-correct a pre-existing stale count: the live
"12 ideas · 34 connections" becomes the true node/edge totals). **Read the
"verbatim check" body back to the author and get an explicit yes that the wording
is exactly theirs** — this is the guard against the content drifting during
conversion. Then get the go-ahead to ship. This is the only safety gate before
production.

### 5. Deploy

Export the Cloudflare API token from its secrets file, then deploy:

```
set -a; source .claude/secrets/cloudflare.env; set +a
python3 scripts/publish.py deploy --stage ./.publish-stage --site ./site --cf-worker ./cf-worker
```

Deploy applies the staged files onto `./site` (the git-tracked source the
Worker reads), then runs `wrangler deploy` from `./cf-worker`, which diffs and
uploads only the new/changed assets itself. If `wrangler deploy` fails, `./site`
has already been updated locally but nothing went live — fix the error and
re-run, or `git checkout` the touched paths to revert before trying again.

### 6. Verify

Fetch the new URL and a touched page to confirm they're live. Use the
`*.workers.dev` URL until DNS cutover is complete (see the transitional note
above), then the real domain afterward:

```
curl -s -o /dev/null -w "%{http_code}\n" https://positiveconstraint.omer-2c2.workers.dev/ideas/<slug>/
```

Spot-check the map and ideas index in a browser if the user wants.

### 7. Snapshot to git

`./site` now matches the new live state, so commit and push it — this keeps
the GitHub backup in step with production and gives you a revertable point.

```
git add -A
git commit -m "Publish idea: <slug>"
git push
```

Never commit `.claude/secrets/` (it holds the plaintext Cloudflare API token
and is gitignored — the repo is public). If a deploy later proves bad, roll
back with `git revert` on `./site` plus `wrangler rollback` on the Worker (or
re-run deploy from the reverted `./site`).

## Design guarantees (why you can trust the output)

- **Single tree.** Content lives only at `/ideas/<slug>/`. The old `/pieces/`
  tree was deleted; don't recreate it.
- **Content fidelity.** The script never touches idea prose — it renders the
  input body and wires structure around it. The one place content can drift is the
  human conversion in step 1, which is why that step forbids editing the body and
  `stage` prints the body verbatim for sign-off. What the author wrote is what
  ships.
- **Counts are derived, never typed.** Map/index headers = live node/edge totals;
  each card's "N connections" = that page's `RELATED` length; filter-pill counts =
  actual cards per category. Publishing self-heals the stale live counts.
- **Homepage mini-map stays in lockstep.** The homepage embeds the same graph
  (`MAP_NODES`/`MAP_EDGES`/`MAP_COLORS`/`MAP_LABELS`) plus a `map-live-meta` count;
  the script updates all of them alongside `/map/` so the two can't diverge. It
  deliberately leaves the curated "Start here" featured cards and the homepage
  category pills alone — those are author-picked, not derived.
- **Cards can't drift from export.** A page's connection cards are generated from
  the same `RELATED[]` array the "Copy as markdown" buttons read.
- **Tracking tags.** Every page carries two, both baked into `page-template.html`
  so new pages inherit them with no extra step: Google Analytics (`G-N9DEMEQG7C`)
  in `<head>`, and the LinkedIn Insight Tag (partner `3001121`) in the footer
  directly above `</body>`. The LinkedIn tag must stay in the footer, not `<head>`
  — LinkedIn's own instructions specify that placement, its `<noscript>` fallback
  is an `<img>` (invalid inside `<head>`), and initializing after the DOM exists is
  what lets LinkedIn Website Actions auto-attach to the Copy/Download buttons.
  Website Actions groups buttons by their **visible text**, so the labels
  "Copy as markdown" and "Download .md" are load-bearing: renaming them in the
  template silently breaks the CTA retargeting audience built on those names.
- **Seeding analytics + AI index.** Every page's "Copy as markdown" / "Download .md"
  buttons fire GA events (`idea_copy` / `idea_download`, tagged with `idea_slug`) so
  you can rank which ideas people carry into AI tools. The template carries these,
  so new pages inherit them. On stage, the script also appends the new idea to
  `/llms.txt` (AI-oriented index) under the section matching its category —
  concepts/frameworks/reflections → "Core ideas", services/work → "Practice & work",
  else "Optional". It also updates `/sitemap.xml`: appends a `<url>` for the new
  page (priority 0.7, or 0.6 for `work`) and refreshes `<lastmod>` on the surfaces
  every publish rewrites (home, `/ideas/`, `/map/`). Both edits are idempotent, so
  re-staging the same slug won't duplicate entries. `/robots.txt` (which points
  crawlers at the sitemap) explicitly welcomes AI crawlers; it's static and needs
  no per-publish update.
- **Minimal, reviewable diffs.** Existing content is edited surgically —
  connections are *appended* to target pages, leaving every existing card
  byte-identical. New content only appears where it should.
- **Category quirk preserved.** Positive Constraint is `frameworks` on the map but
  `concepts` in the index; the script counts each surface by its own labels rather
  than forcing them to agree, so it won't "fix" (i.e. disturb) that on unrelated
  pages.

## Adding a genuinely new category

If `category` is one the site hasn't seen, also pass `category_label` and
`category_color` (a hex like `#FF4040` or a `var(--color-...)` token) in the
front-matter. The script will register it in the map's `COLORS`/`COLORS_LABEL`
and add filter pills to both the map and the ideas index.
