#!/usr/bin/env python3
"""Google Trends — relative interest and rising queries.

Stdlib only, no venv needed. Queries Google Trends' internal endpoints directly
(same approach as google_autocomplete.py). No auth required.

Subcommands:

  interest    Relative interest-over-time for a term (12-month default).
  rising      Rising and top related queries for a term.
  compare     Compare up to 5 terms side by side.

Usage:
    python3 scripts/google_trends.py interest "positive constraint"
    python3 scripts/google_trends.py rising "constraint thinking"
    python3 scripts/google_trends.py compare "constraints" "limitations" "restrictions"
    python3 scripts/google_trends.py interest "positive constraint" --json

Limitations:
  - Values are RELATIVE (0-100 index), not absolute volumes. A score of 50
    means half the peak interest in the time range — not 50 searches.
  - Low-volume terms may return empty results. This is not a bug: Google
    Trends suppresses data below a privacy threshold.
  - Google may throttle aggressive use. The script rate-limits to 2 req/sec.
"""
import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request

EXPLORE_URL = "https://trends.google.com/trends/api/explore"
INTEREST_URL = "https://trends.google.com/trends/api/widgetdata/multiline"
RELATED_URL = "https://trends.google.com/trends/api/widgetdata/relatedsearches"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "application/json",
}
RATE_LIMIT = 2.0

_last_t = 0.0


def _throttle():
    global _last_t
    elapsed = time.monotonic() - _last_t
    if elapsed < RATE_LIMIT:
        time.sleep(RATE_LIMIT - elapsed)
    _last_t = time.monotonic()


def _fetch(url, params=None):
    _throttle()
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    # Google prepends ")]}',\n" to JSON responses
    if raw.startswith(")]}'"):
        raw = raw.split("\n", 1)[1]
    return json.loads(raw)


def _get_widgets(keywords, timeframe="today 12-m", geo="US"):
    """Get widget tokens from the explore endpoint."""
    comparison_items = []
    for kw in keywords[:5]:
        comparison_items.append({
            "keyword": kw,
            "geo": geo,
            "time": timeframe,
        })
    req_params = {
        "comparisonItem": comparison_items,
        "category": 0,
        "property": "",
    }
    params = {
        "hl": "en-US",
        "tz": 360,
        "req": json.dumps(req_params),
    }
    data = _fetch(EXPLORE_URL, params)
    return data.get("widgets", [])


def _find_widget(widgets, widget_id):
    for w in widgets:
        if w.get("id") == widget_id:
            return w
    return None


def cmd_interest(args):
    keywords = [args.query] if isinstance(args.query, str) else [args.query]
    try:
        widgets = _get_widgets(keywords, args.timeframe, args.geo)
    except Exception as e:
        print(f"Could not fetch trends data: {e}", file=sys.stderr)
        print("\nFallback: use Google Trends in a browser at:")
        print(f"  https://trends.google.com/trends/explore?q={urllib.parse.quote(args.query)}&geo={args.geo}")
        return

    widget = _find_widget(widgets, "TIMESERIES")
    if not widget:
        print("No time series widget found. Term may be below Google's threshold.")
        return

    req = widget.get("request", {})
    token = widget.get("token", "")
    params = {
        "hl": "en-US",
        "tz": 360,
        "req": json.dumps(req),
        "token": token,
    }
    data = _fetch(INTEREST_URL, params)
    timeline = data.get("default", {}).get("timelineData", [])

    if not timeline:
        print(f"No trend data for '{args.query}'")
        return

    if args.json:
        out = {"query": args.query, "timeframe": args.timeframe, "geo": args.geo, "data": []}
        for point in timeline:
            out["data"].append({
                "date": point.get("formattedTime", ""),
                "value": point.get("value", [0])[0],
            })
        json.dump(out, sys.stdout, indent=2)
        print()
        return

    values = [p.get("value", [0])[0] for p in timeline]
    peak = max(values) if values else 0
    latest = values[-1] if values else 0
    avg = sum(values) / len(values) if values else 0

    print(f"Interest over time for '{args.query}':")
    print(f"  Timeframe: {args.timeframe}, Geo: {args.geo or 'worldwide'}")
    print(f"  Peak: {peak}  Latest: {latest}  Avg: {avg:.0f}")
    print()

    # Sparkline of recent months
    recent = timeline[-12:] if len(timeline) > 12 else timeline
    for point in recent:
        val = point.get("value", [0])[0]
        bar = "█" * (val // 5) if val > 0 else ""
        print(f"  {point.get('formattedTime', ''):20s}  {val:3d}  {bar}")


def cmd_rising(args):
    try:
        widgets = _get_widgets([args.query], args.timeframe, args.geo)
    except Exception as e:
        print(f"Could not fetch trends data: {e}", file=sys.stderr)
        return

    widget = _find_widget(widgets, "RELATED_QUERIES")
    if not widget:
        print("No related queries widget found.")
        return

    req = widget.get("request", {})
    token = widget.get("token", "")
    params = {
        "hl": "en-US",
        "tz": 360,
        "req": json.dumps(req),
        "token": token,
    }
    data = _fetch(RELATED_URL, params)

    ranked = data.get("default", {}).get("rankedList", [])

    if args.json:
        out = {"query": args.query, "rising": [], "top": []}
        for group in ranked:
            keywords = group.get("rankedKeyword", [])
            label = "rising" if any("Breakout" in str(kw.get("formattedValue", "")) or
                                    str(kw.get("formattedValue", "")).endswith("%")
                                    for kw in keywords) else "top"
            for kw in keywords:
                out[label].append({
                    "query": kw.get("query", ""),
                    "value": kw.get("formattedValue", ""),
                })
        json.dump(out, sys.stdout, indent=2)
        print()
        return

    print(f"Related queries for '{args.query}':")
    for i, group in enumerate(ranked):
        keywords = group.get("rankedKeyword", [])
        if not keywords:
            continue
        label = "Top" if i == 0 else "Rising"
        print(f"\n  {label}:")
        for kw in keywords[:10]:
            q = kw.get("query", "")
            v = kw.get("formattedValue", "")
            print(f"    {q:40s}  {v}")


def cmd_compare(args):
    keywords = args.queries[:5]
    try:
        widgets = _get_widgets(keywords, args.timeframe, args.geo)
    except Exception as e:
        print(f"Could not fetch trends data: {e}", file=sys.stderr)
        return

    widget = _find_widget(widgets, "TIMESERIES")
    if not widget:
        print("No time series data returned.")
        return

    req = widget.get("request", {})
    token = widget.get("token", "")
    params = {
        "hl": "en-US",
        "tz": 360,
        "req": json.dumps(req),
        "token": token,
    }
    data = _fetch(INTEREST_URL, params)
    timeline = data.get("default", {}).get("timelineData", [])

    if args.json:
        out = {"queries": keywords, "data": []}
        for point in timeline:
            entry = {"date": point.get("formattedTime", "")}
            for i, kw in enumerate(keywords):
                vals = point.get("value", [])
                entry[kw] = vals[i] if i < len(vals) else 0
            out["data"].append(entry)
        json.dump(out, sys.stdout, indent=2)
        print()
        return

    print(f"Comparison: {', '.join(keywords)}")
    print(f"  Timeframe: {args.timeframe}\n")
    for i, kw in enumerate(keywords):
        values = [p.get("value", [])[i] if i < len(p.get("value", [])) else 0
                  for p in timeline]
        if values:
            print(f"  {kw}: peak={max(values)} latest={values[-1]} avg={sum(values)/len(values):.0f}")


def main():
    p = argparse.ArgumentParser(description="Google Trends — relative interest data")
    p.add_argument("--json", action="store_true", help="raw JSON output")
    p.add_argument("--timeframe", default="today 12-m",
                   help="e.g. 'today 12-m', 'today 3-m', '2024-01-01 2024-12-31'")
    p.add_argument("--geo", default="US", help="geo code: 'US', 'GB', '' for worldwide")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("interest", help="interest over time for a term")
    s.add_argument("query")

    r = sub.add_parser("rising", help="rising and top related queries")
    r.add_argument("query")

    c = sub.add_parser("compare", help="compare up to 5 terms")
    c.add_argument("queries", nargs="+")

    args = p.parse_args()
    {"interest": cmd_interest, "rising": cmd_rising, "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    main()
