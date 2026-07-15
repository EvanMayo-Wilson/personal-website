#!/usr/bin/env python3
"""
Daily (re-runnable) script: for every citable record in content/publications.md,
resolve a real open-access PDF link and a citation count, and bake both into
docs/pub-stats.json.

Two things used to be slow because they ran live in a visitor's browser:

  * The PDF button - resolved via Unpaywall, one fetch per article (plus a
    PMID->DOI translation hop for most records first).
  * "Sort by Citations" - had no numbers to sort by until every Dimensions/
    Altmetric badge on the page had finished loading and rendering, which
    could take several seconds even after force-loading them early.

This script does both lookups once, ahead of time - the same idea as
generate_csl_cache.py for citation-export data - and the page loads the
result as a static file, so both features are instant instead of waiting on
live API calls. Citation counts come from OpenAlex (Dimensions has no free
API), so the sort order may occasionally differ slightly from the number
shown in an individual Dimensions donut - that donut is untouched and still
loads normally; only the *sort* stopped depending on it.

PDF resolution tries, in order:
  1. Unpaywall's url_for_pdf (never url/url_for_landing_page - see the
     client-side fix this replaces for why that used to be wrong).
  2. A same-domain "smart" pattern for platforms Unpaywall's data is often
     incomplete for (medRxiv/bioRxiv's <article>.full.pdf, OSF's
     <guid>/download) - only used if a HEAD request confirms it actually
     serves a PDF, never guessed blindly.
A resolved PDF identical to the article's own title-link URL is dropped
entirely (a "PDF" button that lands exactly where the title already does is
worse than no button).

Re-run this daily (see .github/workflows/pub-stats.yml) or the client-side
live-fetch fallback covers anything not yet baked in.

    python3 generate_pub_stats.py
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

import html as htmllib

import build

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = None

ROOT = Path(__file__).parent
OUT = ROOT / "docs" / "pub-stats.json"

EMAIL = build.CONTACT_EMAIL
UA = f"evanmayo-wilson.org pub-stats builder (mailto:{EMAIL})"
GAP = 150  # ms between sequential per-item lookups (Unpaywall / HEAD checks)

MEDRXIV_RE = re.compile(
    r"^(https?://www\.(?:medrxiv|biorxiv)\.org/content/10\.\d{4,9}/[^/?#]+v\d+)/?$"
)
OSF_RE = re.compile(
    r"^https?://osf\.io/(?:preprints/[a-z0-9]+/)?([a-z0-9]{4,8})/?$", re.I
)


def http(url, method="GET", timeout=20):
    req = urllib.request.Request(
        url, method=method,
        headers={"Accept": "application/json", "User-Agent": UA},
    )
    return urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT)


def http_json(url):
    with http(url) as r:
        return json.loads(r.read().decode("utf-8"))


def chunk(seq, n):
    return [seq[i:i + n] for i in range(0, len(seq), n)]


def looks_like_pdf(headers, url):
    ctype = (headers.get("Content-Type") or "").lower()
    if "pdf" in ctype:
        return True
    cdisp = (headers.get("Content-Disposition") or "").lower()
    if ".pdf" in cdisp:
        return True
    # OSF's file server serves octet-stream but embeds the real filename here.
    meta = headers.get("X-Waterbutler-Metadata")
    if meta:
        try:
            name = json.loads(meta).get("attributes", {}).get("name", "")
            if name.lower().endswith(".pdf"):
                return True
        except (ValueError, AttributeError, TypeError):
            pass
    return False


def verified_pdf(url):
    """HEAD-check that a candidate URL actually serves a PDF, not an HTML page."""
    try:
        with http(url, method="HEAD", timeout=15) as r:
            clen = int(r.headers.get("Content-Length", "0") or 0)
            return clen > 1000 and looks_like_pdf(r.headers, url)
    except (urllib.error.URLError, OSError, ValueError):
        return False


def smart_pdf(candidate_url):
    """A same-domain PDF URL guess for a location Unpaywall gave no url_for_pdf
    for - only medRxiv/bioRxiv and OSF today. Verified before use, never
    returned blind."""
    m = MEDRXIV_RE.match(candidate_url)
    if m:
        pdf = m.group(1) + ".full.pdf"
        if verified_pdf(pdf):
            return pdf
    m = OSF_RE.match(candidate_url)
    if m:
        pdf = f"https://osf.io/{m.group(1)}/download"
        if verified_pdf(pdf):
            return pdf
    return ""


def collect_items():
    """
    Every citable record (top-level + sub-entries) with a real PMID or DOI,
    as {id: {pmid, doi, title_url}}. Records with only a hand-written
    csl-extra entry are skipped - there's no PMID/DOI to look anything up by.
    """
    items = {}

    def title_url_of(entry_html):
        urls = build.CITE_LINK_RE.findall(entry_html)
        return htmllib.unescape(urls[0]) if urls else ""

    def add(pmid, doi, title_url):
        if not (pmid or doi):
            return
        id_ = "pmid:" + pmid if pmid else "doi:" + doi.lower()
        items[id_] = {"pmid": pmid, "doi": doi, "title_url": title_url}

    years = build.parse_publications()
    for _year, entries in years:
        for e in entries:
            primary = re.sub(r"<ul>.*?</ul>", "", e, flags=re.S)
            pmid, doi, _extra, _title = build.entry_meta(primary)
            add(pmid, doi, title_url_of(primary))

            m = re.search(r"<ul>(.*?)</ul>", e, flags=re.S)
            if not m:
                continue
            for li in build.NESTED_LI_RE.finditer(m.group(1)):
                inner = build.title_on_own_line(li.group(2).lstrip())
                pmid, doi, _extra, _title = build.entry_meta(inner)
                add(pmid, doi, title_url_of(inner))

    return items


def pmid_to_doi(pmids):
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


def resolve_pdf(doi, title_url):
    """Best real PDF for this DOI, or "" if none exists / everything found is
    the same page the title already links to."""
    url = "https://api.unpaywall.org/v2/" + urllib.parse.quote(doi, safe="") + \
          "?email=" + urllib.parse.quote(EMAIL)
    try:
        data = http_json(url)
    except (urllib.error.URLError, ValueError):
        data = None

    pdf = ""
    if data:
        locs = [data.get("best_oa_location")] + (data.get("oa_locations") or [])
        locs = [loc for loc in locs if loc]
        for loc in locs:
            if loc.get("url_for_pdf"):
                pdf = loc["url_for_pdf"]
                break
        if not pdf:
            for loc in locs:
                candidate = smart_pdf(loc.get("url") or "")
                if candidate:
                    pdf = candidate
                    break

    if not pdf:
        # Even with no OA record at all, the title link itself might be a
        # medRxiv/bioRxiv/OSF page with a guessable PDF.
        pdf = smart_pdf(title_url)

    if pdf and title_url and pdf.rstrip("/") == title_url.rstrip("/"):
        return ""  # identical to the title link - not worth a button
    return pdf


def citation_counts(items):
    """id -> OpenAlex cited_by_count, batched by DOI/PMID OR-filters."""
    counts = {}

    dois = [(id_, v["doi"]) for id_, v in items.items() if v["doi"]]
    pmids = [(id_, v["pmid"]) for id_, v in items.items() if v["pmid"] and not v["doi"]]

    def run(pairs, field):
        for group in chunk(pairs, 40):
            values = "|".join(urllib.parse.quote(v, safe="") for _id, v in group)
            url = f"https://api.openalex.org/works?filter={field}:{values}&per-page=50&mailto={urllib.parse.quote(EMAIL)}"
            try:
                data = http_json(url)
            except (urllib.error.URLError, ValueError) as e:
                print(f"  OpenAlex {field} batch failed ({e})")
                continue
            by_value = {}
            for r in data.get("results", []):
                if field == "doi" and r.get("doi"):
                    by_value[r["doi"].lower().replace("https://doi.org/", "")] = r["cited_by_count"]
                elif field == "pmid":
                    pmid_url = (r.get("ids") or {}).get("pmid") or ""
                    m = re.search(r"(\d+)$", pmid_url)
                    if m:
                        by_value[m.group(1)] = r["cited_by_count"]
            for id_, v in group:
                key = v.lower() if field == "doi" else v
                if key in by_value:
                    counts[id_] = by_value[key]
            time.sleep(GAP / 1000)

    run(dois, "doi")
    run(pmids, "pmid")
    return counts


def main():
    items = collect_items()
    print(f"{len(items)} citable records with a PMID/DOI")

    pmids_needing_doi = [v["pmid"] for v in items.values() if v["pmid"] and not v["doi"]]
    p2d = pmid_to_doi(pmids_needing_doi) if pmids_needing_doi else {}

    print("Fetching citation counts from OpenAlex...")
    counts = citation_counts(items)
    print(f"  got {len(counts)}/{len(items)} counts")

    print("Resolving PDF links...")
    pdfs = {}
    for i, (id_, v) in enumerate(items.items(), 1):
        doi = v["doi"] or p2d.get(v["pmid"], "")
        if not doi:
            candidate = smart_pdf(v["title_url"])
            if candidate and candidate.rstrip("/") != v["title_url"].rstrip("/"):
                pdfs[id_] = candidate
            continue
        pdf = resolve_pdf(doi, v["title_url"])
        if pdf:
            pdfs[id_] = pdf
        if i % 25 == 0:
            print(f"  {i}/{len(items)}...")
        time.sleep(GAP / 1000)
    print(f"  found {len(pdfs)}/{len(items)} real PDF links")

    # Every item gets a record, even an empty one - the client relies on
    # "this id is present at all" to mean "already checked, don't bother
    # re-resolving live," distinct from an id that's simply missing because
    # it was added since the last run.
    out = {}
    for id_ in items:
        entry = {}
        if id_ in counts:
            entry["citations"] = counts[id_]
        if id_ in pdfs:
            entry["pdf"] = pdfs[id_]
        out[id_] = entry

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=0, sort_keys=True) + "\n",
                   encoding="utf-8")
    print(f"Wrote {len(out)} records to {OUT}")


if __name__ == "__main__":
    sys.exit(main())
