#!/usr/bin/env python3
"""
Fetch viewing statistics for www.evanmayo-wilson.org from Cloudflare, for the
private, pinned "Website Viewing Stats" dashboard on claude.ai.

The site is proxied through Cloudflare, so Cloudflare's own request logs
(zone analytics) see every request. Bots are most of them, and many pose as
browsers, so the counts are built to resist that:

  visits      loads of the header photo (images/Square_Headshot*), which a
              browser fetches when it shows the page and HTML-only bots and
              scanners don't. GitHub Pages lets browsers cache it for 10
              minutes, so this is close to "visits" rather than page views.
  CV opens    loads of the CV viewer page (/cv/).
  PDF downloads  requests for /papers/*.pdf. Requests whose user agent names
              a bot or script (BOT_UA) are counted apart; bots posing as
              browsers can't be told apart, so treat these as an upper bound.

No IP address or user agent is stored, only counts. Cloudflare's free plan
keeps per-request detail for about a month and samples it once it is a few
weeks old, so the weekday scheduled task re-fetches the last 8 days each run
and the history lives in .analytics/history.json (gitignored).

Reads one macOS Keychain item (never stored in this public repo):
  cloudflare-analytics-token  - account API token "polished-art-b0b4":
                                Zone Analytics Read and Zone Read on
                                evanmayo-wilson.org (plus Account Analytics Read)

Writes into --out-dir, each {"rows", "meta"}:
  daily.json      per UTC day: visits, CV opens, PDF downloads (people / bots)
  papers.json     per PDF: downloads, last 7 / 28 days / all tracked
  countries.json  last 28 days: visits by country

Usage:
  python3.14 fetch_web_analytics.py --out-dir DIR             # last 8 days
  python3.14 fetch_web_analytics.py --out-dir DIR --days 22   # backfill
Stdlib only.
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from collections import defaultdict
from pathlib import Path

HOST = "www.evanmayo-wilson.org"
ZONE = "evanmayo-wilson.org"
API = "https://api.cloudflare.com/client/v4"
ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / ".analytics" / "history.json"
TOP_N = 20

# A user agent that is empty, bare, a script library or names a crawler.
BOT_UA = re.compile(
    r"bot|crawl|spider|slurp|scrap|fetch|preview|monitor|checker|inspect|scan|"
    r"censys|firstpage|python|curl|wget|httpclient|okhttp|go-http|java/|libwww|"
    r"axios|node-fetch|headless|phantom|lighthouse|semrush|ahrefs|bytespider|"
    r"petalbot|yandex|baidu|facebookexternalhit|perplexity|gptbot|chatgpt|"
    r"claude|anthropic|ccbot|googleother|dataprovider|zgrab|masscan|nmap|"
    r"^mozilla/5\.0$|^mozilla/5\.0 \(compatible\)$", re.I)

_F = 'datetime_geq: $s, datetime_lt: $e, clientRequestHTTPHost: "%s"' % HOST
_D = "count dimensions { path: clientRequestPath ua: userAgent country: clientCountryName }"
GROUPS = f"""
query($z: String!, $s: Time!, $e: Time!) {{ viewer {{ zones(filter: {{zoneTag: $z}}) {{
  photo: httpRequestsAdaptiveGroups(limit: 10000, filter: {{{_F},
      clientRequestPath_like: "/images/Square_Headshot%", edgeResponseStatus_in: [200, 304]}}) {{ {_D} }}
  cv: httpRequestsAdaptiveGroups(limit: 10000, filter: {{{_F},
      clientRequestPath_in: ["/cv/", "/cv/index.html"], edgeResponseStatus_in: [200, 304]}}) {{ {_D} }}
  pdf: httpRequestsAdaptiveGroups(limit: 10000, filter: {{{_F},
      clientRequestPath_like: "/papers/%", edgeResponseStatus: 200}}) {{ {_D} }}
}} }} }}"""


def keychain(service):
    r = subprocess.run(["security", "find-generic-password", "-s", service, "-w"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        sys.exit(f"Keychain item '{service}' not found - see this script's docstring.")
    return r.stdout.strip()


def call(token, url, body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.load(resp)


def gql(token, query, variables):
    data = call(token, API + "/graphql", {"query": query, "variables": variables})
    if data.get("errors"):
        sys.exit("Cloudflare GraphQL error: " + json.dumps(data["errors"])[:800])
    return data["data"]["viewer"]["zones"][0]


def iso(d):
    return dt.datetime.combine(d, dt.time(), dt.timezone.utc).isoformat().replace("+00:00", "Z")


def is_bot(ua):
    ua = (ua or "").strip()
    return not ua or bool(BOT_UA.search(ua))


def fetch_day(token, zone, day):
    z = gql(token, GROUPS, {"z": zone, "s": iso(day), "e": iso(day + dt.timedelta(days=1))})
    out = {"visits": 0, "cv": 0, "pdf": 0, "botPdf": 0,
           "papers": defaultdict(int), "botPapers": defaultdict(int), "countries": defaultdict(int)}
    for kind in ("photo", "cv", "pdf"):
        if len(z[kind]) >= 10000:
            print(f"warning: {day} {kind} hit the 10,000-group limit; counts are incomplete")
        for g in z[kind]:
            n, d = g["count"], g["dimensions"]
            bot = is_bot(d["ua"])
            if kind == "pdf":
                out["botPdf" if bot else "pdf"] += n
                (out["botPapers"] if bot else out["papers"])[d["path"]] += n
            elif not bot:
                out["visits" if kind == "photo" else "cv"] += n
                if kind == "photo":
                    out["countries"][d["country"] or "Unknown"] += n
    return {k: (dict(v) if isinstance(v, defaultdict) else v) for k, v in out.items()}


def paper_titles():
    """PDF path -> 'First author Year. Title' from the site's citation cache."""
    try:
        cache = json.loads((ROOT / "docs" / "csl-cache.json").read_text())
    except (OSError, ValueError):
        return {}
    titles = {}
    for rec in cache.values():
        doi = (rec.get("DOI") or "").lower()
        if not doi:
            continue
        slug = re.sub(r"[^a-z0-9]+", "_", doi).strip("_")
        title = rec.get("title") or ""
        title = title[0] if isinstance(title, list) else title
        au = (rec.get("author") or [{}])[0].get("family", "")
        yr = ((rec.get("issued") or {}).get("date-parts") or [[""]])[0][0]
        titles[f"/papers/{slug}.pdf"] = f"{au} {yr}. {re.sub(r'<[^>]+>', '', title)}".strip(". ")
    return titles


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd, "w") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def summed(days, field):
    tot = defaultdict(int)
    for d in days:
        for k, v in d.get(field, {}).items():
            tot[k] += v
    return tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--days", type=int, default=8, help="complete UTC days to (re)fetch")
    args = ap.parse_args()
    out = Path(args.out_dir)
    token = keychain("cloudflare-analytics-token")
    zones = call(token, f"{API}/zones?name={ZONE}")["result"]
    if not zones:
        sys.exit(f"Token cannot see zone {ZONE} - it needs Zone Read and Zone Analytics Read on it.")
    zone = zones[0]["id"]

    now = dt.datetime.now(dt.timezone.utc)
    today = now.date()
    history = json.loads(HISTORY.read_text()) if HISTORY.exists() else {}
    for k in range(args.days, 0, -1):
        day = today - dt.timedelta(days=k)
        history[day.isoformat()] = fetch_day(token, zone, day)
        write_json(HISTORY, dict(sorted(history.items())))  # per day: a kill costs nothing

    dates = sorted(history)
    last = dt.date.fromisoformat(dates[-1])

    def window(n):
        lo = (last - dt.timedelta(days=n - 1)).isoformat()
        return [history[d] for d in dates if d >= lo]

    meta = [{"label": "Fetched (UTC)", "value": now.isoformat(timespec="seconds")},
            {"label": "Source", "value": f"Cloudflare zone analytics (request logs) for {HOST}"},
            {"label": "Tracked since", "value": dates[0]},
            {"label": "fetch_web_analytics.py", "value": (ROOT / "fetch_web_analytics.py").read_text(),
             "type": "code", "lang": "python"}]

    write_json(out / "daily.json", {"meta": meta, "rows": [
        {"date": d, "visits": h["visits"], "cvOpens": h["cv"], "pdfDownloads": h["pdf"],
         "botPdfDownloads": h["botPdf"]} for d, h in sorted(history.items())]})

    titles = paper_titles()
    all_p, p28, p7 = summed(history.values(), "papers"), summed(window(28), "papers"), summed(window(7), "papers")
    bots_all = summed(history.values(), "botPapers")
    rows = [{"file": f.rsplit("/", 1)[-1], "paper": titles.get(f, f.rsplit("/", 1)[-1]),
             "last7": p7.get(f, 0), "last28": p28.get(f, 0), "allTracked": n,
             "botsAllTracked": bots_all.get(f, 0)} for f, n in all_p.items()]
    rows.sort(key=lambda r: (-r["last28"], -r["allTracked"], r["paper"]))
    write_json(out / "papers.json", {"meta": meta, "rows": rows})

    lo = max((last - dt.timedelta(days=27)).isoformat(), dates[0])
    crow = [{"country": c, "visits": n} for c, n in
            sorted(summed(window(28), "countries").items(), key=lambda kv: -kv[1])[:TOP_N]]
    write_json(out / "countries.json", {"meta": [{"label": "Window (UTC)", "value": f"{lo} to {dates[-1]}"}] + meta,
                                        "rows": crow})

    w7 = window(7)
    print(f"{len(dates)} days tracked ({dates[0]}..{dates[-1]}); last 7 days: "
          f"{sum(d['visits'] for d in w7)} visits, {sum(d['cv'] for d in w7)} CV opens, "
          f"{sum(d['pdf'] for d in w7)} PDF downloads (+{sum(d['botPdf'] for d in w7)} by flagged bots); "
          f"{len(rows)} papers downloaded")


if __name__ == "__main__":
    main()
