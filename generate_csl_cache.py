#!/usr/bin/env python3
"""
One-off (re-runnable) script: fetch CSL-JSON for every citable record in
content/publications.md and bake it into docs/csl-cache.json.

The site's "Cite" buttons build RIS/BibTeX/EndNote/CSL-JSON downloads from
CSL-JSON fetched in the browser (NCBI ctxp, falling back to Crossref). That
live fetch is what was lagging. This script does the same fetch once, ahead
of time, and the page loads the result as a static file - so a cache hit
here means zero network round-trips when a visitor clicks Cite.

Re-run this after adding new papers (or just let the existing client-side
fetch-and-cache-in-localStorage fallback handle new entries until you do -
nothing breaks either way, new entries are just not instant on first click
until this is re-run).

    python3 generate_csl_cache.py
"""

import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import build

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = None

ROOT = Path(__file__).parent
OUT = ROOT / "docs" / "csl-cache.json"

GAP = 600  # ms between sequential Crossref calls (Crossref 429'd a few at 250ms)


def http_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                                "User-Agent": "evanmayo-wilson.org csl cache builder"})
    with urllib.request.urlopen(req, timeout=30, context=SSL_CONTEXT) as r:
        return json.loads(r.read().decode("utf-8"))


def chunk(seq, n):
    return [seq[i:i + n] for i in range(0, len(seq), n)]


def collect_items():
    """Every citable record (top-level + sub-entries), as {pmid, doi, extra}."""
    items = {}  # id -> {pmid, doi, extra}

    def add(pmid, doi, extra):
        if not (pmid or doi or extra):
            return
        if extra:
            return  # covered by content/csl-extra.json already, no fetch needed
        id_ = "pmid:" + pmid if pmid else "doi:" + doi.lower()
        items[id_] = {"pmid": pmid, "doi": doi}

    years = build.parse_publications()
    for _year, entries in years:
        for e in entries:
            primary = re.sub(r"<ul>.*?</ul>", "", e, flags=re.S)
            pmid, doi, extra, _title = build.entry_meta(primary)
            add(pmid, doi, extra)

            m = re.search(r"<ul>(.*?)</ul>", e, flags=re.S)
            if not m:
                continue
            for li in build.NESTED_LI_RE.finditer(m.group(1)):
                inner = build.title_on_own_line(li.group(2).lstrip())
                pmid, doi, extra, _title = build.entry_meta(inner)
                add(pmid, doi, extra)

    return items


def fetch_ctxp(pmids):
    """NCBI's citation exporter, batched. Returns {pmid: cslDict}."""
    got = {}
    for group in chunk(pmids, 50):
        url = ("https://api.ncbi.nlm.nih.gov/lit/ctxp/v1/pubmed/?format=csl&id="
               + ",".join(group))
        try:
            data = http_json(url)
        except (urllib.error.URLError, ValueError) as e:
            print(f"  ctxp batch failed ({e}), will fall back to Crossref for these")
            continue
        if isinstance(data, dict):
            data = [data]
        for d in data or []:
            pm = d.get("PMID") or d.get("pmid")
            if pm and d.get("title"):
                got[str(pm)] = d
    return got


def pmid_to_doi(pmids):
    """NCBI esummary, batched. Returns {pmid: doi}."""
    out = {}
    for group in chunk(pmids, 100):
        url = ("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
               "?db=pubmed&retmode=json&id=" + ",".join(group))
        try:
            data = http_json(url)
        except (urllib.error.URLError, ValueError) as e:
            print(f"  esummary batch failed ({e})")
            continue
        result = (data or {}).get("result", {})
        for p in group:
            ids = (result.get(p) or {}).get("articleids", [])
            for entry in ids:
                if entry.get("idtype") == "doi" and entry.get("value"):
                    out[p] = entry["value"]
                    break
    return out


def fetch_crossref(doi):
    url = ("https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="")
           + "/transform/application/vnd.citationstyles.csl+json")
    return http_json(url)


def main():
    items = collect_items()
    print(f"{len(items)} citable records need CSL (excluding hand-written csl-extra entries)")

    found = {}
    if OUT.exists():
        try:
            found = json.loads(OUT.read_text(encoding="utf-8"))
        except ValueError:
            found = {}
    before = len(found)

    pmids = [v["pmid"] for v in items.values() if v["pmid"]]
    dois_only = {k: v["doi"] for k, v in items.items() if not v["pmid"] and v["doi"]}

    print(f"Fetching {len(pmids)} PMIDs via NCBI ctxp...")
    got = fetch_ctxp(pmids)
    for pm, d in got.items():
        found[f"pmid:{pm}"] = d
    missing_pmids = [p for p in pmids if p not in got]

    doi_targets = dict(dois_only)  # id -> doi, for entries with no PMID at all
    if missing_pmids:
        print(f"{len(missing_pmids)} PMIDs not covered by ctxp; translating to DOI via esummary...")
        p2d = pmid_to_doi(missing_pmids)
        for p, doi in p2d.items():
            doi_targets[f"pmid:{p}"] = doi
        still_missing = [p for p in missing_pmids if p not in p2d]
        if still_missing:
            print(f"  {len(still_missing)} PMIDs have no discoverable DOI and ctxp failed - skipped: {still_missing}")

    doi_targets = {k: v for k, v in doi_targets.items() if k not in found}
    print(f"Fetching {len(doi_targets)} records via Crossref...")
    for i, (id_, doi) in enumerate(doi_targets.items(), 1):
        try:
            found[id_] = fetch_crossref(doi)
            print(f"  [{i}/{len(doi_targets)}] ok: {id_}")
        except (urllib.error.URLError, ValueError) as e:
            print(f"  [{i}/{len(doi_targets)}] FAILED: {id_} ({e})")
        time.sleep(GAP / 1000)

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(found, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"Wrote {len(found)} records ({len(found) - before} new) to {OUT}")


if __name__ == "__main__":
    sys.exit(main())
