# SEO Technical Fix Pass — Spec

**Status:** ready to implement (own session + branch). **Scope:** technical hygiene only — NOT the content/demand repositioning (that's separate, higher-leverage work).
**Why this exists:** GA4 + Search Console diagnosis (2026-07-27) found ~0 organic-search discovery. Root cause is demand mismatch + low authority; this pass fixes the underlying technical hygiene so nothing is *actively* holding back consolidation. Modest impact ceiling on its own — do it, but don't expect a traffic jump from it alone.

**Deploy:** use the existing flow — `.claude/skills/publish-idea/scripts/publish.py` (or the publish-idea skill). Changes are edits to existing pages + the page template; no new pages, no map/index changes.

---

## Task 1 — Add `rel="canonical"` to every page (+ the template)

**Problem:** No page has a `<link rel="canonical">`. Google is showing duplicate URLs (e.g. legacy `/core-constraints` at pos 6.1 *outranking* the real `/ideas/core-constraints/` at pos 10; a stray `www.` entry). The 301s already exist and work, but canonicals reinforce consolidation.

**The rule is mechanical:** every page already has `<meta property="og:url" content="…">`. The canonical URL **equals that og:url value**. So for each page, insert directly **after** the existing `og:url` line:

```html
<link rel="canonical" href="{{same URL as og:url on this page}}">
```

**Recommended method — script it** (safer than 24 hand-edits; canonical always mirrors og:url):
- For each `site/**/index.html`: read the `og:url` content value, and if no `rel="canonical"` is present, insert `<link rel="canonical" href="THAT_URL">` right after the `og:url` meta line.
- Pages to cover: `site/index.html`, `site/ideas/index.html`, `site/map/index.html`, all `site/ideas/*/index.html`, and `site/subscribed/index.html` if present. Any page lacking `og:url` → set canonical to its own absolute URL (apex, https, trailing slash).
- Idempotent: skip if a canonical already exists.

**Also update the template** so all *future* published ideas get it automatically:
- File: `.claude/skills/publish-idea/assets/page-template.html`
- After the line `<meta property="og:url" content="https://positiveconstraint.com/ideas/{{SLUG}}/">` add:
  `<link rel="canonical" href="https://positiveconstraint.com/ideas/{{SLUG}}/">`
- Check `.claude/skills/publish-idea/scripts/publish.py` and `SKILL.md` for any head-integrity assertions/checks that enumerate expected `<head>` tags — add canonical there too so the check stays in sync.

**Verify:** `curl -s https://positiveconstraint.com/ideas/core-constraints/ | grep -i canonical` returns the self URL on a sample of pages after deploy.

---

## Task 2 — Rewrite machine-truncated meta descriptions

**Problem:** ~12 descriptions were auto-truncated from body text at ~155 chars and cut off mid-word/mid-sentence. They read as broken. Rewrite each as an intentional 140–160 char summary (complete sentences). Drafts below are proposed — verify/tune against each page's actual body before shipping.

| Page | Current (broken) ending | Proposed description (verify vs body) |
|---|---|---|
| `ideas/about/` | "…By being true to yoursel" | Omer Yarkowich on why he founded Positive Constraint — two lessons from his father about passion, integrity, and finding the constraint that shapes real value. |
| `ideas/abstraction/` | "…everything Positive Constrain" | Abstraction is filtering out detail to surface what truly matters — the core cognitive tool behind Positive Constraint's whole approach to strategy. |
| `ideas/core-constraints/` | "…non-essential. Every" | A core constraint is the irreducible truth at the center of a problem — what remains after you abstract away everything non-essential. |
| `ideas/faq/` | "…The consulting firms will charge" | Straight answers on how Positive Constraint works, who it's for, and why it's different from traditional consulting — no jargon, no retainer games. |
| `ideas/process/` | "…for typical timeline" | Every engagement runs through four phases; depth and duration scale with scope. See the typical timeline and what happens at each stage. |
| `ideas/services/` | "…See The Process to understand" | Three services, one foundation: core constraints and abstraction. The difference is how far we go together — from a focused sprint to full strategy. |
| `ideas/work/` | "…the beauty in harnessing the" | Value creation isn't bound to one industry, geography, or technology. A look at real engagements and the constraints that shaped each outcome. |
| `ideas/work-cortisense/` | "…proving to a multina" | How Positive Constraint helped CortiSense (predictive-maintenance IoT, Israel) sharpen its value proposition and B2B pitch to a multinational buyer. |
| `ideas/work-leap-commerce/` | "…seeking a strategic investor to su" | How Positive Constraint shaped LEAP Commerce's investment pitch and value strategy for its eCommerce-enablement business in Singapore. |
| `ideas/work-tapouts/` | "…the core of our" | How Positive Constraint helped Tapouts — an emotional-wellbeing platform for kids (USA) — articulate its core and build an early-stage pitch deck. |
| `ideas/work-user1st/` | "…reinventing itself from a com" | How Positive Constraint helped User1st (developer tools for digital inclusion, Israel) reframe its value strategy and investor pitch through a reinvention. |
| `ideas/contact/` (optional) | contact-info dump | Have an interesting value puzzle or want better answers? Reach Omer Yarkowich at Positive Constraint — Tel Aviv, Israel. |

Leave the already-good, hand-written descriptions alone: `complex-new-world`, `embrace-the-unchanging`, `prince-of-persia-shadow-man`, `superhuman-100ms-constraint`, `innovation`, `three-axes`, `three-reds-in-haifa`, `desired-reality`, `positive-constraint` (homepage-idea).

**Note:** description edits must be mirrored in the page's `og:description` and `twitter:description` (all three currently share the same string). Keep them in sync.

---

## Task 3 — Fix the duplicated title

- File: `site/ideas/positive-constraint/index.html`
- Current: `<title>Positive Constraint — Positive Constraint</title>` (and matching `og:title`/`twitter:title`)
- This page is the flagship concept. Give it a distinct, meaningful title, e.g.
  `Positive Constraint — the hidden layer of unchange that gives the mind an edge`
  (or a tighter variant). Update `<title>`, `og:title`, `twitter:title`, and `og:image:alt` consistently.
- Keep it under ~60 visible chars if possible; the example above is long — tighten to taste.

---

## Task 4 — Fix the broken `www` (hosting-level, NOT code)

**Diagnosis:** `www.positiveconstraint.com` resolves (same IP, 198.177.120.17). `http://www` 301s to `https://www` (preserving www), but **https://www has no valid SSL cert**, so the TLS handshake fails → dead end. The `.htaccess` www→apex rule never runs because a server-level redirect to https-www fires first and TLS dies before Apache is reached. Google indexed a stray `www` URL once and now can't recrawl/consolidate it.

**Fix (in Namecheap cPanel — user action, low priority, 1 impression at stake):**
- Ensure AutoSSL covers **both** apex and `www` (re-run AutoSSL so the cert includes `www.positiveconstraint.com`), **or** change the server-level force-HTTPS redirect to target the apex host directly so it never lands on the certless https-www.
- Success check: `curl -sI https://www.positiveconstraint.com/` returns `301` → `https://positiveconstraint.com/` (not a TLS error).

---

## After deploy — tell Google
1. In Search Console, re-submit the sitemap (`https://positiveconstraint.com/sitemap.xml`).
2. Use URL Inspection → "Request indexing" on the consolidated pages (esp. `/ideas/core-constraints/`) to nudge recrawl.
3. Re-check in ~2–4 weeks: legacy root URLs should fade from the Pages report and impressions should consolidate onto `/ideas/*`.

## Explicitly OUT OF SCOPE (separate, higher-leverage work)
- Repositioning content/titles around **searched** queries (run the `find-demand` skill first). The homepage title "Wisdom for your context" and the private vocabulary ("core constraints", "desired reality", "three axes") are demand problems, not hygiene — handle them there, not here.
- Link-building / authority.
