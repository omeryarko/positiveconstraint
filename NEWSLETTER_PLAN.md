# Implementation Plan — Newsletter subscribe across the site

**Run this in a fresh session (Sonnet).** Goal: add a "subscribe for weekly new ideas"
form across positiveconstraint.com, connected to **Buttondown**.

The site is hand-built static HTML in `site/`, with shared inline CSS design tokens per
page, deployed over FTP. There is no backend and no build step — the form POSTs directly
to Buttondown's hosted endpoint.

---

## 0. Prerequisite (mostly done)

The Buttondown account exists. Username is **`positiveconstraint`** — already baked into
the form URLs below, so no placeholder to swap.

Remaining human steps in the Buttondown dashboard (nice-to-have, not blocking):
1. Rename the newsletter from the default "My Awesome Newsletter".
2. Enable **double opt-in** (confirmation email).
3. Set a `from` address.

---

## 1. The shared component

Two variants, same Buttondown form. Both use the site's existing CSS variables
(`--color-*`), so **dark mode and the red accent are inherited automatically** — do not
hardcode hex colors.

### Behavior
Use a progressive-enhancement AJAX submit so subscribing shows an inline "Thanks — check
your inbox" message instead of opening a popup. This mirrors the site's existing pattern
(the idea pages already ship inline `<script>` for "copy as markdown"). Buttondown's
endpoint accepts a form POST; on success we swap the form for a confirmation line. If JS
is disabled, the plain form still submits (the `target`/`onsubmit` fallback opens
Buttondown's hosted confirmation page).

### CSS — add once per page

Add this block to the **end of each edited page's existing `<style>`** (the last `<style>`
block, right before `</head>`). It is safe to paste identically into every page since each
file is standalone.

```css
/* Subscribe block */
.pc-subscribe {
  max-width: 680px;
  margin: 0 auto;
  padding: 0 var(--space-lg);
}
.pc-subscribe-inner {
  background: var(--color-background-secondary);
  border: 0.5px solid var(--color-border-tertiary);
  border-radius: 10px;
  padding: var(--space-lg) var(--space-xl);
  display: flex;
  align-items: center;
  gap: var(--space-xl);
  flex-wrap: wrap;
}
.pc-subscribe-text { flex: 1; min-width: 220px; }
.pc-subscribe-title {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 2px;
}
.pc-subscribe-desc {
  font-family: var(--font-body);
  font-size: 13px;
  font-style: italic;
  color: var(--color-text-secondary);
  line-height: 1.5;
}
.pc-subscribe-form { display: flex; gap: var(--space-sm); flex: 1; min-width: 240px; }
.pc-subscribe-form input {
  flex: 1;
  height: 40px;
  padding: 0 14px;
  font-family: var(--font-display);
  font-size: 14px;
  color: var(--color-text-primary);
  background: var(--color-background-primary);
  border: 0.5px solid var(--color-border-secondary);
  border-radius: 6px;
}
.pc-subscribe-form input:focus {
  outline: none;
  border-color: var(--color-red);
}
.pc-subscribe-form button {
  height: 40px;
  padding: 0 18px;
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 500;
  color: var(--color-white);
  background: var(--color-black);
  border: none;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}
.pc-subscribe-form button:hover { background: var(--color-text-secondary); }
.pc-subscribe-note {
  font-family: var(--font-display);
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-top: var(--space-sm);
}

/* Variant A — prominent home band */
.pc-subscribe--hero .pc-subscribe-inner {
  flex-direction: column;
  text-align: center;
  padding: var(--space-2xl) var(--space-xl);
}
.pc-subscribe--hero .pc-subscribe-eyebrow {
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-tertiary);
  margin-bottom: var(--space-sm);
}
.pc-subscribe--hero .pc-subscribe-title { font-size: 26px; font-weight: 700; letter-spacing: -0.02em; }
.pc-subscribe--hero .pc-subscribe-desc {
  font-style: normal;
  font-size: 16px;
  max-width: 420px;
  margin: var(--space-sm) auto var(--space-lg);
}
.pc-subscribe--hero .pc-subscribe-form { flex: none; width: 100%; max-width: 440px; }
.pc-subscribe--hero .pc-subscribe-form button { background: var(--color-red); }
.pc-subscribe--hero .pc-subscribe-form button:hover { background: var(--color-red-hover); }

@media (max-width: 640px) {
  .pc-subscribe-inner { flex-direction: column; align-items: stretch; }
  .pc-subscribe-form { flex-direction: column; }
  .pc-subscribe-form button { width: 100%; }
}
```

### Shared JS — add once per page

Add before `</body>` (on idea pages, alongside the existing `<script>`; a second
`<script>` tag is fine):

```html
<script>
document.querySelectorAll('.pc-subscribe-form').forEach(function (form) {
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var data = new FormData(form);
    fetch(form.action, { method: 'POST', body: data, mode: 'no-cors' });
    var inner = form.closest('.pc-subscribe-inner');
    inner.innerHTML = '<div class="pc-subscribe-text" style="text-align:center;width:100%">'
      + '<div class="pc-subscribe-title">Thanks — check your inbox</div>'
      + '<div class="pc-subscribe-desc">Confirm your email to start getting weekly ideas.</div></div>';
  });
});
</script>
```

Note: `mode: 'no-cors'` means we can't read the response, so we optimistically show
success. That's fine — Buttondown's double opt-in email is the real confirmation, and
duplicate/invalid addresses are handled on their side.

---

## 2. Variant B — idea pages + ideas index (compact card)

**HTML to insert immediately before the page's `<footer class="footer">`:**

```html
<section class="pc-subscribe">
  <div class="pc-subscribe-inner">
    <div class="pc-subscribe-text">
      <div class="pc-subscribe-title">Get new ideas weekly</div>
      <div class="pc-subscribe-desc">One email a week when new ideas enter the vault.</div>
    </div>
    <form class="pc-subscribe-form" method="post" target="popupwindow"
          action="https://buttondown.com/api/emails/embed-subscribe/positiveconstraint"
          onsubmit="window.open('https://buttondown.com/positiveconstraint','popupwindow')">
      <input type="email" name="email" placeholder="you@example.com" aria-label="Email address" required>
      <button type="submit">Subscribe</button>
    </form>
  </div>
</section>
```

Add a little breathing room: the idea-page `<footer>` already has a top border, so the card
sits directly above it. If it looks tight, wrap with `margin-bottom: var(--space-2xl)` on
`.pc-subscribe` for these pages (optional).

### Files to edit (Variant B) — 16 files total

Ideas index:
- `site/ideas/index.html`

All idea pages **except `contact`**:
- `site/ideas/about/index.html`
- `site/ideas/abstraction/index.html`
- `site/ideas/core-constraints/index.html`
- `site/ideas/desired-reality/index.html`
- `site/ideas/faq/index.html`
- `site/ideas/positive-constraint/index.html`
- `site/ideas/process/index.html`
- `site/ideas/services/index.html`
- `site/ideas/three-axes/index.html`
- `site/ideas/three-reds-in-haifa/index.html`
- `site/ideas/work/index.html`
- `site/ideas/work-cortisense/index.html`
- `site/ideas/work-leap-commerce/index.html`
- `site/ideas/work-tapouts/index.html`
- `site/ideas/work-user1st/index.html`

**Do NOT edit:** `site/ideas/contact/index.html` (competing CTA) or `site/map/index.html`
(interactive canvas).

For each file: (1) append the CSS block to the last `<style>`, (2) insert the Variant B
HTML before `<footer class="footer">`, (3) add the shared JS before `</body>`.

---

## 3. Variant A — home page band (prominent)

**File:** `site/index.html`

Insert **after** the closing `</section>` of the `category-section` and **before**
`<footer class="footer">`:

```html
<section class="pc-subscribe pc-subscribe--hero" style="padding-bottom: var(--space-3xl);">
  <div class="pc-subscribe-inner">
    <div class="pc-subscribe-eyebrow">The vault, weekly</div>
    <div class="pc-subscribe-title">New ideas, once a week</div>
    <div class="pc-subscribe-desc">An email when new ideas enter the vault — the week's additions and how they connect. No noise.</div>
    <form class="pc-subscribe-form" method="post" target="popupwindow"
          action="https://buttondown.com/api/emails/embed-subscribe/positiveconstraint"
          onsubmit="window.open('https://buttondown.com/positiveconstraint','popupwindow')">
      <input type="email" name="email" placeholder="you@example.com" aria-label="Email address" required>
      <button type="submit">Subscribe</button>
    </form>
    <div class="pc-subscribe-note">One email a week. Unsubscribe anytime.</div>
  </div>
</section>
```

Then append the CSS block (§1) to the home page's `<style>` and add the shared JS (§1)
before `</body>`.

---

## 4. Verify locally

From the repo root:

```bash
cd site && python3 -m http.server 8000
```

Check in a browser (light + dark via OS appearance):
- `http://localhost:8000/` — hero band renders below "Browse by category", above footer.
- `http://localhost:8000/ideas/` — compact card above footer.
- A few idea pages, e.g. `/ideas/three-axes/`, `/ideas/work/` — compact card present.
- `/ideas/contact/` and `/map/` — **no** subscribe block.
- Submitting an email swaps in the "Thanks — check your inbox" message inline.
- Mobile width (≤640px): input + button stack full-width.

Confirm the real Buttondown username is in place (grep for `positiveconstraint` — should
return nothing before deploy):

```bash
grep -rl "positiveconstraint" site/ && echo "STILL HAS PLACEHOLDER — do not deploy"
```

---

## 5. Deploy

Use the site's normal FTP publish flow (same as the `publish-idea` skill — FTP creds are
in Claude memory `reference_ftp_credentials.md`). Upload the edited files:
`site/index.html`, `site/ideas/index.html`, and the 15 idea-page `index.html` files.
Mirror the `site/` layout on the server. Verify a couple of live URLs after upload.

Then commit on a branch (e.g. `publish/newsletter-subscribe`) and open a PR to `main`.

---

## 6. Weekly digest (operational, after launch)

Start manual: each week, compose the digest in Buttondown listing the new ideas and send.

Optional automation (follow-up, not required for launch): generate `site/feed.xml` (an RSS
feed of ideas, newest first) and point Buttondown's **RSS-to-email** automation at
`https://positiveconstraint.com/feed.xml` to auto-send. If pursued, fold feed regeneration
into the `publish-idea` skill so every publish updates the feed.

---

## Copy reference (approved)

- Eyebrow (home): **The vault, weekly**
- Title (home): **New ideas, once a week**
- Desc (home): *An email when new ideas enter the vault — the week's additions and how they connect. No noise.*
- Note (home): *One email a week. Unsubscribe anytime.*
- Title (idea pages): **Get new ideas weekly**
- Desc (idea pages): *One email a week when new ideas enter the vault.*
- Placeholder: `you@example.com` · Button: **Subscribe** · Success: **Thanks — check your inbox**
