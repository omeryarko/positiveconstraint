#!/usr/bin/env python3
"""GA4 event and traffic data for positiveconstraint.com.

Pulls engagement signals the SEO system needs: which ideas get copied or
downloaded (resonance), traffic sources, and page-level engagement.

Auth: Application Default Credentials.
Scopes required: analytics.readonly.

Property: 532406062 (Positive Constraint, under Braintail account).
Venv: .venv-analytics/ (has google-analytics-data, google-auth).

Note: raw GA4 is ~49% owner noise. The clean segment excludes Haifa +
known bot cities (see analytics-access.md). This script applies that
filter by default; pass --raw to skip it.

Usage:
    .venv-analytics/bin/python3 scripts/ga4_query.py events
    .venv-analytics/bin/python3 scripts/ga4_query.py events --days 90
    .venv-analytics/bin/python3 scripts/ga4_query.py traffic
    .venv-analytics/bin/python3 scripts/ga4_query.py pages --top 20
    .venv-analytics/bin/python3 scripts/ga4_query.py events --json --raw
"""
import argparse
import json
import sys

PROPERTY = "properties/532406062"
EXCLUDE_CITIES = ["Haifa", "Ashburn", "Glenview", "San Jose",
                  "Des Moines", "Hialeah Gardens", "Flint Hill"]


def make_client():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    return BetaAnalyticsDataClient()


def date_range_str(days):
    return f"{days}daysAgo", "today"


def city_filter(raw):
    if raw:
        return None
    from google.analytics.data_v1beta.types import (
        FilterExpression, FilterExpressionList, Filter)
    filters = []
    for city in EXCLUDE_CITIES:
        filters.append(FilterExpression(
            not_expression=FilterExpression(
                filter=Filter(
                    field_name="city",
                    string_filter=Filter.StringFilter(
                        value=city,
                        match_type=Filter.StringFilter.MatchType.EXACT,
                    )))))
    return FilterExpression(
        and_group=FilterExpressionList(expressions=filters))


def cmd_events(client, args):
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric, OrderBy)

    start, end = date_range_str(args.days)
    req = RunReportRequest(
        property=PROPERTY,
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name="eventName"),
                    Dimension(name="pagePath")],
        metrics=[Metric(name="eventCount")],
        dimension_filter=city_filter(args.raw),
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(
            metric_name="eventCount"), desc=True)],
        limit=args.top,
    )
    resp = client.run_report(req)
    rows = []
    for row in resp.rows:
        event = row.dimension_values[0].value
        if event not in ("idea_copy", "idea_download", "copy_markdown",
                         "download_markdown"):
            continue
        rows.append({
            "event": event,
            "page": row.dimension_values[1].value,
            "count": int(row.metric_values[0].value),
        })
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print(f"No idea_copy/idea_download events in last {args.days} days.")
        return
    print(f"Idea engagement events, last {args.days} days"
          f"{' (raw, no city filter)' if args.raw else ''}:")
    print(f"{'Event':<25} {'Page':<50} {'Count':>6}")
    print("-" * 83)
    for r in rows:
        print(f"{r['event']:<25} {r['page']:<50} {r['count']:>6}")


def cmd_traffic(client, args):
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric, OrderBy)

    start, end = date_range_str(args.days)
    req = RunReportRequest(
        property=PROPERTY,
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name="sessionSource"),
                    Dimension(name="sessionMedium")],
        metrics=[Metric(name="sessions"),
                 Metric(name="engagedSessions")],
        dimension_filter=city_filter(args.raw),
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(
            metric_name="sessions"), desc=True)],
        limit=args.top,
    )
    resp = client.run_report(req)
    rows = [{"source": r.dimension_values[0].value,
             "medium": r.dimension_values[1].value,
             "sessions": int(r.metric_values[0].value),
             "engaged": int(r.metric_values[1].value)}
            for r in resp.rows]
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print(f"No traffic data in last {args.days} days.")
        return
    print(f"Traffic sources, last {args.days} days"
          f"{' (raw)' if args.raw else ''}:")
    print(f"{'Source':<30} {'Medium':<15} {'Sessions':>9} {'Engaged':>9}")
    print("-" * 66)
    for r in rows:
        print(f"{r['source']:<30} {r['medium']:<15} "
              f"{r['sessions']:>9} {r['engaged']:>9}")


def cmd_pages(client, args):
    from google.analytics.data_v1beta.types import (
        RunReportRequest, DateRange, Dimension, Metric, OrderBy)

    start, end = date_range_str(args.days)
    req = RunReportRequest(
        property=PROPERTY,
        date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="screenPageViews"),
                 Metric(name="engagementRate"),
                 Metric(name="averageSessionDuration")],
        dimension_filter=city_filter(args.raw),
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(
            metric_name="screenPageViews"), desc=True)],
        limit=args.top,
    )
    resp = client.run_report(req)
    rows = [{"page": r.dimension_values[0].value,
             "views": int(r.metric_values[0].value),
             "eng_rate": float(r.metric_values[1].value),
             "avg_dur": float(r.metric_values[2].value)}
            for r in resp.rows]
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        print(f"No page data in last {args.days} days.")
        return
    print(f"Top {len(rows)} pages, last {args.days} days"
          f"{' (raw)' if args.raw else ''}:")
    print(f"{'Page':<55} {'Views':>6} {'Eng%':>6} {'AvgDur':>7}")
    print("-" * 77)
    for r in rows:
        print(f"{r['page']:<55} {r['views']:>6} {r['eng_rate']:>5.0%} "
              f"{r['avg_dur']:>6.0f}s")


def main():
    p = argparse.ArgumentParser(description="GA4 data for positiveconstraint.com")
    p.add_argument("--json", action="store_true", help="raw JSON output")
    p.add_argument("--raw", action="store_true",
                   help="skip city exclusion filter (include owner traffic)")
    sub = p.add_subparsers(dest="cmd")

    se = sub.add_parser("events", help="idea engagement events")
    se.add_argument("--days", type=int, default=28)
    se.add_argument("--top", type=int, default=100)

    st = sub.add_parser("traffic", help="traffic sources")
    st.add_argument("--days", type=int, default=28)
    st.add_argument("--top", type=int, default=25)

    sp = sub.add_parser("pages", help="top pages by views")
    sp.add_argument("--days", type=int, default=28)
    sp.add_argument("--top", type=int, default=25)

    args = p.parse_args()
    if not args.cmd:
        p.print_help()
        sys.exit(1)

    client = make_client()
    {"events": cmd_events, "traffic": cmd_traffic, "pages": cmd_pages
     }[args.cmd](client, args)


if __name__ == "__main__":
    main()
