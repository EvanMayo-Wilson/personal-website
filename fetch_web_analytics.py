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
              Loads from data-centre networks (DATA_CENTRE below: cloud and
              web-hosting companies, which are almost always automated
              browsers) are counted apart as dataCentreVisits, from the days
              that have network detail (2026-11-02 on). Fastly, Cloudflare and
              Akamai are not on the list: their addresses are mostly iCloud
              Private Relay users.
  CV opens    loads of the CV viewer page (/cv/).
  PDF downloads  requests for /papers/*.pdf. Requests whose user agent names
              a bot or script (BOT_UA) are counted apart; bots posing as
              browsers can't be told apart, so treat these as an upper bound.

No IP address or user agent is stored, only counts. Regions, cities and
networks come from looking up each visit's IP address, on this Mac, in DB-IP's
free "Lite" databases (CC BY 4.0, https://db-ip.com; attribution is shown on the
dashboard). The IPs are held in memory for the lookup and never written. The
databases (~93 MB compressed) are downloaded once a month into GEO_CACHE,
outside the repo and outside the backed-up .analytics folder. Cloudflare's free plan
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
  countries.json  last 28 days: visits by country, with drill-down rows
                  under each: level "region" (state/province), "city" (under
                  its region) and "network" (the visitor's network, e.g. a
                  university or an internet provider)

Usage:
  python3.14 fetch_web_analytics.py --out-dir DIR             # last 8 days
  python3.14 fetch_web_analytics.py --out-dir DIR --days 22   # backfill
  python3.14 fetch_web_analytics.py --out-dir DIR --geo-days 31
      # also add regions/cities/networks to older stored days that lack them,
      # leaving those days' other counts alone (Cloudflare keeps ~1 month)
Stdlib only.
"""
import argparse
import csv
import datetime as dt
import gzip
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zlib
from collections import defaultdict
from pathlib import Path

HOST = "www.evanmayo-wilson.org"
ZONE = "evanmayo-wilson.org"
API = "https://api.cloudflare.com/client/v4"
ROOT = Path(__file__).resolve().parent
HISTORY = ROOT / ".analytics" / "history.json"
TOP_N = 20
SUB_N = 10   # regions / cities / networks listed under one parent before "Other"
NO_DETAIL = "No location detail"   # visits whose request detail Cloudflare had already dropped
GEO_CACHE = Path.home() / "Library" / "Caches" / "evanmayo-wilson-analytics"
GEO_URL = "https://download.db-ip.com/free/dbip-{kind}-lite-{month}.csv.gz"

# Networks (DB-IP organisation names) that are data centres, not people: cloud and
# web hosts. Anchored whole-name matches, so "Google Fiber Inc." (a home ISP) is
# not caught by "Google LLC". Fastly, Cloudflare and Akamai Technologies are
# deliberately absent (iCloud Private Relay egress). To add a network, add a
# pattern here and run with --regeo-days 31 to redo the stored days.
DATA_CENTRE = re.compile(
    r"^(Amazon\.com, Inc\.|Amazon Technologies Inc\.|Amazon Data Services.*|Google LLC|"
    r"Microsoft Corporation|Oracle Corporation|DigitalOcean.*|Linode.*|Akamai Connected Cloud.*|"
    r"The Constant Company, LLC|Choopa.*|Vultr.*|OVH.*|Hetzner Online GmbH|Contabo.*|Leaseweb.*|"
    r"Datacamp Limited|M247.*|EGIHosting|CustodianDC.*|HostRoyale.*|firstcolo GmbH|Timeweb.*|"
    r"Alibaba.*|Tencent.*|Zenlayer.*|Packet Host.*|Equinix.*|"
    r".*\b(IDC|hosting|datacenter|data center|cloud)\b.*)$", re.I)


def is_data_centre(net):
    return bool(DATA_CENTRE.match(net or ""))

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
_DP = _D[:-2] + " ip: clientIP }"   # photo loads only: the IP is looked up, never stored
GROUPS = f"""
query($z: String!, $s: Time!, $e: Time!) {{ viewer {{ zones(filter: {{zoneTag: $z}}) {{
  photo: httpRequestsAdaptiveGroups(limit: 10000, filter: {{{_F},
      clientRequestPath_like: "/images/Square_Headshot%", edgeResponseStatus_in: [200, 304]}}) {{ {_DP} }}
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
    """One UTC day's counts, plus "_ips" {(country, ip): visits} for the geo
    lookup, which add_geo() turns into counts and removes before anything is saved."""
    z = gql(token, GROUPS, {"z": zone, "s": iso(day), "e": iso(day + dt.timedelta(days=1))})
    out = {"visits": 0, "cv": 0, "pdf": 0, "botPdf": 0,
           "papers": defaultdict(int), "botPapers": defaultdict(int), "countries": defaultdict(int),
           "_ips": defaultdict(int)}
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
                    out["_ips"][(d["country"] or "Unknown", d["ip"])] += n
    return {k: (dict(v) if isinstance(v, defaultdict) else v) for k, v in out.items()}


def ip_key(ip):
    """(4 or 6, integer) for an IP address string, or None."""
    try:
        if ":" in ip:
            return 6, int.from_bytes(socket.inet_pton(socket.AF_INET6, ip), "big")
        return 4, int.from_bytes(socket.inet_pton(socket.AF_INET, ip), "big")
    except (OSError, TypeError):
        return None


def geo_db(kind):
    """Path of this month's DB-IP Lite file ('city' or 'asn'), downloading it if
    not cached; falls back to last month's early in a month. Older copies are
    deleted once a newer one is in place."""
    GEO_CACHE.mkdir(parents=True, exist_ok=True)
    first = dt.date.today().replace(day=1)
    for month in (first, (first - dt.timedelta(days=1)).replace(day=1)):
        path = GEO_CACHE / f"dbip-{kind}-lite-{month:%Y-%m}.csv.gz"
        if not path.exists():
            req = urllib.request.Request(GEO_URL.format(kind=kind, month=f"{month:%Y-%m}"),
                                         headers={"User-Agent": "website-stats/1.0"})
            tmp = GEO_CACHE / f".partial-{kind}-{os.getpid()}"
            try:
                with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as f:
                    want = int(resp.headers.get("Content-Length") or 0)
                    while chunk := resp.read(1 << 20):
                        f.write(chunk)
                if want and tmp.stat().st_size != want:
                    raise OSError(f"DB-IP {kind} download cut short ({tmp.stat().st_size} of {want} bytes)")
                with gzip.open(tmp, "rb") as g:   # whole file must decompress before it is cached
                    while g.read(1 << 22):
                        pass
                os.replace(tmp, path)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue   # this month's file isn't published yet
                raise
            finally:
                tmp.unlink(missing_ok=True)
        for old in [*GEO_CACHE.glob(f"dbip-{kind}-lite-*.csv.gz"), *GEO_CACHE.glob(".partial-*")]:
            if old != path and (old.name.startswith("dbip") or old.stat().st_mtime < dt.datetime.now().timestamp() - 86400):
                old.unlink(missing_ok=True)
        return path
    raise OSError(f"no DB-IP {kind} file for this month or last")


def lookup(path, ips):
    """{ip: csv row} for each IP, by one streaming pass over a DB-IP Lite file
    (rows sorted by range start, IPv4 then IPv6, ranges contiguous)."""
    targets = {4: [], 6: []}
    for ip in ips:
        k = ip_key(ip)
        if k:
            targets[k[0]].append((k[1], ip))
    for t in targets.values():
        t.sort()
    found, idx, prev = {}, {4: 0, 6: 0}, {4: None, 6: None}

    def settle(v, upto):
        t, i, row = targets[v], idx[v], prev[v]
        while i < len(t) and (upto is None or t[i][0] < upto):
            if row is not None and t[i][0] <= ip_key(row[1])[1]:
                found[t[i][1]] = row
            i += 1
        idx[v] = i

    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        for row in csv.reader(f):
            k = ip_key(row[0]) if row else None
            if not k:
                continue
            v, start = k
            settle(v, start)
            prev[v] = row
            if all(idx[x] >= len(targets[x]) for x in (4, 6)):
                break
    for v in (4, 6):
        settle(v, None)
    return found


def add_geo(days):
    """Turn each fetched day's "_ips" into "places" {country: {region: {city: n}}}
    and "networks" {country: {network: n}}, then drop the IPs. Cloudflare's
    country stays the top level; a region/city is used only where DB-IP agrees
    on the country. Returns False (days keep no geo detail) if the lookup fails."""
    ips = {ip for d in days for (_, ip) in d.get("_ips", {})}
    try:
        city = lookup(geo_db("city"), ips) if ips else {}
        asn = lookup(geo_db("asn"), ips) if ips else {}
        ok = True
    except (OSError, EOFError, zlib.error, urllib.error.URLError, ValueError, csv.Error) as e:
        print(f"note: region/city/network lookup skipped ({type(e).__name__}: {e})")
        for bad in GEO_CACHE.glob("dbip-*-lite-*.csv.gz"):   # a corrupt cached file would fail all month
            bad.unlink(missing_ok=True)
        ok = False
    for d in days:
        pairs = d.pop("_ips", {})
        if not ok:
            continue
        places, nets = {}, {}
        for (country, ip), n in pairs.items():
            c = city.get(ip)   # ip_start, ip_end, continent, country, stateprov, city, lat, lon
            a = asn.get(ip)    # ip_start, ip_end, asn, organisation
            net = (a[3] or f"AS{a[2]}") if a else "Unknown network"
            nets.setdefault(country, {})[net] = nets.get(country, {}).get(net, 0) + n
            if is_data_centre(net):
                continue   # not a visitor: kept in networks only, left out of places
            region, town = (c[4] or "Unknown", c[5] or "Unknown") if c and c[3] == country else ("Unknown", "Unknown")
            r = places.setdefault(country, {}).setdefault(region, {})
            r[town] = r.get(town, 0) + n
        d["places"], d["networks"] = places, nets
    return ok


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


def dc_by_country(d):
    """{country: data-centre visits} for a day, from its stored networks."""
    return {c: n for c, nn in d.get("networks", {}).items()
            if (n := sum(v for k, v in nn.items() if is_data_centre(k)))}


def people(d):
    """The day's visits less data-centre visits (days without network detail: all)."""
    return d["visits"] - sum(dc_by_country(d).values())


def summed(days, field):
    tot = defaultdict(int)
    for d in days:
        for k, v in d.get(field, {}).items():
            tot[k] += v
    return tot


def row(key, level, visits, country, region="", city="", network=""):
    """One countries.json row: a country, or a region, city or network under it.
    `key` is unique per row; the page nests rows by country and region."""
    return {"key": key, "level": level, "country": country, "region": region, "city": city,
            "network": network, "visits": visits}


def top_and_other(items, n, other_label, size=lambda v: v):
    """The first n (name, value) pairs, then the rest folded into one
    (other_label, total) pair."""
    items = list(items)
    rest = sum(size(v) for _, v in items[n:])
    return items[:n] + ([(other_label, rest)] if rest else [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--days", type=int, default=8, help="complete UTC days to (re)fetch")
    ap.add_argument("--geo-days", type=int, default=0,
                    help="also add regions/cities/networks to stored days this far back that "
                         "lack them, changing nothing else on those days")
    ap.add_argument("--regeo-days", type=int, default=0,
                    help="redo regions/cities/networks of stored days this far back (after "
                         "DATA_CENTRE changes); a day is replaced only if the re-fetch "
                         "reproduces its stored country counts exactly")
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
    fresh = {}
    for k in range(args.days, 0, -1):
        day = today - dt.timedelta(days=k)
        fresh[day.isoformat()] = fetch_day(token, zone, day)
    if add_geo(fresh.values()):
        history.update(fresh)
    else:   # keep the geo detail already stored for these days
        for day, d in fresh.items():
            history[day] = {**{k: v for k, v in history.get(day, {}).items()
                               if k in ("places", "networks")}, **d}
    write_json(HISTORY, dict(sorted(history.items())))
    for k in range(args.geo_days, args.days, -1):   # per day: a kill costs nothing
        day = (today - dt.timedelta(days=k)).isoformat()
        if day in history and "places" not in history[day]:
            d = fetch_day(token, zone, dt.date.fromisoformat(day))
            # Cloudflare samples, then drops, older days' detail: keep it only if the
            # re-fetch reproduces the stored country counts exactly.
            if add_geo([d]) and d["visits"] and d["countries"] == history[day].get("countries"):
                history[day]["places"], history[day]["networks"] = d["places"], d["networks"]
                write_json(HISTORY, dict(sorted(history.items())))

    for k in range(args.regeo_days, 0, -1):
        day = (today - dt.timedelta(days=k)).isoformat()
        if day in history and "places" in history[day]:
            d = fetch_day(token, zone, dt.date.fromisoformat(day))
            if add_geo([d]) and d["visits"] and d["countries"] == history[day].get("countries"):
                history[day]["places"], history[day]["networks"] = d["places"], d["networks"]
                write_json(HISTORY, dict(sorted(history.items())))
            else:
                print(f"note: {day} not redone (Cloudflare detail changed or lookup failed)")

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
        {"date": d, "visits": people(h), "dataCentreVisits": h["visits"] - people(h), "cvOpens": h["cv"], "pdfDownloads": h["pdf"],
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
    w28 = window(28)
    nets, places = defaultdict(lambda: defaultdict(int)), defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for d in w28:
        for c, nn in d.get("networks", {}).items():
            for name, n in nn.items():
                if not is_data_centre(name):
                    nets[c][name] += n
        for c, regs in d.get("places", {}).items():
            for reg, cities in regs.items():
                for town, n in cities.items():
                    places[c][reg][town] += n
    crow = []
    cnt, dcc = summed(w28, "countries"), summed([{"x": dc_by_country(d)} for d in w28], "x")
    for c, n in sorted(((c, v - dcc.get(c, 0)) for c, v in cnt.items()), key=lambda kv: -kv[1])[:TOP_N]:
        if n <= 0:
            continue
        crow.append(row(c, "country", n, c))
        regs = sorted(places[c].items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))
        for reg, towns in top_and_other(regs, SUB_N, "Other regions", lambda v: sum(v.values())):
            if isinstance(towns, int):
                crow.append(row(f"{c}|r|{reg}", "region", towns, c, region=reg))
                continue
            crow.append(row(f"{c}|r|{reg}", "region", sum(towns.values()), c, region=reg))
            for town, m in top_and_other(sorted(towns.items(), key=lambda kv: (-kv[1], kv[0])), SUB_N, "Other cities"):
                crow.append(row(f"{c}|r|{reg}|c|{town}", "city", m, c, region=reg, city=town))
        gap = n - sum(sum(t.values()) for t in places[c].values())
        if gap > 0:   # visits on days whose detail was gone before it was collected
            crow.append(row(f"{c}|r|{NO_DETAIL}", "region", gap, c, region=NO_DETAIL))
        for name, m in top_and_other(sorted(nets[c].items(), key=lambda kv: (-kv[1], kv[0])), SUB_N, "Other networks"):
            crow.append(row(f"{c}|n|{name}", "network", m, c, network=name))
        gap = n - sum(nets[c].values())
        if gap > 0:
            crow.append(row(f"{c}|n|{NO_DETAIL}", "network", gap, c, network=NO_DETAIL))
    located = sum(n for d in w28 for regs in d.get("places", {}).values()
                  for reg, t in regs.items() if reg != "Unknown" for n in t.values())
    first_geo = min((day for day in dates if history[day].get("places")), default="")
    write_json(out / "countries.json", {"meta": [
        {"label": "Window (UTC)", "value": f"{lo} to {dates[-1]}"},
        {"label": "Visits with region, city and network detail", "value": f"{located} of {sum(people(d) for d in w28)}"},
        {"label": "Data-centre visits left out (28 days)", "value": str(sum(dcc.values()))},
        {"label": "Detail since (UTC)", "value": first_geo},
        {"label": "IP geolocation", "value": "IP Geolocation by DB-IP (https://db-ip.com), Lite edition, CC BY 4.0"},
    ] + meta, "rows": crow})

    w7 = window(7)
    print(f"{len(dates)} days tracked ({dates[0]}..{dates[-1]}); last 7 days: "
          f"{sum(people(d) for d in w7)} visits (+{sum(d['visits'] - people(d) for d in w7)} from data centres, not counted), {sum(d['cv'] for d in w7)} CV opens, "
          f"{sum(d['pdf'] for d in w7)} PDF downloads (+{sum(d['botPdf'] for d in w7)} by flagged bots); "
          f"{len(rows)} papers downloaded")


if __name__ == "__main__":
    main()
