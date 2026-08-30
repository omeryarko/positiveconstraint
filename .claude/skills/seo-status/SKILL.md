---
name: seo-status
description: >-
  SEO status check using only free data sources (GSC, GA4, Bing WMT, serve signals).
  Reports current ranking positions, traffic, impressions, and AI discoverability
  without consuming paid DataForSEO or Serper credits. Use when the user asks for
  SEO status, ranking check, or position update.
agent: seo
model: haiku
effort: low
---

# SEO Status Check

You are running a **status check only**. This is a read-only report using free data sources.

## Hard constraint: NO PAID API CALLS

**Do NOT call any of these:**
- `dataforseo.py` (any subcommand — volume, related, serp, bulk)
- `serper.py` (any subcommand — paa, full, related)

These cost money. A status check must be free.

## Data sources to use (all free)

Run these in parallel where possible:

### 1. Google Search Console — ranking positions and impressions

```bash
.venv-analytics/bin/python3 scripts/gsc_query.py queries --json
.venv-analytics/bin/python3 scripts/gsc_query.py pages --json
.venv-analytics/bin/python3 scripts/gsc_query.py compare --json
```

This gives: position, impressions, clicks, CTR for every query Google associates with
the site. The `compare` subcommand shows trend between two periods.

### 2. GA4 — traffic and engagement

```bash
.venv-analytics/bin/python3 scripts/ga4_query.py pages --json
.venv-analytics/bin/python3 scripts/ga4_query.py traffic --json
.venv-analytics/bin/python3 scripts/ga4_query.py events --json
```

This gives: page views, engagement rate, dwell time, traffic sources, idea_copy/download
event counts.

### 3. Bing WMT — ChatGPT discoverability

```bash
python3 scripts/bing_wmt.py keyword --q "TERM"
python3 scripts/bing_wmt.py coverage
```

Run `keyword` for each tracked term. Run `coverage` once for overall index status.
A zero Bing volume means ChatGPT cannot find the site for that term.

### 4. Serve signals — AI assistant traffic

```bash
python3 cf-worker/scripts/serve_signal_report.py
```

Shows which ideas AI assistants (Claude, ChatGPT, Perplexity) actually fetched.

## Tracked keywords

Check status on these keywords (from GSC + Bing WMT):
- "positive constraint"
- "positive constraints" (plural)
- "core constraint"
- Any other terms that appear in GSC with significant impressions

If the user asks about a specific keyword, add it to the check list.

## Report format

```
## SEO Status — YYYY-MM-DD

### Ranking positions (Google, via GSC)

| Keyword | Position | Impressions (30d) | Clicks | CTR | Trend |
|---------|----------|-------------------|--------|-----|-------|
| ...     | ...      | ...               | ...    | ... | ↑/↓/→ |

### Traffic (GA4, last 28 days)

| Page | Views | Engagement | Avg time |
|------|-------|------------|----------|
| ...  | ...   | ...        | ...      |

Top traffic sources: ...

### AI discoverability (Bing + serve signals)

| Keyword | Bing volume | Bing indexed? | AI serves (30d) |
|---------|-------------|---------------|-----------------|
| ...     | ...         | ...           | ...             |

### Changes since last check

- Position movements
- New queries appearing
- Index status changes

### Data sources used

All free: GSC (date), GA4 (date), Bing WMT (date), serve signals (date).
No paid APIs consumed.
```

## What NOT to do

- Do NOT run DataForSEO or Serper — this is a status check, not research.
- Do NOT recommend content changes — just report the numbers.
- Do NOT run Google Autocomplete or Trends — those are for research, not status.
- Do NOT fabricate any numbers. If a source returns nothing, say so.
