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

CHAIN_QUERY = """
SELECT
  blob3 AS source_slug,
  blob2 AS target_slug,
  count() AS hits
FROM {dataset}
WHERE blob1 = 'chain'
  AND timestamp > NOW() - INTERVAL '{days}' DAY
GROUP BY source_slug, target_slug
ORDER BY hits DESC
""".strip()


def run_query_sql(account_id, token, sql):
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/analytics_engine/sql"
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


def run_query(account_id, token, days):
    return run_query_sql(account_id, token, QUERY.format(dataset=DATASET, days=days))


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
        by_idea.setdefault(slug, {"ai-assistant": 0, "ai-crawler": 0, "chain": 0, "grab": 0})
        cls = r["class"]
        by_idea[slug][cls] = by_idea[slug].get(cls, 0) + int(r["hits"])

    print(f"Serve signal, last {args.days}d ({len(rows)} day/class/idea rows):\n")
    print(f"{'idea':40s} {'Grabbed':>8s} {'Served':>8s} {'Chained':>8s} {'Crawled':>8s}")
    for slug, c in sorted(by_idea.items(), key=lambda kv: (-kv[1]["grab"], -kv[1]["ai-assistant"])):
        print(f"{slug:40s} {c['grab']:>8d} {c['ai-assistant']:>8d} {c['chain']:>8d} {c['ai-crawler']:>8d}")

    chain_rows = run_query_sql(account_id, token, CHAIN_QUERY.format(dataset=DATASET, days=args.days))
    if chain_rows:
        print(f"\nChain detail (grabbed idea → fetched idea):\n")
        print(f"{'source':40s} {'target':40s} {'hits':>6s}")
        for r in chain_rows:
            src = r["source_slug"] or "(unknown)"
            tgt = r["target_slug"] or "(no slug)"
            print(f"{src:40s} {tgt:40s} {int(r['hits']):>6d}")

    # Activation rate: of the ideas a human grabbed, how many led to an AI actually
    # fetching a related link (a chain). chain hits (by source slug) ÷ grabs (by slug)
    # — the one honest denominator. Only meaningful for slugs with at least one grab.
    chains_by_source = {}
    for r in chain_rows:
        src = r["source_slug"] or "(unknown)"
        chains_by_source[src] = chains_by_source.get(src, 0) + int(r["hits"])
    activation = {
        slug: (c["grab"], chains_by_source.get(slug, 0))
        for slug, c in by_idea.items()
        if c["grab"] > 0
    }
    if activation:
        print(f"\nActivation (grabbed → reached an AI via a chain link):\n")
        print(f"{'source':40s} {'Grabbed':>8s} {'Chains':>8s} {'Rate':>8s}")
        for slug, (grabs, chains) in sorted(activation.items(), key=lambda kv: -kv[1][0]):
            rate = f"{chains / grabs * 100:.0f}%" if grabs else "-"
            print(f"{slug:40s} {grabs:>8d} {chains:>8d} {rate:>8s}")

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
