#!/usr/bin/env python3
"""Google Search Console query data for positiveconstraint.com.

Pulls the data Google gives site owners for free: which queries brought
impressions, clicks, CTR, and average position. This is the closest free
proxy for Google search volume — but only for terms the site already appears
for. For discovery of new terms, use bing_wmt.py related.

Auth: Application Default Credentials.
Scopes required: webmasters.readonly (re-auth with the full scope string in
analytics-access.md if the default token lacks it).

Venv: .venv-analytics/ (has google-api-python-client, google-auth).

Usage:
    .venv-analytics/bin/python3 scripts/gsc_query.py queries
    .venv-analytics/bin/python3 scripts/gsc_query.py queries --days 90 --top 50
    .venv-analytics/bin/python3 scripts/gsc_query.py pages
    .venv-analytics/bin/python3 scripts/gsc_query.py query-page --query "positive constraint"
    .venv-analytics/bin/python3 scripts/gsc_query.py compare --days 28
    .venv-analytics/bin/python3 scripts/gsc_query.py queries --json
"""
import argparse
import datetime as dt
import json
import sys

SITE = "sc-domain:positiveconstraint.com"


def build_service():
    from google.auth import default
    from googleapiclient.discovery import build

    creds, _ = default(scopes=["https://www.googleapis.com/auth/webmasters.readonly"])
    return build("searchconsole", "v1", credentials=creds)


def date_range(days):
    end = dt.date.today() - dt.timedelta(days=3)
    start = end - dt.timedelta(days=days)
    return start.isoformat(), end.isoformat()


def cmd_queries(svc, args):
    start, end = date_range(args.days)
    body = {
        "startDate": start,
        "endDate": end,
        "dimensions": ["query"],
        "rowLimit": args.top,
    }
    resp = svc.searchanalytics().query(siteUrl=SITE, body=body).execute()
    rows = resp.get("rows", [])
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print(f"No query data for {start} to {end}.")
        return
    print(f"Top {len(rows)} queries, {start} to {end}:")
    print(f"{'Query':<50} {'Clicks':>7} {'Impr':>7} {'CTR':>7} {'Pos':>6}")
    print("-" * 80)
    for r in rows:
        q = r["keys"][0]
        print(f"{q:<50} {r['clicks']:>7.0f} {r['impressions']:>7.0f} "
              f"{r['ctr']:>6.1%} {r['position']:>6.1f}")


def cmd_pages(svc, args):
    start, end = date_range(args.days)
    body = {
        "startDate": start,
        "endDate": end,
        "dimensions": ["page"],
        "rowLimit": args.top,
    }
    resp = svc.searchanalytics().query(siteUrl=SITE, body=body).execute()
    rows = resp.get("rows", [])
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print(f"No page data for {start} to {end}.")
        return
    print(f"Top {len(rows)} pages, {start} to {end}:")
    print(f"{'Page':<70} {'Clicks':>7} {'Impr':>7} {'CTR':>7} {'Pos':>6}")
    print("-" * 95)
    for r in rows:
        pg = r["keys"][0].replace("https://positiveconstraint.com", "")
        print(f"{pg:<70} {r['clicks']:>7.0f} {r['impressions']:>7.0f} "
              f"{r['ctr']:>6.1%} {r['position']:>6.1f}")


def cmd_query_page(svc, args):
    start, end = date_range(args.days)
    body = {
        "startDate": start,
        "endDate": end,
        "dimensions": ["query", "page"],
        "rowLimit": args.top,
    }
    if args.query:
        body["dimensionFilterGroups"] = [{
            "filters": [{"dimension": "query", "operator": "contains",
                         "expression": args.query}]
        }]
    resp = svc.searchanalytics().query(siteUrl=SITE, body=body).execute()
    rows = resp.get("rows", [])
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print(f"No query-page data for {start} to {end}.")
        return
    print(f"Query-page mapping, {start} to {end}:")
    print(f"{'Query':<40} {'Page':<40} {'Clicks':>7} {'Impr':>7} {'Pos':>6}")
    print("-" * 105)
    for r in rows:
        q = r["keys"][0][:39]
        pg = r["keys"][1].replace("https://positiveconstraint.com", "")[:39]
        print(f"{q:<40} {pg:<40} {r['clicks']:>7.0f} {r['impressions']:>7.0f} "
              f"{r['position']:>6.1f}")


def cmd_compare(svc, args):
    half = args.days
    end = dt.date.today() - dt.timedelta(days=3)
    mid = end - dt.timedelta(days=half)
    start = mid - dt.timedelta(days=half)

    def fetch(s, e):
        body = {
            "startDate": s.isoformat(),
            "endDate": e.isoformat(),
            "dimensions": ["query"],
            "rowLimit": 100,
        }
        resp = svc.searchanalytics().query(siteUrl=SITE, body=body).execute()
        return {r["keys"][0]: r for r in resp.get("rows", [])}

    prev = fetch(start, mid)
    curr = fetch(mid, end)
    all_queries = sorted(set(prev) | set(curr))

    if args.json:
        out = []
        for q in all_queries:
            p = prev.get(q, {})
            c = curr.get(q, {})
            out.append({"query": q,
                        "prev_impressions": p.get("impressions", 0),
                        "curr_impressions": c.get("impressions", 0),
                        "prev_clicks": p.get("clicks", 0),
                        "curr_clicks": c.get("clicks", 0)})
        print(json.dumps(out, indent=2))
        return

    if not all_queries:
        print("No data in either period.")
        return
    print(f"Compare: {start} to {mid} vs {mid} to {end}")
    print(f"{'Query':<40} {'Prev Impr':>10} {'Curr Impr':>10} {'Delta':>8}")
    print("-" * 72)
    for q in all_queries:
        pi = prev.get(q, {}).get("impressions", 0)
        ci = curr.get(q, {}).get("impressions", 0)
        delta = ci - pi
        sign = "+" if delta > 0 else ""
        print(f"{q:<40} {pi:>10.0f} {ci:>10.0f} {sign}{delta:>7.0f}")


def main():
    p = argparse.ArgumentParser(description="Google Search Console data")
    p.add_argument("--json", action="store_true", help="raw JSON output")
    sub = p.add_subparsers(dest="cmd")

    sq = sub.add_parser("queries", help="top queries by impressions")
    sq.add_argument("--days", type=int, default=28)
    sq.add_argument("--top", type=int, default=25)

    sp = sub.add_parser("pages", help="top pages by impressions")
    sp.add_argument("--days", type=int, default=28)
    sp.add_argument("--top", type=int, default=25)

    sqp = sub.add_parser("query-page", help="query-to-page mapping")
    sqp.add_argument("--query", help="filter by query substring")
    sqp.add_argument("--days", type=int, default=28)
    sqp.add_argument("--top", type=int, default=50)

    sc = sub.add_parser("compare", help="compare two consecutive periods")
    sc.add_argument("--days", type=int, default=28, help="length of each period")

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(1)

    svc = build_service()
    {"queries": cmd_queries, "pages": cmd_pages, "query-page": cmd_query_page,
     "compare": cmd_compare}[args.cmd](svc, args)


if __name__ == "__main__":
    main()
