---
name: deploy-site
description: >-
  Apply a staged set of positiveconstraint.com site edits onto ./site and
  deploy it via `wrangler deploy` to the Cloudflare Worker that serves the
  site, with an optional post-deploy HTTP verification. Use this as the last
  mechanical step of publishing an idea (after build-page and update-indexes
  have staged everything and a human has reviewed the diff), or any time a
  reviewed set of changes to ./site needs to go live.
license: MIT
compatibility: >-
  Requires Python 3.6+, and `wrangler` (installed via nvm if node/npm/wrangler
  aren't already on PATH). Requires CLOUDFLARE_API_TOKEN and
  CLOUDFLARE_ACCOUNT_ID in the environment.
metadata:
  author: positiveconstraint
  version: "1.0"
---

# Deploy the site

Applies a staged manifest onto `./site` (the git-tracked source of truth the
Worker's `assets` binding serves — see `cf-worker/wrangler.jsonc`), then runs
`wrangler deploy` from the worker directory, which diffs and uploads only the
changed assets itself.

**This is the point of no return** for a publish — everything before this
(build-page, update-indexes) only ever wrote to a staged copy. Don't run this
until a human has reviewed the diff update-indexes printed and confirmed the
verbatim body check.

## Prerequisites

**Node/wrangler:** if `node`/`npm`/`wrangler` aren't on `PATH`, they're
installed via nvm:

```bash
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"
```

`scripts/deploy.py` runs this setup itself before invoking `wrangler deploy`,
so it works from a non-interactive shell without the caller doing this first.

**Cloudflare credentials:**

```bash
set -a; source .claude/secrets/cloudflare.env; set +a
```

Never commit `.claude/secrets/` — it holds the plaintext Cloudflare API token
and the repo is public.

## Usage

```bash
set -a; source .claude/secrets/cloudflare.env; set +a
python3 scripts/deploy.py --site-dir ./site --stage-dir ./.publish-stage --cf-worker ./cf-worker --verify
```

- `--site-dir` (default `./site`) — the git-tracked tree the Worker serves.
- `--stage-dir` (default `./.publish-stage`) — where build-page +
  update-indexes staged their edits, including `manifest.json`. Every file
  `manifest.json` lists gets copied from here onto `--site-dir` before
  `wrangler deploy` runs.
  - **If `wrangler.jsonc`'s `assets.directory` already points at the stage
    path directly** (some setups deploy straight from `.publish-stage`
    instead of copying onto `./site` first), pass the same path for both
    `--site-dir` and `--stage-dir` — the copy step becomes a no-op and
    `wrangler deploy` just picks up what's already there.
  - If `--stage-dir` has no `manifest.json`, the copy step is skipped
    entirely (assumes `--site-dir` is already current).
- `--cf-worker` (default `./cf-worker`) — the wrangler project directory
  (`cf-worker/wrangler.jsonc` in this repo).
- `--verify` (optional) — after a successful deploy, fetch one or more URLs
  and check their HTTP status. Exits non-zero if any check fails, so a broken
  deploy is caught immediately.
- `--verify-url URL` (repeatable, optional) — URL(s) to check with
  `--verify`. Defaults to the site root if omitted. Pass the new idea's URL
  and a touched page explicitly for a real publish, e.g.:

  ```bash
  --verify --verify-url https://positiveconstraint.omer-2c2.workers.dev/ideas/<slug>/ \
           --verify-url https://positiveconstraint.omer-2c2.workers.dev/map/
  ```

## Transitional note: workers.dev vs. the real domain

Until positiveconstraint.com's nameservers move to Cloudflare (a separate,
not-yet-done migration step), `wrangler deploy` publishes to the Worker's
`*.workers.dev` URL, which is **not** yet what visitors to
positiveconstraint.com see (that's still the old host). Use the
`*.workers.dev` URL for `--verify-url` until DNS cutover completes, then the
real domain afterward.

## Failure handling

If `wrangler deploy` fails, `--site-dir` has **already been updated locally**
but nothing went live — the script exits non-zero with that exact warning.
Fix the error and re-run `deploy.py`, or `git checkout` the touched paths in
`--site-dir` to revert before trying again.

If `--verify` fails after an otherwise-successful deploy, the deploy itself
already happened — a failed verify means investigate (DNS propagation,
caching, a bad path), not necessarily re-deploy.

## After this

Once verified, snapshot `./site` to git — this is what keeps GitHub in step
with production and gives a revertable point:

```bash
git add -A
git commit -m "Publish idea: <slug>"
git push
```

Rollback for a bad deploy: `git revert` on `./site` plus `wrangler rollback`
on the Worker (or re-run `deploy.py` from the reverted `./site`).
