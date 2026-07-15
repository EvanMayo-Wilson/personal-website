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
     <guid>/download).
  3. The publisher's own <meta name="citation_pdf_url"> tag on the article's
     landing page - the same convention Google Scholar uses to find PDFs.
     Many publishers embed this even when Unpaywall's record doesn't have a
     url_for_pdf; several others (Elsevier, Wiley, SAGE, JAMA, BMJ, Cochrane)
     either don't expose it or block a scripted fetch of the landing page
     entirely (403) - those are left without a button rather than guessed at
     or scraped around.
  4. NCBI Bookshelf's own PDF convention (<NBK id>/pdf/Bookshelf_<id>.pdf)
     for PMIDs whose PubMed record is a book (the NICE guideline monographs -
     no DOI, so nothing else here applies).
  5. The entry's own "[Preprint on X](url)" bracket link, if the published
     version has no free copy anywhere - tried the same way as the title URL
     (steps 2-3 above). Several preprint servers host the manuscript as a
     Word doc rather than a PDF, which the verification step correctly
     rejects (a "PDF" button should never hand someone a .docx).
Every candidate from (2)-(5) is only used once its first few bytes are
confirmed to start with the "%PDF-" magic number (see verified_pdf()) -
never guessed blindly from headers or a URL's ".pdf" suffix, since several
hosts that genuinely serve a PDF send no distinguishing Content-Type at all,
while a host blocking a paywalled PDF often serves an HTML page with a
plain 200 rather than an error. A resolved PDF identical to the article's
own title-link URL is dropped entirely (a "PDF" button that lands exactly
where the title already does is worse than no button).

Not attempted: institutional-subscription APIs (Elsevier, Wiley TDM, Scopus,
Springer) some sibling projects on this machine use - those are gated on
Evan's personal/UNC-institutional credentials and IP-based entitlement, which
isn't appropriate to bake into a public site's automated, publicly-run
pipeline. Also not attempted: PMC's official OA Web Service - it only covers
PMC's explicit "OA subset" (a fraction of what's readable on PMC) and returns
a .tar.gz package rather than a PDF URL, which would mean downloading,
extracting, and re-hosting a copy of the paper ourselves rather than linking
to the copy the publisher/repository already hosts - a meaningfully bigger
step this script doesn't take on its own.

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
CITATION_PDF_RE = re.compile(
    r'name=["\']citation_pdf_url["\']\s+content=["\']([^"\']+)["\']', re.I
)

# A browser-style UA for fetching a publisher's human-facing landing page
# (looking for the same <meta citation_pdf_url> tag Google Scholar reads) -
# distinct from UA above, which honestly identifies us to the polite-pool
# APIs (Unpaywall/OpenAlex/NCBI) that expect and want that. This is a single
# plain GET of a public page, not evasion of anything - publishers that block
# it (403) are simply left without a PDF button rather than worked around.
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def http(url, method="GET", timeout=20):
    req = urllib.request.Request(
        url, method=method,
        headers={"Accept": "application/json", "User-Agent": UA},
    )
    return urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT)


def http_html(url, timeout=20):
    req = urllib.request.Request(
        url, headers={"Accept": "text/html", "User-Agent": BROWSER_UA},
    )
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CONTEXT) as r:
        return r.read(300_000).decode("utf-8", errors="ignore")


def http_json(url):
    with http(url) as r:
        return json.loads(r.read().decode("utf-8"))


def chunk(seq, n):
    return [seq[i:i + n] for i in range(0, len(seq), n)]


def verified_pdf(url):
    """
    Ground-truth check that a candidate URL actually serves a PDF: request
    just the first few bytes (Range) and look for the "%PDF-" magic number,
    rather than trusting Content-Type/Content-Disposition - several hosts
    that genuinely serve a PDF (F1000Research, OSF) send generic
    application/octet-stream with no distinguishing header at all, while a
    host blocking access to a paywalled PDF (e.g. non-open-access Springer
    content) often ignores the Range request and serves an HTML page with a
    plain 200, which this catches too (no "%PDF-" at the start either way).
    """
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Range": "bytes=0-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as r:
            return r.read(8).startswith(b"%PDF-")
    except (urllib.error.URLError, OSError):
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


def citation_pdf_url(landing_url):
    """
    The publisher's own <meta name="citation_pdf_url"> tag, if the landing
    page has one and actually serves a PDF there. Many publishers (Springer/
    Nature's article pages, among others) embed a plausible-looking tag whose
    URL then serves an HTML bot-check page instead of the PDF when fetched
    without a browser session - which is exactly why this is verified via
    verified_pdf() like every other candidate, not trusted on sight.
    """
    if not landing_url:
        return ""
    try:
        html_text = http_html(landing_url)
    except (urllib.error.URLError, OSError):
        return ""
    m = CITATION_PDF_RE.search(html_text)
    if not m:
        return ""
    pdf = htmllib.unescape(m.group(1))
    return pdf if verified_pdf(pdf) else ""


def bookshelf_pdf(nbk_id):
    """NCBI Bookshelf's own PDF, for book-type PubMed records (no DOI) - e.g.
    the NICE guideline monographs. Predictable and consistently present for
    every Bookshelf id, but still verified rather than assumed."""
    pdf = f"https://www.ncbi.nlm.nih.gov/books/{nbk_id}/pdf/Bookshelf_{nbk_id}.pdf"
    return pdf if verified_pdf(pdf) else ""


PREPRINT_LINK_RE = re.compile(
    r'<a\b[^>]*href="([^"]+)"[^>]*>[^<]*preprint[^<]*</a>', re.I
)


def collect_items():
    """
    Every citable record (top-level + sub-entries) with a real PMID or DOI,
    as {id: {pmid, doi, title_url, preprint_url}}. Records with only a
    hand-written csl-extra entry are skipped - there's no PMID/DOI to look
    anything up by. preprint_url is the entry's own "[Preprint on X](url)"
    bracket link, if it has one - a fallback PDF source for articles whose
    published version has no OA copy (see resolve_pdf()).
    """
    items = {}

    def title_url_of(entry_html):
        urls = build.CITE_LINK_RE.findall(entry_html)
        return htmllib.unescape(urls[0]) if urls else ""

    def preprint_url_of(entry_html):
        m = PREPRINT_LINK_RE.search(entry_html)
        return htmllib.unescape(m.group(1)) if m else ""

    def add(pmid, doi, title_url, preprint_url):
        if not (pmid or doi):
            return
        id_ = "pmid:" + pmid if pmid else "doi:" + doi.lower()
        items[id_] = {"pmid": pmid, "doi": doi, "title_url": title_url,
                      "preprint_url": preprint_url}

    years = build.parse_publications()
    for _year, entries in years:
        for e in entries:
            primary = re.sub(r"<ul>.*?</ul>", "", e, flags=re.S)
            pmid, doi, _extra, _title = build.entry_meta(primary)
            add(pmid, doi, title_url_of(primary), preprint_url_of(primary))

            m = re.search(r"<ul>(.*?)</ul>", e, flags=re.S)
            if not m:
                continue
            for li in build.NESTED_LI_RE.finditer(m.group(1)):
                inner = build.title_on_own_line(li.group(2).lstrip())
                pmid, doi, _extra, _title = build.entry_meta(inner)
                add(pmid, doi, title_url_of(inner), preprint_url_of(inner))

    return items


def pmid_to_doi(pmids):
    """PMID -> (doi, bookaccession NBK id) - the latter is only ever set for
    PubMed records with no DOI at all (the NICE guideline monographs, catalogued
    as books), so it's the fallback identifier for bookshelf_pdf()."""
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
            doi = next((e["value"] for e in ids if e.get("idtype") == "doi" and e.get("value")), "")
            nbk = next((e["value"] for e in ids if e.get("idtype") == "bookaccession" and e.get("value")), "")
            if doi or nbk:
                out[p] = (doi, nbk)
    return out


def resolve_pdf(doi, title_url, preprint_url=""):
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

    if not pdf:
        # Last resort: the publisher's own landing page (via Unpaywall's DOI
        # redirect, since that's the canonical landing page) might advertise
        # a citation_pdf_url even though Unpaywall's own record has nothing.
        pdf = citation_pdf_url("https://doi.org/" + urllib.parse.quote(doi, safe="/"))

    if not pdf and preprint_url:
        # The published version has no free copy anywhere, but the entry's
        # own "[Preprint on X]" link might. Many preprint servers host the
        # manuscript as a Word doc rather than a PDF, which verified_pdf()
        # correctly rejects (a "PDF" button should not hand someone a .docx).
        pdf = smart_pdf(preprint_url) or citation_pdf_url(preprint_url)

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
        doi_nbk = p2d.get(v["pmid"], ("", ""))
        doi = v["doi"] or doi_nbk[0]
        if not doi:
            candidate = smart_pdf(v["title_url"])
            if not candidate and doi_nbk[1]:
                candidate = bookshelf_pdf(doi_nbk[1])
            if not candidate and v["preprint_url"]:
                candidate = smart_pdf(v["preprint_url"]) or citation_pdf_url(v["preprint_url"])
            if candidate and candidate.rstrip("/") != v["title_url"].rstrip("/"):
                pdfs[id_] = candidate
            continue
        pdf = resolve_pdf(doi, v["title_url"], v["preprint_url"])
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
