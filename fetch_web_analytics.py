#!/usr/bin/env python3
"""
Fetch viewing statistics for www.evanmayo-wilson.org from Cloudflare Web
Analytics (the cookie-free beacon build.py adds to every page) for the
private, pinned "Website Viewing Stats" dashboard on claude.ai.

Reads two macOS Keychain items (never stored in this public repo):
  cloudflare-analytics-token  - API token, Account > Account Analytics > Read
  cloudflare-account-id       - the Cloudflare account ID

Writes two files into --out-dir, each {"rows": [...], "meta": [...]}:
  daily.json      one row per UTC day: date, visits, pageviews. Merged into
                  the history kept at .analytics/daily-history.json
                  (gitignored), because Cloudflare keeps only ~6 months.
  breakdown.json  the last 4 complete Monday-Sunday weeks: top pages,
                  referrers, countries and devices.
A weekly scheduled Claude task uploads both to the dashboard.

Usage:
  python3.14 fetch_web_analytics.py --out-dir DIR             # last 5 weeks
  python3.14 fetch_web_analytics.py --out-dir DIR --days 180  # backfill
Stdlib only.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HOST = "www.evanmayo-wilson.org"
API = "https://api.cloudflare.com/client/v4/graphql"
HISTORY = Path(__file__).resolve().parent / ".analytics" / "daily-history.json"
TOP_N = 15

FILTER = "filter: {datetime_geq: $start, datetime_lt: $end, requestHost: $host}"
DAILY_Q = f"""
query($acct: String!, $start: Time!, $end: Time!, $host: String!) {{
  viewer {{ accounts(filter: {{accountTag: $acct}}) {{
    daily: rumPageloadEventsAdaptiveGroups(limit: 1000, {FILTER}, orderBy: [date_ASC]) {{
      count sum {{ visits }} dimensions {{ date }} }}
  }} }}
}}"""
BREAKDOWN_Q = "query($acct: String!, $start: Time!, $end: Time!, $host: String!, $n: Int!) {\n" \
    "  viewer { accounts(filter: {accountTag: $acct}) {\n" + "".join(
        f"    {alias}: rumPageloadEventsAdaptiveGroups(limit: $n, {FILTER}, "
        f"orderBy: [sum_visits_DESC]) {{ count sum {{ visits }} dimensions {{ key: {field} }} }}\n"
        for alias, field in [("page", "requestPath"), ("referrer", "refererHost"),
                             ("country", "countryName"), ("device", "deviceType")]
    ) + "  } }\n}"


def keychain(service):
    r = subprocess.run(["security", "find-generic-password", "-s", service, "-w"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit(f"Keychain item '{service}' not found - see this script's docstring.")
    return r.stdout.strip()


def iso(d):
    return dt.datetime.combine(d, dt.time(), dt.timezone.utc).isoformat().replace("+00:00", "Z")


def gql(token, query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    if data.get("errors"):
        sys.exit("Cloudflare GraphQL error: " + json.dumps(data["errors"])[:800])
    accts = data["data"]["viewer"]["accounts"]
    if not accts:
        sys.exit("No account returned - check cloudflare-account-id and the token's account scope.")
    return accts[0]


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--days", type=int, default=35, help="days of daily totals to (re)fetch")
    args = ap.parse_args()
    out = Path(args.out_dir)
    token, acct = keychain("cloudflare-analytics-token"), keychain("cloudflare-account-id")
    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()
    stamp = now.isoformat(timespec="seconds")

    # Daily totals, up to yesterday (today is incomplete), in <=30-day chunks.
    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else {}
    start = today - dt.timedelta(days=args.days)
    while start < today:
        end = min(start + dt.timedelta(days=30), today)
        a = gql(token, DAILY_Q, {"acct": acct, "host": HOST, "start": iso(start), "end": iso(end)})
        for g in a["daily"]:
            history[g["dimensions"]["date"]] = {"visits": g["sum"]["visits"], "pageviews": g["count"]}
        start = end
    write_json(HISTORY, dict(sorted(history.items())))
    me = Path(__file__).read_text()
    meta = [{"label": "Fetched (UTC)", "value": stamp},
            {"label": "Source", "value": f"Cloudflare Web Analytics, host {HOST}"},
            {"label": "fetch_web_analytics.py", "value": me, "type": "code", "lang": "python"}]
    write_json(out / "daily.json", {
        "rows": [{"date": d, **v} for d, v in sorted(history.items())], "meta": meta})

    # Breakdown for the last 4 complete Monday-Sunday weeks.
    b_end = today - dt.timedelta(days=today.weekday())
    b_start = b_end - dt.timedelta(weeks=4)
    a = gql(token, BREAKDOWN_Q, {"acct": acct, "host": HOST, "n": TOP_N,
                                 "start": iso(b_start), "end": iso(b_end)})
    rows = []
    for dim in ("page", "referrer", "country", "device"):
        for g in a[dim]:
            rows.append({"dimension": dim, "item": g["dimensions"]["key"] or "(none)",
                         "visits": g["sum"]["visits"], "pageviews": g["count"]})
    write_json(out / "breakdown.json", {"rows": rows, "meta": [
        {"label": "Window (UTC)", "value": f"{b_start} to {b_end - dt.timedelta(days=1)}"}] + meta})

    last = list(history.items())[-7:]
    print(f"{len(history)} days of history; last 7 days: "
          f"{sum(v['visits'] for _, v in last)} visits, {sum(v['pageviews'] for _, v in last)} page views; "
          f"breakdown {b_start}..{b_end - dt.timedelta(days=1)}: {len(rows)} rows")


if __name__ == "__main__":
    main()
