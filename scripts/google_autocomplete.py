#!/usr/bin/env python3
"""Google Autocomplete — live long-tail intent discovery.

No auth, no API key. Queries Google's public suggestion endpoint to surface
what people actually type. Stdlib only, no venv needed.

Subcommands:

  suggest   Autocomplete suggestions for a term.
  tree      Two-level expansion: seed → suggestions → each suggestion expanded.
  alphabet  Seed + each letter a-z appended, shows the spread of intent.

Usage:
    python3 scripts/google_autocomplete.py suggest "positive constraint"
    python3 scripts/google_autocomplete.py tree "constraint thinking"
    python3 scripts/google_autocomplete.py alphabet "deliberate limitation"
    python3 scripts/google_autocomplete.py suggest "positive constraint" --json

Limitations:
  - Suggestions reflect current Google Search popularity. As search shifts to
    AI, these signals will lag behind AI-native queries.
  - No volume numbers — only ranked suggestions. Use DataForSEO or Bing WMT
    for actual volumes on terms discovered here.
  - Google may throttle aggressive use. The script rate-limits to 1 req/sec.
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

ENDPOINT = "https://suggestqueries.google.com/complete/search"
HEADERS = {"User-Agent": "posconcom-autocomplete/1"}
RATE_LIMIT = 1.0  # seconds between requests


def _last_call():
    if not hasattr(_last_call, "t"):
        _last_call.t = 0.0
    return _last_call.t


def _throttle():
    elapsed = time.monotonic() - _last_call()
    if elapsed < RATE_LIMIT:
        time.sleep(RATE_LIMIT - elapsed)
    _last_call.t = time.monotonic()


def fetch_suggestions(query, lang="en", country="us"):
    _throttle()
    params = urllib.parse.urlencode({
        "client": "firefox",
        "q": query,
        "hl": lang,
        "gl": country,
    })
    url = f"{ENDPOINT}?{params}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data[1] if isinstance(data, list) and len(data) > 1 else []
    except Exception as e:
        print(f"  warning: {e}", file=sys.stderr)
        return []


def cmd_suggest(args):
    results = fetch_suggestions(args.query, args.lang, args.country)
    if args.json:
        json.dump({"query": args.query, "suggestions": results}, sys.stdout, indent=2)
        print()
        return
    if not results:
        print(f"No suggestions for '{args.query}'")
        return
    print(f"Suggestions for '{args.query}':")
    for i, s in enumerate(results, 1):
        print(f"  {i:2}. {s}")


def cmd_tree(args):
    root = fetch_suggestions(args.query, args.lang, args.country)
    tree = {"query": args.query, "branches": []}
    print(f"Tree for '{args.query}':")
    for s in root:
        children = fetch_suggestions(s, args.lang, args.country)
        tree["branches"].append({"suggestion": s, "expansions": children})
        print(f"\n  {s}")
        for c in children[:5]:
            print(f"    → {c}")
    if args.json:
        json.dump(tree, sys.stdout, indent=2)
        print()


def cmd_alphabet(args):
    all_results = {}
    print(f"Alphabet expansion for '{args.query}':")
    for letter in "abcdefghijklmnopqrstuvwxyz":
        expanded = f"{args.query} {letter}"
        suggestions = fetch_suggestions(expanded, args.lang, args.country)
        all_results[letter] = suggestions
        if suggestions:
            print(f"\n  {args.query} {letter}:")
            for s in suggestions[:5]:
                print(f"    {s}")
    if args.json:
        json.dump({"query": args.query, "alphabet": all_results}, sys.stdout, indent=2)
        print()


def main():
    p = argparse.ArgumentParser(description="Google Autocomplete intent discovery")
    p.add_argument("--json", action="store_true", help="raw JSON output")
    p.add_argument("--lang", default="en")
    p.add_argument("--country", default="us")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("suggest", help="autocomplete suggestions for a term")
    s.add_argument("query")

    t = sub.add_parser("tree", help="two-level suggestion expansion")
    t.add_argument("query")

    a = sub.add_parser("alphabet", help="seed + a-z letter expansion")
    a.add_argument("query")

    args = p.parse_args()
    {"suggest": cmd_suggest, "tree": cmd_tree, "alphabet": cmd_alphabet}[args.cmd](args)


if __name__ == "__main__":
    main()
