#!/usr/bin/env python3
"""DataForSEO client — exact Google search volumes and SERP data.

This is the only tool in the stack that gives real Google keyword volumes for
arbitrary terms (not just terms the site already ranks for). Stdlib only, no
venv needed.

Auth: login + password from .claude/secrets/dataforseo.env or env vars.
Pay-per-call — be mindful of credit consumption.

Subcommands:

  volume      Exact Google volume + competition for one or more keywords.
  bulk        Volume for many keywords in one API call (cheaper).
  serp        Live SERP results for a query (top 10 organic).
  related     Related keywords with volumes.
  suggestions Keyword suggestions (seed expansion with volumes).
  balance     Check remaining API credits.

Usage:
    python3 scripts/dataforseo.py volume "positive constraint"
    python3 scripts/dataforseo.py volume "constraint thinking" "deliberate limitation"
    python3 scripts/dataforseo.py bulk keywords.txt
    python3 scripts/dataforseo.py serp "positive constraint"
    python3 scripts/dataforseo.py related "constraint"
    python3 scripts/dataforseo.py suggestions "deliberate limitation"
    python3 scripts/dataforseo.py balance

Cost guidance (approximate, 2026 pricing):
  - volume:      ~0.05 credits per keyword (Keywords Data API)
  - bulk:        ~0.05 credits per keyword, batched
  - serp:        ~2.0  credits per query (SERP API live)
  - related:     ~0.05 credits per seed
  - suggestions: ~0.05 credits per seed
  - balance:     free
"""
import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request

API_BASE = "https://api.dataforseo.com/v3"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS = os.path.join(ROOT, ".claude", "secrets", "dataforseo.env")


def credentials():
    login = os.environ.get("DATAFORSEO_LOGIN", "").strip()
    password = os.environ.get("DATAFORSEO_PASSWORD", "").strip()
    if login and password:
        return login, password
    if os.path.exists(SECRETS):
        vals = {}
        with open(SECRETS) as fh:
            for line in fh:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    vals[k.strip()] = v.strip().strip("'\"")
        login = vals.get("DATAFORSEO_LOGIN", "")
        password = vals.get("DATAFORSEO_PASSWORD", "")
        if login and password:
            return login, password
    sys.exit(
        f"No credentials. Put DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in {SECRETS}\n"
        "(or export them as environment variables)."
    )


def call(path, payload=None):
    login, password = credentials()
    token = base64.b64encode(f"{login}:{password}".encode()).decode()
    url = f"{API_BASE}/{path}"
    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "User-Agent": "posconcom-dataforseo/1",
    }
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:1000]
        sys.exit(f"HTTP {e.code}: {body}")


def cmd_volume(args):
    keywords = args.keywords
    payload = [{
        "keywords": keywords,
        "location_code": args.location,
        "language_code": args.language,
    }]
    resp = call("keywords_data/google_ads/search_volume/live", payload)
    tasks = resp.get("tasks", [])

    results = []
    for task in tasks:
        for item in (task.get("result") or []):
            results.append(item)

    if args.json:
        json.dump(results, sys.stdout, indent=2)
        print()
        return

    if not results:
        print("No volume data returned.")
        return

    print(f"{'Keyword':40s}  {'Volume':>8s}  {'CPC':>6s}  {'Comp':>6s}  {'Trend'}")
    print("-" * 90)
    for r in results:
        kw = r.get("keyword", "?")
        vol = r.get("search_volume")
        cpc = r.get("cpc")
        comp = r.get("competition")
        monthly = r.get("monthly_searches") or []
        trend = ""
        if monthly:
            recent = [m.get("search_volume", 0) for m in monthly[-3:]]
            trend = " → ".join(str(v) for v in recent)
        vol_s = str(vol) if vol is not None else "-"
        cpc_s = f"${cpc:.2f}" if isinstance(cpc, (int, float)) else "-"
        comp_s = str(comp) if comp is not None else "-"
        print(f"  {kw:38s}  {vol_s:>8s}  {cpc_s:>6s}  {comp_s:>6s}  {trend}")


def cmd_bulk(args):
    with open(args.file) as fh:
        keywords = [line.strip() for line in fh if line.strip() and not line.startswith("#")]
    if not keywords:
        sys.exit("No keywords in file.")
    # DataForSEO allows up to 700 keywords per request
    batch_size = 700
    all_results = []
    for i in range(0, len(keywords), batch_size):
        batch = keywords[i:i + batch_size]
        payload = [{
            "keywords": batch,
            "location_code": args.location,
            "language_code": args.language,
        }]
        resp = call("keywords_data/google_ads/search_volume/live", payload)
        for task in resp.get("tasks", []):
            for item in (task.get("result") or []):
                all_results.append(item)

    if args.json:
        json.dump(all_results, sys.stdout, indent=2)
        print()
        return

    print(f"{'Keyword':40s}  {'Volume':>8s}  {'CPC':>6s}  {'Competition':>12s}")
    print("-" * 70)
    for r in sorted(all_results, key=lambda x: x.get("search_volume") or 0, reverse=True):
        kw = r.get("keyword", "?")
        vol = r.get("search_volume")
        cpc = r.get("cpc")
        comp = r.get("competition")
        print(f"  {kw:38s}  {str(vol) if vol is not None else '-':>8s}  "
              f"{'$'+f'{cpc:.2f}' if cpc is not None else '-':>6s}  "
              f"{f'{comp:.4f}' if comp is not None else '-':>12s}")
    print(f"\nTotal: {len(all_results)} keywords")


def cmd_serp(args):
    payload = [{
        "keyword": args.query,
        "location_code": args.location,
        "language_code": args.language,
        "depth": 10,
    }]
    resp = call("serp/google/organic/live/advanced", payload)
    tasks = resp.get("tasks", [])

    items = []
    for task in tasks:
        for result in (task.get("result") or []):
            for item in (result.get("items") or []):
                if item.get("type") == "organic":
                    items.append(item)

    if args.json:
        json.dump(items, sys.stdout, indent=2)
        print()
        return

    print(f"SERP for '{args.query}' (Google, location {args.location}):\n")
    for item in items[:10]:
        pos = item.get("rank_absolute", "?")
        title = item.get("title", "")
        url = item.get("url", "")
        desc = (item.get("description") or "")[:80]
        print(f"  {pos:>2}. {title}")
        print(f"      {url}")
        if desc:
            print(f"      {desc}")
        print()


def cmd_related(args):
    payload = [{
        "keyword": args.query,
        "location_code": args.location,
        "language_code": args.language,
        "depth": 2,
        "include_seed_keyword": True,
    }]
    resp = call("keywords_data/google_ads/keywords_for_keywords/live", payload)
    results = []
    for task in resp.get("tasks", []):
        for item in (task.get("result") or []):
            results.append(item)

    results.sort(key=lambda x: x.get("search_volume") or 0, reverse=True)

    if args.json:
        json.dump(results, sys.stdout, indent=2)
        print()
        return

    print(f"Related keywords for '{args.query}':\n")
    print(f"  {'Keyword':40s}  {'Volume':>8s}  {'CPC':>6s}  {'Competition':>12s}")
    print("  " + "-" * 70)
    for r in results[:20]:
        kw = r.get("keyword", "?")
        vol = r.get("search_volume")
        cpc = r.get("cpc")
        comp = r.get("competition")
        print(f"  {kw:40s}  {str(vol) if vol is not None else '-':>8s}  "
              f"{'$'+f'{cpc:.2f}' if cpc is not None else '-':>6s}  "
              f"{f'{comp:.4f}' if comp is not None else '-':>12s}")


def cmd_suggestions(args):
    payload = [{
        "keyword": args.query,
        "location_code": args.location,
        "language_code": args.language,
    }]
    resp = call("keywords_data/google_ads/keywords_for_site/live", payload)
    results = []
    for task in resp.get("tasks", []):
        for item in (task.get("result") or []):
            results.append(item)

    results.sort(key=lambda x: x.get("search_volume") or 0, reverse=True)

    if args.json:
        json.dump(results, sys.stdout, indent=2)
        print()
        return

    print(f"Keyword suggestions for '{args.query}':\n")
    print(f"  {'Keyword':40s}  {'Volume':>8s}  {'CPC':>6s}")
    print("  " + "-" * 58)
    for r in results[:20]:
        kw = r.get("keyword", "?")
        vol = r.get("search_volume")
        cpc = r.get("cpc")
        print(f"  {kw:40s}  {str(vol) if vol is not None else '-':>8s}  "
              f"{'$'+f'{cpc:.2f}' if cpc is not None else '-':>6s}")


def cmd_balance(args):
    resp = call("appendix/user_data")
    tasks = resp.get("tasks", [])
    for task in tasks:
        result = task.get("result") or [{}]
        for r in result:
            money = r.get("money", {})
            balance = money.get("balance", "?")
            total_spent = money.get("total", "?")
            print(f"Balance: ${balance}")
            print(f"Total spent: ${total_spent}")
            limits = r.get("limits", {})
            if limits:
                day_limit = limits.get("day", {})
                if day_limit:
                    print(f"Daily limit: ${day_limit.get('maximum_amount', '?')}")
                    print(f"Today spent: ${day_limit.get('spent_amount', '?')}")
            return
    if args.json:
        json.dump(resp, sys.stdout, indent=2)
        print()


def main():
    p = argparse.ArgumentParser(description="DataForSEO — exact Google search volumes")
    p.add_argument("--json", action="store_true", help="raw JSON output")
    p.add_argument("--location", type=int, default=2840, help="location code (2840=US, 2826=UK)")
    p.add_argument("--language", default="en", help="language code")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("volume", help="exact Google volume for keywords")
    v.add_argument("keywords", nargs="+")

    b = sub.add_parser("bulk", help="bulk volume from a file (one keyword per line)")
    b.add_argument("file")

    s = sub.add_parser("serp", help="live Google SERP results")
    s.add_argument("query")

    r = sub.add_parser("related", help="related keywords with volumes")
    r.add_argument("query")

    g = sub.add_parser("suggestions", help="keyword suggestions")
    g.add_argument("query")

    sub.add_parser("balance", help="check remaining API credits")

    args = p.parse_args()
    {"volume": cmd_volume, "bulk": cmd_bulk, "serp": cmd_serp,
     "related": cmd_related, "suggestions": cmd_suggestions,
     "balance": cmd_balance}[args.cmd](args)


if __name__ == "__main__":
    main()
