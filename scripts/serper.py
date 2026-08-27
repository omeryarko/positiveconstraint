#!/usr/bin/env python3
"""Serper.dev client — People Also Ask trees and SERP structure.

The unique value here is PAA (People Also Ask) data: the questions Google
surfaces around a topic. No other tool in the stack gives this. Stdlib only.

Auth: API key from .claude/secrets/serper.env or $SERPER_API_KEY.
Free tier: ~2,500 queries/month.

Subcommands:

  paa         People Also Ask questions for a query.
  search      Organic SERP results (top 10).
  related     Related searches Google shows at the bottom.
  full        PAA + organic + related in one call.

Usage:
    python3 scripts/serper.py paa "what is a positive constraint"
    python3 scripts/serper.py search "constraint thinking"
    python3 scripts/serper.py related "deliberate limitation"
    python3 scripts/serper.py full "positive constraint" --json

Limitations:
  - Free tier is 2,500 queries/month. Each subcommand is one query.
  - PAA trees vary by location and personalisation. Results here reflect
    the US/en defaults, not a specific user's SERP.
"""
import argparse
import json
import os
import sys
import urllib.request

API_BASE = "https://google.serper.dev"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS = os.path.join(ROOT, ".claude", "secrets", "serper.env")


def api_key():
    key = os.environ.get("SERPER_API_KEY", "").strip()
    if key:
        return key
    if os.path.exists(SECRETS):
        with open(SECRETS) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("SERPER_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip("'\"")
                    if key:
                        return key
    sys.exit(
        f"No API key. Sign up at https://serper.dev (free tier: 2,500 queries/month),\n"
        f"then put SERPER_API_KEY=<key> in {SECRETS}\n"
        "(or export SERPER_API_KEY in the environment)."
    )


def call(endpoint, payload):
    url = f"{API_BASE}/{endpoint}"
    headers = {
        "X-API-KEY": api_key(),
        "Content-Type": "application/json",
        "User-Agent": "posconcom-serper/1",
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:800]
        sys.exit(f"HTTP {e.code}: {body}")


def _search(query, gl="us", hl="en", num=10):
    return call("search", {"q": query, "gl": gl, "hl": hl, "num": num})


def cmd_paa(args):
    resp = _search(args.query, args.country, args.lang)
    paa = resp.get("peopleAlsoAsk", [])

    if args.json:
        json.dump({"query": args.query, "peopleAlsoAsk": paa}, sys.stdout, indent=2)
        print()
        return

    if not paa:
        print(f"No People Also Ask results for '{args.query}'")
        return

    print(f"People Also Ask for '{args.query}':\n")
    for i, item in enumerate(paa, 1):
        question = item.get("question", "")
        snippet = item.get("snippet", "")
        source = item.get("link", "")
        print(f"  {i}. {question}")
        if snippet:
            print(f"     {snippet[:120]}")
        if source:
            print(f"     → {source}")
        print()


def cmd_search(args):
    resp = _search(args.query, args.country, args.lang)
    organic = resp.get("organic", [])

    if args.json:
        json.dump({"query": args.query, "organic": organic}, sys.stdout, indent=2)
        print()
        return

    if not organic:
        print(f"No organic results for '{args.query}'")
        return

    print(f"Organic results for '{args.query}':\n")
    for item in organic[:10]:
        pos = item.get("position", "?")
        title = item.get("title", "")
        url = item.get("link", "")
        snippet = (item.get("snippet") or "")[:100]
        print(f"  {pos:>2}. {title}")
        print(f"      {url}")
        if snippet:
            print(f"      {snippet}")
        print()


def cmd_related(args):
    resp = _search(args.query, args.country, args.lang)
    related = resp.get("relatedSearches", [])

    if args.json:
        json.dump({"query": args.query, "relatedSearches": related}, sys.stdout, indent=2)
        print()
        return

    if not related:
        print(f"No related searches for '{args.query}'")
        return

    print(f"Related searches for '{args.query}':\n")
    for item in related:
        print(f"  • {item.get('query', '')}")


def cmd_full(args):
    resp = _search(args.query, args.country, args.lang)

    if args.json:
        json.dump(resp, sys.stdout, indent=2)
        print()
        return

    # PAA
    paa = resp.get("peopleAlsoAsk", [])
    if paa:
        print(f"People Also Ask for '{args.query}':\n")
        for i, item in enumerate(paa, 1):
            print(f"  {i}. {item.get('question', '')}")
        print()

    # Organic
    organic = resp.get("organic", [])
    if organic:
        print(f"Top organic results:\n")
        for item in organic[:5]:
            pos = item.get("position", "?")
            title = item.get("title", "")
            url = item.get("link", "")
            print(f"  {pos:>2}. {title}")
            print(f"      {url}")
        print()

    # Related
    related = resp.get("relatedSearches", [])
    if related:
        print(f"Related searches:\n")
        for item in related:
            print(f"  • {item.get('query', '')}")

    # Knowledge graph
    kg = resp.get("knowledgeGraph", {})
    if kg:
        print(f"\nKnowledge Graph: {kg.get('title', '')} — {kg.get('type', '')}")
        desc = kg.get("description", "")
        if desc:
            print(f"  {desc[:150]}")


def main():
    p = argparse.ArgumentParser(description="Serper.dev — PAA trees and SERP structure")
    p.add_argument("--json", action="store_true", help="raw JSON output")
    p.add_argument("--country", default="us", help="country code (us, gb, etc.)")
    p.add_argument("--lang", default="en", help="language code")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("paa", help="People Also Ask questions")
    s.add_argument("query")

    o = sub.add_parser("search", help="organic SERP results")
    o.add_argument("query")

    r = sub.add_parser("related", help="related searches")
    r.add_argument("query")

    f = sub.add_parser("full", help="PAA + organic + related in one call")
    f.add_argument("query")

    args = p.parse_args()
    {"paa": cmd_paa, "search": cmd_search, "related": cmd_related,
     "full": cmd_full}[args.cmd](args)


if __name__ == "__main__":
    main()
