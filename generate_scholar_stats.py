#!/usr/bin/env python3
"""
Refresh docs/scholar-stats.json from Evan's public Google Scholar profile.

Google Scholar has no API, so this reads the "All" column of the profile
page's stats table (Citations / h-index / i10-index) directly - one plain
page fetch, stdlib only. It replaced the `scholarly` package, which broke in
2026-09 (it imports bibtexparser.bibdatabase, removed in bibtexparser 2.x)
and, when Scholar blocked the runner, spent ~15 minutes retrying before
failing anyway.

Scholar sometimes blocks datacenter IPs (GitHub Actions runners) with a
CAPTCHA page. That's detected - the stats table is missing - and the script
exits non-zero without touching the file, so the last good numbers stay up.

The file is only rewritten when a number changes ("updated" = date of the
last change), and the write is atomic (temp file + rename), so a killed run
never leaves a half-written file.

Usage: python3 generate_scholar_stats.py
"""
import datetime
import html
import json
import os
import re
import ssl
import sys
import tempfile
import urllib.request
from pathlib import Path

PROFILE = "https://scholar.google.com/citations?user=gwrtLekAAAAJ&hl=en"
OUT = Path(__file__).resolve().parent / "docs" / "scholar-stats.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

try:  # python.org macOS builds ship without system CA certs
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()


def fetch_stats():
    req = urllib.request.Request(PROFILE, headers={
        "User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=30, context=SSL_CONTEXT) as r:
        page = r.read().decode("utf-8", "replace")
    table = re.search(r'<table id="gsc_rsb_st".*?</table>', page, re.S)
    if not table:
        raise RuntimeError("stats table not found (blocked or CAPTCHA page?)")
    rows = {}
    for row in re.findall(r"<tr>(.*?)</tr>", table.group(0), re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)]
        if len(cells) >= 2:
            rows[cells[0]] = cells[1]          # label -> "All" column
    try:
        stats = {"citations": int(rows["Citations"]),
                 "hindex":    int(rows["h-index"]),
                 "i10index":  int(rows["i10-index"])}
    except (KeyError, ValueError):
        raise RuntimeError(f"unexpected stats table: {rows!r}")
    if stats["citations"] <= 0:
        raise RuntimeError(f"implausible stats: {stats!r}")
    return stats


def main():
    try:
        new = fetch_stats()
    except Exception as e:
        print(f"Google Scholar fetch failed: {e}", file=sys.stderr)
        return 1
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    if all(old.get(k) == v for k, v in new.items()):
        print("unchanged", new)
        return 0
    new["updated"] = datetime.date.today().isoformat()
    fd, tmp = tempfile.mkstemp(dir=OUT.parent, prefix=".scholar-stats.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(json.dumps(new) + "\n")
    os.replace(tmp, OUT)
    print("wrote", new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
