#!/usr/bin/env python3
"""deploy.py — apply a staged publish-idea manifest onto ./site and deploy it
via wrangler to the Cloudflare Worker that serves positiveconstraint.com.

Extracted from the "deploy" half of the original monolithic scripts/publish.py.
Reads CLOUDFLARE_API_TOKEN/CLOUDFLARE_ACCOUNT_ID from the environment. There's
no separate backup folder — rollback is `git revert` on ./site plus
`wrangler rollback` on the Worker (or re-run deploy from the reverted ./site).

CLI:
    python deploy.py --site-dir ./site [--stage-dir ./.publish-stage] [--cf-worker ./cf-worker] [--verify] [--verify-url URL ...]

--site-dir is the git-tracked source of truth the Worker's assets binding
serves (wrangler.jsonc's `assets.directory`). --stage-dir is where build-page
+ update-indexes wrote the new/edited files and manifest.json; its contents
get copied onto --site-dir before `wrangler deploy` runs. If wrangler.jsonc's
`assets.directory` is itself set to the stage path (some setups deploy
straight from .publish-stage rather than copying onto ./site first), pass
--site-dir pointing at that same stage directory and this script's copy step
becomes a no-op self-copy — either layout works.

--verify (optional) fetches one or more URLs after a successful deploy and
prints their HTTP status, so a broken deploy is caught immediately instead of
silently. Defaults to the site root if no --verify-url is given.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '_lib'))
import config
import site_io


def apply_manifest(stage_dir, site_dir):
    manifest_path = os.path.join(stage_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        print(f"  (no manifest.json in {stage_dir} — nothing to apply, assuming --site-dir is already up to date)")
        return []
    manifest = json.loads(site_io.read(manifest_path))
    for m in manifest:
        src = os.path.join(stage_dir, m["path"])
        dst = os.path.join(site_dir, m["path"])
        if os.path.normpath(src) == os.path.normpath(dst):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        print(("new  " if m["new"] else "edit "), "/" + m["path"])
    return manifest


def run_wrangler(worker_dir):
    result = subprocess.run(
        'export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; node_modules/.bin/wrangler deploy',
        shell=True, executable="/bin/bash", cwd=worker_dir,
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit("wrangler deploy failed -- ./site was updated locally but is "
                  "NOT live. Fix the error above and re-run deploy, or "
                  "`git checkout` the touched paths in ./site to revert.")


def verify_urls(urls):
    ok = True
    for url in urls:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                code = resp.status
        except urllib.error.HTTPError as e:
            code = e.code
        except Exception as e:
            print(f"  {url} -> ERROR ({e})")
            ok = False
            continue
        marker = "OK" if 200 <= code < 400 else "!!"
        print(f"  {url} -> {code} {marker}")
        if not (200 <= code < 400):
            ok = False
    return ok


def do_deploy(args):
    site_dir = os.path.abspath(args.site_dir)
    stage_dir = os.path.abspath(args.stage_dir)
    worker_dir = os.path.abspath(args.cf_worker)

    if not (os.environ.get("CLOUDFLARE_API_TOKEN") and os.environ.get("CLOUDFLARE_ACCOUNT_ID")):
        sys.exit("Set CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID in the environment before deploy "
                 "(e.g. `set -a; source .claude/secrets/cloudflare.env; set +a`).")

    # apply the staged edits onto --site-dir, the git-tracked source of truth
    # that the Worker's assets binding serves directly -- no separate upload
    # step. A no-op if --stage-dir and --site-dir are the same path (the
    # "wrangler deploys straight from .publish-stage" layout).
    if os.path.normpath(stage_dir) != os.path.normpath(site_dir):
        apply_manifest(stage_dir, site_dir)
    else:
        print(f"  (--stage-dir == --site-dir: {site_dir}; nothing to copy)")

    # publish: wrangler diffs the assets directory against the last deployed
    # version itself and uploads only what changed. Cloudflare's version
    # history is the rollback net now (`wrangler rollback`) -- no hand-rolled
    # backup folder.
    run_wrangler(worker_dir)
    print("Done.")

    if args.verify:
        urls = args.verify_url or [config.CANONICAL_URL_PREFIX + "/"]
        print("\n--- verify ---")
        ok = verify_urls(urls)
        if not ok:
            sys.exit("verify: one or more URLs did not return a healthy status.")


def main():
    ap = argparse.ArgumentParser(description="Apply a staged publish-idea manifest onto ./site and deploy via wrangler.")
    ap.add_argument("--site-dir", default="./site")
    ap.add_argument("--stage-dir", default="./.publish-stage")
    ap.add_argument("--cf-worker", default="./cf-worker")
    ap.add_argument("--verify", action="store_true", help="Fetch --verify-url(s) after a successful deploy and check their HTTP status.")
    ap.add_argument("--verify-url", action="append", help="URL to check after deploy (repeatable). Defaults to the site root.")
    args = ap.parse_args()
    do_deploy(args)


if __name__ == "__main__":
    main()
