#!/usr/bin/env python3
"""Bing Webmaster Tools client for positiveconstraint.com.

SCOPE — deliberately narrow. Google Search Console, GA4 and the Cloudflare
serve-signal pipeline already cover query/click/traffic reporting and AI-fetcher
detection. This tool does NOT duplicate them. It covers only what Bing alone
gives:

  1. GATE     Is a page in Bing's index? Bing is ChatGPT's search backend, so a
              page Bing has not indexed cannot be cited by ChatGPT. GSC cannot
              answer this. -> `coverage`, `index`, `sitemap`, `crawl`, `issues`
  2. DEMAND   Bing reports real search volume for a term. Google gives no free
              equivalent. -> `keyword`, `related`, `history`
  3. PUSH     Direct submit to Bing's index, the fastest path to ChatGPT
              freshness. -> `submit`, `quota`
  4. VALIDATE Bing-side query/page stats, used only to cross-check GSC — not as
              a primary report. -> `queries`, `pages`

Protocol: JSON/HTTP (REST) only. Bing retires SOAP and POX on 2026-08-31;
JSON/HTTP stays supported. Never add /soap/ or /pox/ calls here.

Auth: one per-user API key (not per-site), passed as the `apikey` query param.
Bing WMT -> Settings -> API Access -> API Key -> Generate. Only one key exists
per user; regenerating breaks every other consumer of the old key.
Lookup order: $BING_WMT_API_KEY, then .claude/secrets/bing.env (gitignored).

Usage:
    python3 scripts/bing_wmt.py sites
    python3 scripts/bing_wmt.py sitemap
    python3 scripts/bing_wmt.py coverage
    python3 scripts/bing_wmt.py index --url https://positiveconstraint.com/ideas/core-constraints/ --json
    python3 scripts/bing_wmt.py keyword --q "strategic clarity"
    python3 scripts/bing_wmt.py related --q "strategic clarity"
    python3 scripts/bing_wmt.py submit --url https://positiveconstraint.com/ideas/abstraction/
    python3 scripts/bing_wmt.py queries --top 30
    python3 scripts/bing_wmt.py raw GetRankAndTrafficStats

--json on any subcommand prints the raw parsed payload. Use it whenever a table
shows "-" everywhere: it reveals the real field names Bing returned.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://ssl.bing.com/webmaster/api.svc/json"
SITE_URL = "https://positiveconstraint.com/"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS = os.path.join(ROOT, ".claude", "secrets", "bing.env")
SITEMAP = os.path.join(ROOT, "site", "sitemap.xml")

# Waits after a ThrottleHost response, in seconds. Measured against the live
# API 2026-08-12: a GetUrlInfo loop at 1.5s spacing trips the throttle after
# roughly 10 calls, and short retries do not clear it.
THROTTLE_BACKOFF = [30, 60, 120, 240]

# Bing serializes dates in the legacy ASP.NET form: /Date(1754870400000)/
_MS_DATE = re.compile(r"^/Date\((-?\d+)([+-]\d{4})?\)/$")


def api_key():
    key = os.environ.get("BING_WMT_API_KEY", "").strip()
    if key:
        return key
    if os.path.exists(SECRETS):
        with open(SECRETS) as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("BING_WMT_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip("'\"")
                    if key:
                        return key
    sys.exit(
        "No API key. Generate one at Bing Webmaster Tools -> Settings -> API Access,\n"
        f"then put BING_WMT_API_KEY=<key> in {SECRETS}\n"
        "(or export BING_WMT_API_KEY in the environment)."
    )


def call(method, params=None, body=None, soft=False, retries=4):
    """Call a JSON/HTTP method. POST when a body is given, else GET.

    Bing throttles rapid sequential calls: a tight GetUrlInfo loop starts
    faulting after ~10 requests even though each URL answers fine on its own.
    Retry with exponential backoff so a throttled call is never mistaken for
    "Bing does not know this URL". soft=True returns None once retries are
    exhausted instead of exiting.
    """
    for attempt in range(retries):
        try:
            return _call_once(method, params, body)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            # Bing signals throttling as HTTP 400 with ErrorCode 5 /
            # "ThrottleHost" — NOT 429. Detect it in the body, never by code.
            throttled = "ThrottleHost" in detail or '"ErrorCode":5' in detail
            transient = throttled or e.code in (429, 500, 502, 503, 504)
            if not transient or attempt == retries - 1:
                if soft:
                    return None
                sys.exit(f"HTTP {e.code} calling {method}\n{detail[:800]}")
            # The throttle is a rolling host window, so back off in tens of
            # seconds. Retrying fast only extends it.
            time.sleep(THROTTLE_BACKOFF[min(attempt, len(THROTTLE_BACKOFF) - 1)]
                       if throttled else 2 ** attempt)
        except urllib.error.URLError:
            if attempt == retries - 1:
                if soft:
                    return None
                raise
            time.sleep(2 ** attempt)
    return None


def _call_once(method, params=None, body=None):
    q = {"apikey": api_key()}
    q.update(params or {})
    url = f"{BASE}/{method}?" + urllib.parse.urlencode(q)
    data = None
    headers = {"Accept": "application/json", "User-Agent": "posconcom-bing-wmt/1"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8-sig") or "{}")
    return decode_dates(payload.get("d", payload))


def decode_dates(obj):
    if isinstance(obj, dict):
        return {k: decode_dates(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decode_dates(v) for v in obj]
    if isinstance(obj, str):
        m = _MS_DATE.match(obj)
        if m:
            ts = int(m.group(1)) / 1000
            return dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat()
    return obj


def market(country, language):
    """Normalise the keyword-API market pair.

    Verified against the live API 2026-08-12: `country` must be lowercase
    ("us" works, "US" is rejected) and `language` must be lowercase-dash-
    UPPERCASE ("en-US" works, "en-us" and "en" are rejected). Both faults
    return the same opaque "argument was out of the range of valid values",
    so normalise here rather than make the caller guess.

    Note `il` is accepted but carries no data — Bing reports zero volume for
    every Israeli query. Use `us`, or `gb` for the UK.
    """
    country = country.strip().lower()
    language = language.strip()
    if "-" in language:
        lang, _, region = language.partition("-")
        language = f"{lang.lower()}-{region.upper()}"
    return country, language


def sitemap_urls():
    if not os.path.exists(SITEMAP):
        sys.exit(f"No sitemap at {SITEMAP}")
    with open(SITEMAP) as fh:
        return re.findall(r"<loc>([^<]+)</loc>", fh.read())


def fmt(v):
    if v is None or v == "":
        return "-"
    if isinstance(v, float):
        return f"{v:.1f}"
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v)


def table(rows, cols, limit=None):
    if not rows:
        print("(no rows — Bing has no data for this site or date range yet)")
        return
    rows = rows[:limit] if limit else rows
    widths = [max(len(h), *(len(fmt(r.get(k))) for r in rows)) for k, h in cols]
    print("  ".join(h.ljust(w) for (_, h), w in zip(cols, widths)))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(fmt(r.get(k)).ljust(w) for (k, _), w in zip(cols, widths)))
    print(f"\n{len(rows)} row(s)")
    # Tell the user when the chosen columns found nothing — the field names differ.
    present = {k for k, _ in cols if any(r.get(k) not in (None, "") for r in rows)}
    if not present and rows:
        print(f"NOTE: none of those fields were present. Actual keys: "
              f"{', '.join(sorted(rows[0].keys()))}\nRe-run with --json.")


def emit(data, cols, args, limit=None, sort_key=None):
    if args.json:
        print(json.dumps(data, indent=2))
        return
    rows = data if isinstance(data, list) else ([data] if data else [])
    if sort_key:
        rows = sorted(rows, key=lambda r: r.get(sort_key) or 0, reverse=True)
    table(rows, cols, limit)


def cmd_coverage(args):
    """The ChatGPT gate: which of our pages does Bing actually have indexed?"""
    urls = sitemap_urls()
    rows = []
    for i, u in enumerate(urls):
        if i:
            time.sleep(args.pace)  # Bing throttles tight loops; pace the walk.
        info = call("GetUrlInfo", {"siteUrl": args.site, "url": u}, soft=True)
        if isinstance(info, list):
            info = info[0] if info else None
        if info is None:
            state = "API-ERROR"  # never conflate a failed call with "not in index"
            info = {}
        else:
            # Three real states. Bing answers for every URL, so absence shows up
            # as the sentinel date 0001-01-01, not as a missing row. A merely
            # discovered URL has a real DiscoveryDate but DocumentSize 0 —
            # Bing knows the address and has not fetched the body.
            discovered = (info.get("DiscoveryDate") or "").startswith("0001-01-01")
            size = info.get("DocumentSize") or 0
            state = "indexed" if size > 0 else ("not-known" if discovered else "discovered")
        rows.append({
            "Url": u.replace("https://positiveconstraint.com", ""),
            "State": state,
            "DiscoveryDate": None if state in ("not-known", "API-ERROR") else info.get("DiscoveryDate"),
            "LastCrawledDate": None if state in ("not-known", "API-ERROR") else info.get("LastCrawledDate"),
            "DocumentSize": info.get("DocumentSize"),
            "AnchorCount": info.get("AnchorCount"),
        })
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    table(rows, [("Url", "PATH"), ("State", "STATE"), ("DiscoveryDate", "DISCOVERED"),
                 ("LastCrawledDate", "LAST CRAWLED"),
                 ("DocumentSize", "BYTES"), ("AnchorCount", "ANCHORS")])
    n = len(urls)
    counts = {}
    for r in rows:
        counts[r["State"]] = counts.get(r["State"], 0) + 1
    print()
    for state, label in [("indexed", "Indexed (body fetched) — citable by ChatGPT via Bing"),
                         ("discovered", "Discovered, body never fetched"),
                         ("not-known", "Not known to Bing at all"),
                         ("API-ERROR", "Call failed — rerun, NOT a verdict")]:
        if counts.get(state):
            print(f"{label}: {counts[state]}/{n}")


def main():
    # Shared flags, accepted either before or after the subcommand. The parent
    # copy suppresses its default so an absent flag never clobbers a value
    # already set on the main parser; set_defaults supplies the base values.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--site", default=argparse.SUPPRESS,
                        help=f"siteUrl exactly as verified in Bing WMT (default: {SITE_URL})")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="print raw JSON")

    p = argparse.ArgumentParser(description=__doc__, parents=[common],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.set_defaults(site=SITE_URL, json=False)
    sub = p.add_subparsers(dest="cmd", required=True)

    _add = sub.add_parser
    sub.add_parser = lambda *a, **kw: _add(*a, parents=[common], **kw)

    # --- setup ---
    sub.add_parser("sites", help="GetUserSites — the exact siteUrl strings Bing knows")

    # --- 1. gate: indexing ---
    s = sub.add_parser("coverage", help="index status for every URL in site/sitemap.xml")
    s.add_argument("--pace", type=float, default=3.0,
                   help="seconds between calls; Bing throttles tight loops (default: %(default)s)")
    s = sub.add_parser("index", help="GetUrlInfo — index detail for one page")
    s.add_argument("--url", required=True)
    sub.add_parser("sitemap", help="GetFeeds — did the submitted sitemap process?")
    sub.add_parser("crawl", help="GetCrawlStats — crawl volume, 4xx/5xx, robots blocks")
    sub.add_parser("issues", help="GetCrawlIssues — what stops Bing indexing us")

    # --- 2. demand: keyword research (no free Google equivalent) ---
    for name, help_ in [("keyword", "GetKeyword — search volume for one term"),
                        ("related", "GetRelatedKeywords — adjacent terms + volume")]:
        s = sub.add_parser(name, help=help_)
        s.add_argument("--q", required=True)
        s.add_argument("--country", default="us", help="lowercase two-letter code; il has no data (default: %(default)s)")
        s.add_argument("--language", default="en-US", help="xx-YY form, e.g. en-US, en-GB (default: %(default)s)")
        s.add_argument("--days", type=int, default=90)
    s = sub.add_parser("history", help="GetKeywordStats — volume trend for one term")
    s.add_argument("--q", required=True)
    s.add_argument("--country", default="us")
    s.add_argument("--language", default="en-US")

    # --- 3. push ---
    s = sub.add_parser("submit", help="SubmitUrlBatch — push URLs into Bing's index now")
    s.add_argument("--url", action="append", dest="urls",
                   help="repeatable; omit to submit every URL in site/sitemap.xml")
    sub.add_parser("quota", help="GetUrlSubmissionQuota — submit budget left")

    # --- 4. validate against GSC ---
    for name, help_ in [("queries", "GetQueryStats — cross-check GSC queries"),
                        ("pages", "GetPageStats — cross-check GSC pages")]:
        s = sub.add_parser(name, help=help_)
        s.add_argument("--top", type=int, default=30)

    s = sub.add_parser("raw", help="call any JSON method directly")
    s.add_argument("method")
    s.add_argument("params", nargs="*", help="key=value pairs")

    args = p.parse_args()
    site = {"siteUrl": args.site}

    if args.cmd == "sites":
        emit(call("GetUserSites"),
             [("Url", "URL"), ("IsVerified", "VERIFIED")], args)

    elif args.cmd == "coverage":
        cmd_coverage(args)

    elif args.cmd == "index":
        d = call("GetUrlInfo", {"siteUrl": args.site, "url": args.url})
        emit(d, [("Url", "URL"), ("LastCrawledDate", "LAST CRAWLED"),
                 ("HttpStatus", "HTTP"), ("DocumentSize", "BYTES"),
                 ("AnchorTextCount", "ANCHORS"), ("TotalChildUrlCount", "CHILD URLS"),
                 ("DiscoveryDate", "DISCOVERED")], args)

    elif args.cmd == "sitemap":
        emit(call("GetFeeds", site),
             [("Url", "FEED"), ("LastCrawled", "LAST CRAWLED"), ("Submitted", "SUBMITTED"),
              ("UrlCount", "URLS"), ("UrlWithErrors", "ERRORS"), ("Status", "STATUS")], args)

    elif args.cmd == "crawl":
        emit(call("GetCrawlStats", site),
             [("Date", "DATE"), ("CrawledPages", "CRAWLED"), ("InIndex", "IN INDEX"),
              ("InLinks", "INLINKS"), ("Code4xx", "4XX"), ("Code5xx", "5XX"),
              ("BlockedByRobotsTxt", "ROBOTS"), ("AllOtherCodes", "OTHER")], args)

    elif args.cmd == "issues":
        emit(call("GetCrawlIssues", site),
             [("Url", "URL"), ("HttpCode", "HTTP"), ("Issues", "ISSUES"),
              ("InLinks", "INLINKS"), ("DiscoveryDate", "DISCOVERED")], args)

    elif args.cmd in ("keyword", "related"):
        country, language = market(args.country, args.language)
        end = dt.date.today()
        start = end - dt.timedelta(days=args.days)
        method = "GetKeyword" if args.cmd == "keyword" else "GetRelatedKeywords"
        d = call(method, {"q": args.q, "country": country, "language": language,
                          "startDate": start.isoformat(), "endDate": end.isoformat()})
        emit(d, [("Query", "KEYWORD"), ("Impressions", "VOLUME"),
                 ("BroadImpressions", "BROAD")], args, sort_key="Impressions")

    elif args.cmd == "history":
        country, language = market(args.country, args.language)
        d = call("GetKeywordStats", {"q": args.q, "country": country, "language": language})
        emit(d, [("Date", "DATE"), ("Impressions", "VOLUME")], args)

    elif args.cmd == "submit":
        urls = args.urls or sitemap_urls()
        call("SubmitUrlBatch", site, body={"siteUrl": args.site, "urlList": urls})
        print(f"submitted {len(urls)} URL(s) to Bing")
        emit(call("GetUrlSubmissionQuota", site),
             [("DailyQuota", "DAILY LEFT"), ("MonthlyQuota", "MONTHLY LEFT")], args)

    elif args.cmd == "quota":
        emit(call("GetUrlSubmissionQuota", site),
             [("DailyQuota", "DAILY LEFT"), ("MonthlyQuota", "MONTHLY LEFT")], args)

    elif args.cmd == "queries":
        emit(call("GetQueryStats", site),
             [("Query", "QUERY"), ("Impressions", "IMPR"), ("Clicks", "CLICKS"),
              ("AvgImpressionPosition", "AVG POS")],
             args, limit=args.top, sort_key="Impressions")

    elif args.cmd == "pages":
        emit(call("GetPageStats", site),
             [("Query", "PAGE"), ("Impressions", "IMPR"), ("Clicks", "CLICKS"),
              ("AvgImpressionPosition", "AVG POS")],
             args, limit=args.top, sort_key="Impressions")

    elif args.cmd == "raw":
        params = dict(kv.split("=", 1) for kv in args.params)
        params.setdefault("siteUrl", args.site)
        print(json.dumps(call(args.method, params), indent=2))


if __name__ == "__main__":
    main()
