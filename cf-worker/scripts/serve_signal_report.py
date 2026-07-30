#!/usr/bin/env python3
"""Read side of the Serve-signal measurement (see memory: ai-context-measurement-plan).

Queries the Workers Analytics Engine SQL API for per-idea counts of
user-triggered AI fetcher hits ("ai-assistant": Claude-User/ChatGPT-User/
Perplexity-User) and training-crawler hits ("ai-crawler"), written by
cf-worker/src/index.js into the `ai_serve_signal` dataset.

AE retains ~90 days of raw data. Run with --export periodically (e.g.
monthly, mirroring the GA4-pull pattern in the analytics-access memory) to
append daily rollups to a local JSONL file for indefinite history.

Auth: the existing CLOUDFLARE_API_TOKEN in .claude/secrets/cloudflare.env
already works against the AE SQL API -- verified 2026-07-30 running this script
with only that token set. No separate Account-Analytics token is needed.
CLOUDFLARE_ANALYTICS_API_TOKEN is still honored if present (preferred when set),
but is optional; the code falls back to CLOUDFLARE_API_TOKEN.

Usage:
    set -a; source .claude/secrets/cloudflare.env; set +a
    python3 cf-worker/scripts/serve_signal_report.py --days 30
    python3 cf-worker/scripts/serve_signal_report.py --days 30 --export cf-worker/serve-signal-history.jsonl
"""
import argparse
import json
import os
import sys
import urllib.request

DATASET = "ai_serve_signal"

QUERY = """
SELECT
  toDate(timestamp) AS day,
  blob1 AS class,
  blob2 AS idea_slug,
  count() AS hits
FROM {dataset}
WHERE timestamp > NOW() - INTERVAL '{days}' DAY
GROUP BY day, class, idea_slug
ORDER BY day DESC, hits DESC
""".strip()


def run_query(account_id, token, days):
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql"
    sql = QUERY.format(dataset=DATASET, days=days)
    req = urllib.request.Request(
        url,
        data=sql.encode("utf-8"),
        headers={"Authorization": f"Bearer {token}"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        body = json.load(resp)
    if "data" not in body:
        raise RuntimeError(f"Unexpected AE response: {body}")
    return body["data"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days (AE retains ~90)")
    parser.add_argument("--export", metavar="PATH", help="Append daily rollups as JSONL to this file")
    args = parser.parse_args()

    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    token = os.environ.get("CLOUDFLARE_ANALYTICS_API_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
    if not account_id or not token:
        sys.exit(
            "Missing CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_ANALYTICS_API_TOKEN.\n"
            "source .claude/secrets/cloudflare.env first; see this script's docstring "
            "for the token permission needed."
        )

    rows = run_query(account_id, token, args.days)

    by_idea = {}
    for r in rows:
        slug = r["idea_slug"] or "(no slug)"
        by_idea.setdefault(slug, {"ai-assistant": 0, "ai-crawler": 0})
        by_idea[slug][r["class"]] = by_idea[slug].get(r["class"], 0) + int(r["hits"])

    print(f"Serve signal, last {args.days}d ({len(rows)} day/class/idea rows):\n")
    print(f"{'idea':40s} {'Served (ai-assistant)':>22s} {'Crawled (ai-crawler)':>22s}")
    for slug, counts in sorted(by_idea.items(), key=lambda kv: -kv[1]["ai-assistant"]):
        print(f"{slug:40s} {counts['ai-assistant']:>22d} {counts['ai-crawler']:>22d}")

    if args.export:
        seen = set()
        if os.path.exists(args.export):
            with open(args.export) as f:
                for line in f:
                    r = json.loads(line)
                    seen.add((r["day"], r["class"], r["idea_slug"]))
        new_rows = [r for r in rows if (r["day"], r["class"], r["idea_slug"]) not in seen]
        with open(args.export, "a") as f:
            for r in new_rows:
                f.write(json.dumps(r) + "\n")
        print(f"\nAppended {len(new_rows)} new rows ({len(rows) - len(new_rows)} already present) to {args.export}")


if __name__ == "__main__":
    main()
