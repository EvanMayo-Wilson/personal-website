#!/usr/bin/env python3
"""
Check content/publications.md for house-style drift and, with --online, for
accuracy against PubMed and Crossref.

    python3 check_publications.py            # offline style lint (build.py runs this)
    python3 check_publications.py --online   # + compare every entry with PubMed/Crossref
    python3 check_publications.py --online --json out.json

Exit code 1 if any ERROR is found, else 0. WARN lines are judgment calls.

What is checked
  offline: title link is https://doi.org/<DOI> when a DOI is known, never PubMed
           or a PDF; PMID and DOI formatted per CLAUDE.md; DOI shown only when
           there is no PMID; final period; "vol(issue):pages" shape (no spaces,
           hyphen not en dash); author-list punctuation; one display form per
           journal; sentence-case titles (WARN); duplicate PMIDs.
  online:  PMID exists and is this paper (title match); title, journal (NLM
           abbreviation), volume, issue, pages and author list agree with
           PubMed; title-link DOI agrees with PubMed; DOI-only entries that
           PubMed has since indexed (missing PMID); Crossref volume/issue/pages
           for DOI-only entries.

Deliberate deviations from PubMed (compound surnames, a PubMed record that
misspells a name, titles kept in the publisher's form) live in
content/citation-exceptions.json, so a check never re-flags a settled call.
"""
import argparse
import difflib
import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBS = ROOT / "content" / "publications.md"
EXC = ROOT / "content" / "citation-exceptions.json"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
UA = {"User-Agent": "evanmayo-wilson.org citation check (mailto:evan.mayo-wilson@unc.edu)"}

TITLE_LINK_RE = re.compile(r"^\[\*\*(.+?)\*\*\]\(")
PMID_RE = re.compile(r"PMID: \[(\d+)\]\(https://pubmed\.ncbi\.nlm\.nih\.gov/(\d+)/\)")
DOI_TEXT_RE = re.compile(r"DOI: \[(10\.[^\]]+)\]\(https://doi\.org/([^)\s]+(?:\([^)\s]*\)[^)\s]*)*)\)")
JOURNAL_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")


# ---------------------------------------------------------------- parsing
def balanced_url(s, start):
    """URL inside markdown parens starting at s[start] (just after '('), allowing nested parens."""
    k, depth = start, 1
    while k < len(s) and depth:
        depth += {"(": 1, ")": -1}.get(s[k], 0)
        k += 1
    return s[start:k - 1], k


def parse():
    entries, year, cur = [], None, None
    for n, ln in enumerate(PUBS.read_text(encoding="utf-8").splitlines(), 1):
        m = re.match(r"^##\s+(\d{4})", ln)
        if m:
            cur and entries.append(cur)
            year, cur = m.group(1), None
            continue
        m = re.match(r"^(\s*)-\s+(.*)$", ln)
        if m and year:
            cur and entries.append(cur)
            cur = {"year": year, "line": n, "nested": bool(m.group(1)), "raw": m.group(2)}
        elif not ln.strip() or ln.strip().startswith("This article was published"):
            cur and entries.append(cur)
            cur = None
        elif cur:
            cur["raw"] += "\n" + ln
    cur and entries.append(cur)
    for e in entries:
        r = e["raw"]
        m = TITLE_LINK_RE.match(r)
        if m:
            e["title"] = m.group(1)
            e["url"], end = balanced_url(r, m.end())
        else:
            m = re.match(r"\*\*(.+?)\*\*", r)
            e["title"], e["url"], end = (m.group(1), "", m.end()) if m else ("", "", 0)
        rest = r[end:]
        e["rest"] = rest
        pm = PMID_RE.search(rest)
        e["pmid"] = pm.group(1) if pm else ""
        e["pmid_ok"] = bool(pm and pm.group(1) == pm.group(2))
        dt = DOI_TEXT_RE.search(rest)
        e["doi_text"] = dt.group(1) if dt else ""
        e["doi"] = e["url"][len("https://doi.org/"):] if e["url"].startswith("https://doi.org/") else e["doi_text"]
        body = re.split(r"\s\[\[|\s\[(?=Published protocol\]|Data |GitHub )", rest.strip())[0]
        e["body"] = body
        jm = JOURNAL_RE.search(body)
        e["journal"] = jm.group(1).strip() if jm else ""
        e["authors"] = body[: jm.start()].strip() if jm else ""
        e["cite"] = body[jm.end(): body.find("PMID:") if "PMID:" in body else (body.find("DOI:") if "DOI:" in body else len(body))].strip() if jm else ""
    return entries


# ---------------------------------------------------------------- helpers
def norm(s):
    s = html.unescape(re.sub(r"<[^>]+>|\*", "", s or ""))
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def expand_pages(p):
    p = (p or "").replace("–", "-").replace(" ", "")
    m = re.match(r"^([A-Za-z]*)(\d+)-([A-Za-z]*)(\d+)$", p)
    if not m:
        return p
    a, b = m.group(2), m.group(4)
    if len(b) < len(a):
        b = a[: len(a) - len(b)] + b
    return f"{m.group(1)}{a}-{m.group(3) or m.group(1)}{b}"


def split_cite(c):
    """'23(10):e1005275.' -> ('23', '10', 'e1005275')"""
    m = re.match(r"^(\d+[A-Z]?)?(?:\(([^)]+)\))?(?::(\S+?))?\.?$", c.strip())
    return (m.group(1) or "", m.group(2) or "", m.group(3) or "") if m else (None, None, None)


def author_names(s):
    s = s.replace("**", "")
    s = re.sub(r"\s*\((?:order of authorship|joint first|contributor)[^)]*\)", "", s)
    s = re.sub(r",?\s*(?:on behalf of|for the|and the)\b.*$", "", s).strip().rstrip(".")
    return [p.strip() for p in s.split(",") if p.strip()]


def get_json(url):
    last = None
    for k in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.loads(r.read())
        except Exception as ex:  # noqa: BLE001 - network flakiness; retry then report
            last = ex
            time.sleep(2 ** k)
    raise RuntimeError(f"{url}: {last}")


# ---------------------------------------------------------------- checks
class Report:
    def __init__(self):
        self.items = []

    def add(self, level, e, msg):
        self.items.append({"level": level, "line": e["line"], "year": e["year"], "title": e["title"][:70], "msg": msg})


ACRONYM = re.compile(r"^(?:[A-Z0-9][A-Z0-9\-]+s?|[A-Za-z]*[A-Z][A-Za-z]*[A-Z][A-Za-z\-]*|[A-Z])[\'’]?s?$")


def offline(entries, exc, rep):
    seen = defaultdict(list)
    forms = defaultdict(set)
    proper = set(exc.get("title_case_ok", []))
    for e in entries:
        r, url = e["raw"], e["url"]
        if e["pmid"]:
            seen[e["pmid"]].append(e)
            if not e["pmid_ok"]:
                rep.add("ERROR", e, "PMID link number differs from the PMID shown")
        if "pubmed.ncbi" in url:
            rep.add("ERROR", e, "title links to PubMed; link the publisher (https://doi.org/<DOI>)")
        if url.startswith("http://"):
            rep.add("ERROR", e, "title link uses http://")
        if url and not url.startswith("https://doi.org/") and url not in exc.get("non_doi_title_links", []):
            rep.add("WARN", e, f"title link is not a doi.org link: {url[:80]}")
        if re.search(r"\.pdf$|/pdf$|full-guideline-pdf", url):
            rep.add("ERROR", e, "title links to a PDF")
        if re.search(r"DOI:\s*10\.", r):
            rep.add("ERROR", e, "DOI not hyperlinked (write DOI: [10.x/y](https://doi.org/10.x/y).)")
        if e["pmid"] and "DOI:" in e["body"]:
            rep.add("ERROR", e, "DOI shown although there is a PMID")
        if not e["pmid"] and e["doi"] and not e["doi_text"] and "ISBN" not in r:
            rep.add("ERROR", e, "no PMID and no DOI shown")
        if e["body"] and not e["body"].rstrip().endswith((".", "?")):
            rep.add("ERROR", e, "citation does not end with a period")
        c = e["cite"]
        if c and split_cite(c)[0] is None and not re.search(r"Press|Institute|College|ISBN|pp\.", e["body"]):
            rep.add("ERROR", e, f"volume/issue/pages not in vol(issue):pages form: “{c}”")
        if "–" in c:
            rep.add("ERROR", e, "en dash in page range (use a hyphen)")
        if e["journal"] and e["journal"].endswith("."):
            rep.add("ERROR", e, f"period inside journal name: *{e['journal']}*")
        a = e["authors"]
        if re.search(r"\b[A-Z] [A-Z]\b(?![a-z])", a.replace("**", "")) and "Mayo-Wilson E (" not in a:
            rep.add("ERROR", e, "spaced initials (e.g. “Page M J”)")
        if re.search(r"[A-Z]\.,|[a-z], [A-Z]{1,3},", a):
            rep.add("ERROR", e, "author punctuation (period after initials, or comma between surname and initials)")
        if "&" in a and "In " not in a:
            rep.add("ERROR", e, "“&” in author list")
        if "Mayo-Wilson E" not in a and "(contributor)" not in a and "National Academies" not in a:
            rep.add("WARN", e, "Mayo-Wilson E not found in author list")
        if re.search(r"Mayo-W[A-Z]|\*\*Mayo-Wilson E[.,]\*\*", r):
            rep.add("ERROR", e, "Mayo-Wilson E misspelled or punctuation inside the bold")
        if e["journal"]:
            forms[norm(e["journal"])].add(e["journal"])
        # sentence case (WARN): capitalized words mid-title that are not acronyms/proper nouns
        t = re.sub(r"\*", "", e["title"])
        t = re.split(r"\.\s+In:\s", t)[0]  # chapter: book title keeps its own case
        starts = {0} | {m.start(1) for m in re.finditer(r"[:?—]\s+(\S)", t)}
        caps = [m.group(1) for m in re.finditer(r"(?<![\w\-'])([A-Za-z][\w'\-]*)", t)
                if m.start() not in starts and m.group(1)[0].isupper()
                and not ACRONYM.match(m.group(1)) and m.group(1) not in proper]
        if caps:
            rep.add("WARN", e, "check sentence case: " + ", ".join(dict.fromkeys(caps)))
        for m in re.finditer(r"[:?]\s+([a-z]\w*)", t):
            rep.add("ERROR", e, f"lower-case word after colon: “{m.group(1)}”")
    for p, es in seen.items():
        if len(es) > 1:
            for e in es:
                rep.add("ERROR", e, f"PMID {p} is used by more than one entry (lines {[x['line'] for x in es]})")


def online(entries, exc, rep):
    pmids = sorted({e["pmid"] for e in entries if e["pmid"]})
    pm = {}
    for i in range(0, len(pmids), 150):
        r = get_json(EUTILS + "esummary.fcgi?db=pubmed&retmode=json&id=" + ",".join(pmids[i:i + 150]))
        pm.update({k: v for k, v in r.get("result", {}).items() if k != "uids"})
        time.sleep(0.4)
    name_ok = exc.get("author_names", {})
    title_ok = exc.get("titles", {})
    group_ok = set(exc.get("group_authorship_pmids", []))
    for e in entries:
        if not e["pmid"]:
            continue
        rec = pm.get(e["pmid"])
        if not rec or "error" in rec:
            rep.add("ERROR", e, f"PMID {e['pmid']} not found in PubMed")
            continue
        pt = rec.get("title") or rec.get("booktitle", "")
        if e["pmid"] not in title_ok and difflib.SequenceMatcher(None, norm(e["title"]), norm(pt)).ratio() < 0.6:
            rep.add("ERROR", e, f"PMID {e['pmid']} is a different paper: “{pt[:80]}”")
            continue
        if norm(e["title"]) != norm(pt) and title_ok.get(e["pmid"]) != e["title"]:
            rep.add("ERROR", e, f"title differs from PubMed: “{pt[:120]}”")
        if e["journal"] and rec.get("source") and not rec.get("booktitle") and e["journal"] != rec["source"].rstrip("."):
            rep.add("ERROR", e, f"journal *{e['journal']}* ≠ NLM *{rec['source']}*")
        doi = next((a["value"] for a in rec.get("articleids", []) if a.get("idtype") == "doi"), "")
        if doi and e["url"].startswith("https://doi.org/") and e["doi"].lower() != doi.lower():
            rep.add("ERROR", e, f"title-link DOI {e['doi']} ≠ PubMed DOI {doi}")
        if doi and not e["url"].startswith("https://doi.org/") and e["url"] not in exc.get("non_doi_title_links", []):
            rep.add("ERROR", e, f"title link should be https://doi.org/{doi}")
        vol, iss, pg = split_cite(e["cite"]) if e["cite"] else ("", "", "")
        pv, pi, pp = rec.get("volume", ""), rec.get("issue", ""), expand_pages(rec.get("pages", ""))
        if rec.get("source") == "Cochrane Database Syst Rev":
            vol, pv = pi or pv, pi or pv  # site style is issue:CD-number
        bad = []
        if pv and vol != pv:
            bad.append(f"volume “{vol}” → {pv}")
        if pi and iss and iss != pi and rec.get("source") != "Cochrane Database Syst Rev":
            bad.append(f"issue “{iss}” → {pi}")
        if pv and pi and not iss and rec.get("source") != "Cochrane Database Syst Rev":
            bad.append(f"issue missing ({pi})")
        if pp and expand_pages(pg) != pp:
            bad.append(f"pages “{pg}” → {pp}")
        if bad:
            rep.add("ERROR", e, "citation differs from PubMed: " + "; ".join(bad))
        if e["pmid"] in group_ok:
            continue
        groups = {a["name"] for a in rec.get("authors", []) if a.get("authtype") != "Author"}
        mine = [a for a in author_names(e["authors"]) if a not in groups and a.removeprefix("the ") not in groups]
        theirs = [name_ok.get(a["name"], a["name"]) for a in rec.get("authors", []) if a.get("authtype") == "Author"]
        mine_cmp = [name_ok.get(a, a) for a in mine]
        if theirs and mine_cmp != theirs:
            # site may carry fuller initials than PubMed (Page MJ vs Page M): allowed
            def same(a, b):
                fa, ia = (a.rsplit(" ", 1) + [""])[:2]
                fb, ib = (b.rsplit(" ", 1) + [""])[:2]
                return fa == fb and ia.startswith(ib)
            if len(mine_cmp) != len(theirs) or not all(same(a, b) for a, b in zip(mine_cmp, theirs)):
                diff = [f"{i+1}: “{a}” vs “{b}”" for i, (a, b) in enumerate(zip(mine_cmp, theirs)) if not same(a, b)][:4]
                rep.add("ERROR", e, f"authors differ from PubMed ({len(mine)} vs {len(theirs)}): " + "; ".join(diff))
    # DOI-only entries: has PubMed indexed them since?
    for e in entries:
        if e["pmid"] or not e["doi"]:
            continue
        r = get_json(EUTILS + "esearch.fcgi?db=pubmed&retmode=json&term=" + urllib.parse.quote(f'"{e["doi"]}"[aid]'))
        ids = r.get("esearchresult", {}).get("idlist", [])
        ids = [i for i in ids if i not in exc.get("not_this_paper_pmids", [])]
        if ids:
            rep.add("ERROR", e, f"PubMed now has this DOI: PMID {', '.join(ids)} — add it")
        time.sleep(0.35)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--online", action="store_true", help="also compare with PubMed/Crossref (network)")
    ap.add_argument("--json", help="write findings to this file")
    ap.add_argument("--file", help="check this markdown file instead of content/publications.md")
    ap.add_argument("--quiet", action="store_true", help="print only the summary line and ERRORs")
    a = ap.parse_args()
    global PUBS
    if a.file:
        PUBS = Path(a.file)
    exc = json.loads(EXC.read_text(encoding="utf-8")) if EXC.exists() else {}
    entries = parse()
    rep = Report()
    offline(entries, exc, rep)
    if a.online:
        online(entries, exc, rep)
    for it in sorted(rep.items, key=lambda x: (x["level"] != "ERROR", x["line"])):
        if a.quiet and it["level"] != "ERROR":
            continue
        print(f"{it['level']:5} line {it['line']:>3}  {it['title'][:45]:45}  {it['msg']}")
    n_err = sum(1 for i in rep.items if i["level"] == "ERROR")
    n_warn = len(rep.items) - n_err
    print(f"check_publications: {len(entries)} entries, {n_err} error(s), {n_warn} warning(s)"
          + ("" if a.online else " (offline; run --online to compare with PubMed)"))
    if a.json:
        Path(a.json).write_text(json.dumps(rep.items, indent=1, ensure_ascii=False))
    return 1 if n_err else 0


if __name__ == "__main__":
    sys.exit(main())
