---
name: find-demand
description: >
  Find live demand for a Positive Constraint idea — the real threads, posts, and
  questions where people are describing the exact complexity, indecision, or
  churn that an idea in the vault dissolves. Reads the vault to learn what an idea
  offers, translates it into the words a person in the problem would actually
  type, searches the open web (Reddit, Hacker News, Q&A sites, forums, community
  spaces), qualifies each hit, and writes a ranked dossier of outreach
  opportunities for a human to review and act on. Use when the user wants to find
  who to reach, where their audience is asking, where to seed an idea, or "find
  demand / find the right people" for the site. This skill never posts anywhere —
  it only produces a reviewed list of opportunities.
---

# Find demand for a Positive Constraint idea

This is the **discovery** skill in the messenger library — the outbound
counterpart to `publish-idea`. `publish-idea` gets an idea *into* the vault; this
finds the person, in the wild, who is right now describing the problem that idea
solves, and hands you a ranked list of places to show up.

The goal it serves: **drive traffic and idea copy/downloads by finding the right
people** — those looking for a way to simplify complexity and find the unchanging
to embrace. So the output isn't "places to advertise." It's "real people, in
their own words, whom this specific idea would genuinely help," ranked so the
human can spend their scarce credibility where it lands.

## Hard rules — never break these

1. **This skill never posts, replies, DMs, or submits anywhere.** Its only output
   is a dossier file the human reads. The final act — showing up in a thread — is
   always a person, not this skill. This mirrors the `newsletter` agent's
   draft-only contract.
2. **Helpful-first, or not at all.** Only surface a thread where the idea *truly*
   answers what the person asked. If the fit is a stretch, drop it. A messenger
   that shows up where it doesn't belong burns the beacon. When in doubt, cut it.
3. **Quote the person, don't paraphrase them.** Each opportunity carries the
   asker's real words (a short quote) and a real URL, so the human can judge fit
   without re-reading the thread.
4. **You are drafting an *angle*, never a canned reply.** Suggest, in one line,
   how the idea helps this person — as raw material for the human's own voice.
   Never write a copy-paste comment; that's how communities detect and ban
   seeding.

## Prerequisite — WebSearch

This skill searches the live web. If `WebSearch` (and optionally `WebFetch`) are
deferred, load them first:

```
ToolSearch → "select:WebSearch,WebFetch"
```

## Workflow

### 1. Pick the scope

Take one idea (a slug like `abstraction`, `positive-constraint`, `core-constraints`)
or a theme. If the user didn't name one, list the vault's ideas and ask which to
hunt demand for — one at a time is sharper than "all of them." Read the vault's
node summaries to ground yourself:

```
grep -o '"id": "[^"]*", "title": "[^"]*", "category": "[^"]*", "summary": "[^"]*"' site/map/index.html
```

For the chosen idea, read its full page (`site/ideas/<slug>/index.html`) so you
know its essence, not just the blurb. `work-*` and `about`/`faq`/`contact` pages
are usually poor demand targets — prefer the concept/framework/reflection ideas
(`abstraction`, `core-constraints`, `positive-constraint`, `three-axes`,
`desired-reality`, `innovation`, `three-reds-in-haifa`).

### 2. Build the demand profile — translate idea → the asker's words

This is the craft of the skill. People in the problem do **not** search in the
idea's vocabulary. Nobody types "I need abstraction." They type "too many
features, can't decide what to cut" or "drowning in options, everything feels
important." So for the chosen idea, write:

- **The pain it dissolves**, in plain language (1–2 lines).
- **6–10 demand phrasings** — how a real person mid-problem would actually phrase
  it: the founder overwhelmed by scope, the PM who can't prioritize, the writer
  buried in research, the person paralyzed by a changing market. Mix
  question-forms ("how do I decide what matters when...") and venting-forms
  ("everything keeps changing and I can't...").
- **Where these people gather** — name specific venues: subreddits
  (r/startups, r/ProductManagement, r/Entrepreneur, r/decisionmaking,
  r/productivity, r/PKM…), Hacker News, Indie Hackers, Lobsters, Stack Exchange
  sites, Quora, niche Discords/forums. Pick venues that fit *this* idea, not a
  generic list.

Show this profile to the user before searching — it's fast to correct here and
expensive to correct after 30 searches.

### 3. Search for live demand

For each demand phrasing × likely venue, run `WebSearch`. Favor queries that
surface a *person asking*, not a listicle marketing at them. Techniques:

- Site-scope to where people ask: `site:reddit.com`, `site:news.ycombinator.com`,
  `site:indiehackers.com`, `site:*.stackexchange.com`, `site:quora.com`.
- Prefer question/venting phrasings over topic keywords ("how do I decide what
  to build first" beats "product prioritization").
- Add recency terms when a venue lets you ("2025", "this year") — fresh threads
  are actionable; a 2019 thread is not.

Collect concrete URLs. Optionally `WebFetch` a promising thread to confirm it's a
real person with a real problem before scoring it.

### 4. Qualify each hit

Keep only threads that pass all of:

- **Real person, real problem** — not an article, ad, or SEO farm.
- **Genuine fit** — the idea actually answers *this* question (rule 2).
- **Reachable** — a place a human could plausibly contribute today (open thread,
  active community), not a dead or locked page.
- **Fresh enough** to still be alive.

Score each survivor on **fit** (how squarely the idea answers them) and
**reach** (how alive/visible the venue is), and note the recency.

### 5. Write the dossier

Write to `messengers/find-demand/<slug>-<YYYY-MM-DD>.md`. One ranked table plus a
short block per opportunity. Rank by fit first, then reach. Format:

```markdown
# Find-demand — <idea title> — <date>

Idea: /ideas/<slug>/ · Pain it dissolves: <one line>
Reviewed by a human before any outreach. This skill posted nothing.

## Ranked opportunities

| # | Fit | Venue | The ask (quoted) | URL | Angle (raw material, not a reply) |
|---|-----|-------|------------------|-----|-----------------------------------|
| 1 | ●●● | r/startups | "everything feels important, I can't pick what to build" | <url> | Name the core constraint under the feature list — link `abstraction` as the how |
...

## Notes
- Venues worth a standing presence (recurring demand): ...
- Demand phrasings that found nothing (gaps / not where they gather): ...
- Ideas this surfaced demand for that we haven't published yet: ...
```

The `messengers/` tree is working output, not site content — if the user prefers
it not tracked in the public repo, add `messengers/` to `.gitignore`.

### 6. Hand off

Report the top few opportunities inline and point to the file. Remind the user
the next move is theirs: show up helpfully in the top threads, link the idea only
where it earns its place. What lands will show up later in GA + the
`idea_copy` / `idea_download` events — which is what a future `measure-resonance`
skill reads to sharpen the next demand profile.

## Why this composes

- Reads the same vault `publish-idea` writes, so demand-hunting always reflects
  the current ideas.
- Its demand profiles (step 2) are the raw form of a future `distill-idea` skill;
  when that exists, this consumes its essence instead of re-deriving it.
- Its output feeds `measure-resonance` (what actually drove copies) and `pitch`
  (which multipliers serve which demand), closing the messenger loop.
