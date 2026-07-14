#!/usr/bin/env python3
"""
Build evanmayo-wilson.org from the markdown files in content/.

    pip3 install markdown
    python3 build.py

Output: docs/index.html  (+ CNAME, .nojekyll, images/)

To update the site, edit the files in content/ and re-run this script.
"""

import datetime
import json
import html
import os
import re
import shutil
import urllib.parse
from pathlib import Path

try:
    import markdown
except ImportError:
    raise SystemExit("Missing dependency. Run:  pip3 install markdown")

ROOT = Path(__file__).parent
CONTENT = ROOT / "content"
OUT = ROOT / "docs"   # GitHub Pages branch-deploys only allow / or /docs

DOMAIN = "www.evanmayo-wilson.org"
CONTACT_EMAIL = "evan.mayo-wilson@unc.edu"   # sent to OpenAlex "polite pool"
SCHOLAR_PROFILE = "https://scholar.google.com/citations?user=gwrtLekAAAAJ&hl=en"
ORCID = "0000-0001-6126-2459"
OPENALEX_AUTHOR = "orcid:" + ORCID          # OpenAlex resolves ORCIDs directly

# Set to your Cloudflare Web Analytics token to enable analytics; "" disables it.
CLOUDFLARE_ANALYTICS_TOKEN = "bbbbe37fa9a84afa972a08c98b1d942c"

MD = markdown.Markdown(extensions=["extra", "sane_lists"])


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def render(name: str) -> str:
    MD.reset()
    return MD.convert((CONTENT / f"{name}.md").read_text(encoding="utf-8"))


def demote(html_str: str, by: int = 1) -> str:
    """h2 -> h3 etc, so section <h2> stays the top of each section's outline."""
    def sub(m):
        lvl = min(6, int(m.group(2)) + by)
        return f"<{m.group(1)}h{lvl}>"
    return re.sub(r"<(/?)h([1-6])>", sub, html_str)


def strip_h1(html_str: str) -> str:
    return re.sub(r"^\s*<h1>.*?</h1>", "", html_str, count=1, flags=re.S).strip()


def section(name: str) -> str:
    return demote(strip_h1(render(name)))


def parse_profile():
    raw = (CONTENT / "profile.md").read_text(encoding="utf-8")
    name = re.search(r"^#\s+(.*)", raw, re.M).group(1).strip()

    photo_m = re.search(r"!\[([^\]]*)\]\(([^)]+)\)", raw)
    photo, photo_alt = (photo_m.group(2), photo_m.group(1)) if photo_m else ("", "")

    # remove image syntax before harvesting links, or the alt text becomes a link
    body = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", raw)

    email_m = re.search(r"\(mailto:([^)?]+)", body)
    email = email_m.group(1) if email_m else CONTACT_EMAIL

    links = [
        (t, html.escape(u, quote=True))          # escape & in query strings
        for t, u in re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", body)
    ]
    return {
        "name": name,
        "photo": photo,
        "photo_alt": photo_alt or name,
        "email": email,
        "links": links,
    }


def parse_publications():
    """-> [(year, [entry_html, ...]), ...], newest first."""
    raw = (CONTENT / "publications.md").read_text(encoding="utf-8")
    body = re.sub(r"^#\s+Publications\s*$", "", raw, count=1, flags=re.M)
    chunks = re.split(r"^##\s+(\d{4})\s*$", body, flags=re.M)[1:]

    years = []
    for year, block in zip(chunks[0::2], chunks[1::2]):
        entries = []
        for item in re.split(r"^-\s+", block.strip(), flags=re.M):
            item = item.strip()
            if not item:
                continue
            MD.reset()
            # Keep the markdown output intact (some entries carry a nested
            # "also published in:" list). Unwrapping the <p> broke those, so we
            # leave the block structure alone and handle spacing in CSS.
            entries.append(MD.convert(item).strip())
        years.append((year, entries))
    return years


PMID_RE = re.compile(r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)")
TITLE_RE = re.compile(r"<strong>(.*?)</strong>", re.S)
HREF_RE = re.compile(r'href="([^"]+)"')
# A DOI sitting inside an article URL, e.g. .../doi/10.1177/1049731513512374
DOI_IN_URL_RE = re.compile(r"(10\.\d{4,9}/[^\s\"'<>)&#]+)")


def load_doi_overrides():
    """content/dois.tsv: URL <TAB> DOI, for articles whose URL hides the DOI."""
    path = CONTENT / "dois.tsv"
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "\t" not in line:
            continue
        url, doi = line.split("\t", 1)
        out[html.unescape(url.strip())] = doi.strip()
    return out


DOI_OVERRIDES = load_doi_overrides()

# A DOI written out in the prose, e.g. "DOI: 10.1093/bjsw/bct129"
DOI_IN_TEXT_RE = re.compile(r"\b(?:doi:?\s*)(10\.\d{4,9}/[^\s<,;)\"']+)", re.I)


def load_csl_extra():
    """
    content/csl-extra.json - hand-written CSL for items with no PMID and no DOI
    (NICE monographs, book chapters, the PCORI report). Without these there is
    nothing for PubMed or Crossref to look up, so no download button.
    """
    path = CONTENT / "csl-extra.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


CSL_EXTRA = load_csl_extra()


def entry_meta(entry_html: str):
    """
    Return (pmid, doi, extra_key, title).

    Identifier precedence:
      1. PMID          - PubMed-indexed articles (badges + NCBI citation export)
      2. DOI           - from content/dois.tsv, from the article URL, or written
                         out in the prose ("DOI: 10.1093/...")
      3. extra_key     - a hand-written CSL record in content/csl-extra.json,
                         keyed by URL or by exact title. No badges (there is
                         nothing to look up), but citation download still works.
    """
    pmid_m = PMID_RE.search(entry_html)
    pmid = pmid_m.group(1) if pmid_m else ""

    urls = [html.unescape(u) for u in HREF_RE.findall(entry_html)]
    text = html.unescape(re.sub(r"<[^>]+>", " ", entry_html))

    doi = ""
    if not pmid:
        for u in urls:
            if u in DOI_OVERRIDES:
                doi = DOI_OVERRIDES[u]
                break
        if not doi:
            for u in urls:
                m = DOI_IN_URL_RE.search(u)
                if m:
                    doi = m.group(1).rstrip(".,;/")
                    break
        if not doi:
            m = DOI_IN_TEXT_RE.search(text)
            if m:
                doi = m.group(1).rstrip(".,;/")

    title_m = TITLE_RE.search(entry_html)
    title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""

    extra = ""
    if not pmid and not doi:
        for u in urls:
            if u in CSL_EXTRA:
                extra = u
                break
        if not extra and title in CSL_EXTRA:
            extra = title

    return pmid, doi, extra, title


ICON_DOWNLOAD = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
    '<path d="M12 3v11"/><path d="m7.5 10 4.5 4.5 4.5-4.5"/><path d="M4.5 20h15"/>'
    "</svg>"
)


CITE_FORMATS = [
    ("ris", "RIS"),          # Zotero, Mendeley, EndNote, Papers - the safe default
    ("bib", "BibTeX"),       # LaTeX, Zotero, JabRef
    ("enw", "EndNote"),      # EndNote's own tagged format
    ("csl", "CSL-JSON"),     # Zotero's native format; also pandoc
]


def cite_menu(bulk: bool = False) -> str:
    label = "Download all citations" if bulk else "Download citation"
    visible = "Download citations" if bulk else "Cite"
    return (
        '<summary title="{0}" aria-label="{0}">{1}'
        '<span class="btn-label">{3}</span></summary>'
        '<div class="cite-menu" role="group" aria-label="Citation format">'
        "{2}</div>"
    ).format(
        label,
        ICON_DOWNLOAD,
        "".join(
            f'<button type="button" data-fmt="{f}">{t}</button>'
            for f, t in CITE_FORMATS
        ),
        visible,
    )


def ident_attr(pmid: str, doi: str, extra: str = "") -> str:
    """The data-* attribute the front-end uses to identify a record."""
    if pmid:
        return f'data-pmid="{pmid}"'
    if doi:
        return f'data-doi="{html.escape(doi, quote=True)}"'
    if extra:
        return f'data-csl="{html.escape(extra, quote=True)}"'
    return ""


def cite_button(key: str) -> str:
    """
    Download-citation control. A native <details> disclosure, so it opens with
    the keyboard and needs no JavaScript to work as a menu. If the article has
    no identifier at all we still emit an empty cell, to keep the column aligned.
    """
    if not key:
        return '<span class="cite-dl-empty"></span>'
    return f'<details class="cite-dl" {key}>{cite_menu()}</details>'


ICON_PDF = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" '
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">'
    '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
    '<path d="M14 3v5h5"/><path d="M9 13h6"/><path d="M9 17h4"/>'
    "</svg>"
)


def oa_button(key: str) -> str:
    """
    Open-access full text. Resolved on demand via Unpaywall, which indexes only
    legally free copies (publisher OA, PMC, institutional repositories). Starts
    hidden and stays hidden if no free copy exists - so the icon appearing is
    itself the signal that there is something to read.
    """
    if not key or "data-csl" in key:
        return '<span class="oa-empty"></span>'
    return (
        f'<a class="oa-pdf" {key} href="#" '
        f'title="Download free full text" aria-label="Download free full text (open access)" '
        f'hidden>{ICON_PDF}<span class="btn-label">PDF</span></a>'
    )


NESTED_LI_RE = re.compile(r"(<li>)(.*?)(</li>)", re.S)


def nested_badges(frag: str) -> str:
    """
    Some entries carry a sub-list: "This article was published simultaneously
    in: <journal A>, <journal B>". Each of those is a separate indexed article
    with its own PMID/DOI, so each gets its own pair of badges - rendered as
    compact rectangles rather than donuts so they sit inline in a list item.
    """
    if "<ul>" not in frag:
        return frag

    def one(m):
        open_tag, inner, close_tag = m.groups()
        pmid, doi, extra, _t = entry_meta(inner)
        if not (pmid or doi or extra):
            return m.group(0)

        key = ident_attr(pmid, doi, extra)
        badge_key = ident_attr(pmid, doi, "")   # badges need a real identifier

        badges = ['<span class="metrics">']
        for kind in ("dim", "alt"):
            badges.append('<span class="slot">')
            if badge_key and kind == "dim":
                badges.append(
                    f'<span class="__dimensions_badge_embed__ dim-lazy" {badge_key} '
                    'data-style="small_circle" data-legend="hover" '
                    'data-hide-zero-citations="true"></span>'
                )
            elif badge_key:
                badges.append(
                    f'<span class="altmetric-lazy" data-badge-type="donut" '
                    'data-badge-popover="right" data-hide-no-mentions="true" '
                    f'data-link-target="_blank" {badge_key}></span>'
                )
            badges.append("</span>")
        badges.append("</span>")

        return (
            '<li class="subpub">'
            + '<span class="cite-col">' + cite_button(key) + oa_button(key) + "</span>"
            + '<div class="pub-text">' + inner.rstrip() + "</div>"
            + "".join(badges)
            + close_tag
        )

    return NESTED_LI_RE.sub(one, frag)


def title_on_own_line(frag: str) -> str:
    """
    The scraped markdown put a hard line break after the title inconsistently.
    Drop any <br> that immediately follows the title link; CSS then renders the
    title as a block, so the author list always starts on the next line.
    """
    return re.sub(
        r"(^<p>\s*(?:<strong>)?<a\b[^>]*>.*?</a>(?:</strong>)?)\s*<br\s*/?>\s*",
        r"\1",
        frag,
        count=1,
        flags=re.S,
    )


def publications_html(years):
    out = []
    for year, entries in years:
        out.append(f'<section class="year-block" data-year="{year}" '
                   f'aria-labelledby="y{year}">')
        out.append(f'<h3 class="year" id="y{year}">{year}</h3>')
        out.append('<ul class="pubs">')
        for e in entries:
            # Identify the parent article from its own paragraph only - the
            # "also published in" sub-list has its own PMIDs and must not be
            # mistaken for the parent's.
            primary = re.sub(r"<ul>.*?</ul>", "", e, flags=re.S)
            pmid, doi, extra, _title = entry_meta(primary)

            e = title_on_own_line(e)
            e = nested_badges(e)

            # Two fixed slots, so the donuts line up down the page whether or
            # not either badge has anything to show.
            key = ident_attr(pmid, doi, extra)
            badge_key = ident_attr(pmid, doi, "")

            metrics = ['<div class="metrics">']

            # Slot 1 - Dimensions citation donut. Hides itself at zero.
            metrics.append('<span class="slot">')
            if badge_key:
                metrics.append(
                    f'<span class="__dimensions_badge_embed__ dim-lazy" {badge_key} '
                    f'data-style="small_circle" data-legend="hover" '
                    f'data-hide-zero-citations="true"></span>'
                )
            metrics.append("</span>")

            # Slot 2 - Altmetric attention donut. Hides itself at zero.
            metrics.append('<span class="slot">')
            if badge_key:
                metrics.append(
                    f'<span class="altmetric-lazy" data-badge-type="donut" '
                    f'data-badge-popover="right" data-hide-no-mentions="true" '
                    f'data-link-target="_blank" {badge_key}></span>'
                )
            metrics.append("</span>")
            metrics.append("</div>")

            out.append(
                '<li class="pub">'
                + '<span class="cite-col">' + cite_button(key) + oa_button(key) + "</span>"
                + f'<div class="pub-text">{e}</div>'
                + "".join(metrics)
                + "</li>"
            )
        out.append("</ul></section>")
    return "\n".join(out)


EXT_LINK_RE = re.compile(r'<a\s+(?![^>]*\btarget=)([^>]*href="https?://[^"]*"[^>]*)>')


def open_links_in_new_tab(page: str) -> str:
    """Every outbound link opens in a new tab; in-page anchors and mailto don't."""
    return EXT_LINK_RE.sub(
        lambda m: f'<a target="_blank" rel="noopener noreferrer" {m.group(1)}>',
        page,
    )


def profile_links_html(p):
    """UNC on its own line; PubMed | ORCID | Scholar on the next; email last."""
    if not p["links"]:
        return ""
    first = p["links"][0]
    rest = p["links"][1:]
    lines = [f'<a href="{first[1]}">{first[0]}</a>']
    if rest:
        lines.append(
            '<span class="sep-list">'
            + '<span class="sep" aria-hidden="true">|</span>'.join(
                f'<a href="{u}">{t}</a>' for t, u in rest
            )
            + "</span>"
        )
    lines.append(f'<a href="mailto:{p["email"]}">{p["email"]}</a>')
    return "".join(f'<p class="plink">{l}</p>' for l in lines)


# --------------------------------------------------------------------------
# template
# --------------------------------------------------------------------------

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{name}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="https://{domain}/">
<meta name="theme-color" content="#ffffff" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0d1521" media="(prefers-color-scheme: dark)">
<meta property="og:title" content="{name}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="profile">
<meta property="og:url" content="https://{domain}/">
<meta property="og:image" content="https://{domain}/{photo}">
<meta name="twitter:card" content="summary">

<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Person",
  "name": "Evan Mayo-Wilson",
  "url": "https://{domain}/",
  "email": "mailto:{email}",
  "jobTitle": "Associate Professor of Epidemiology",
  "affiliation": {{
    "@type": "Organization",
    "name": "UNC Gillings School of Global Public Health"
  }},
  "sameAs": [
    "https://orcid.org/0000-0001-6126-2459",
    "{scholar}"
  ]
}}
</script>

<!-- Set the theme before first paint so there is no flash of the wrong colours. -->
<script>
  (function () {{
    try {{
      var t = localStorage.getItem("theme");
      if (t === "light" || t === "dark") {{
        document.documentElement.setAttribute("data-theme", t);
      }}
    }} catch (e) {{}}
  }})();
</script>

<style>
  /* ---- UNC palette -------------------------------------------------------
     Carolina Blue  #4B9CD3   Navy  #13294B   Basin Slate  #4F758B
     Carolina Blue on white is only ~2.4:1, so it is never used for body text
     or links - it is an accent (rules, focus rings, hover). All text/link
     colours below meet WCAG 2.2 AA (>=4.5:1) in both themes.
  --------------------------------------------------------------------------- */
  :root {{
    --carolina:  #4b9cd3;
    --navy:      #13294b;

    --bg:        #ffffff;
    --surface:   #f4f6f9;
    --text:      #23282f;   /* 13.5:1 on white */
    --muted:     #5b6570;   /*  5.4:1 on white */
    --faint:     #737d88;   /*  4.6:1 on white */
    --heading:   #13294b;   /* UNC Navy */
    --subhead:   #14568c;   /* UNC blue, darkened only as far as AA requires */
    --link:      #14568c;   /*  6.0:1 on white */
    --link-hover:#0e3f68;
    --rule:      #e2e6eb;
    --rule-2:    #cfd6de;
    --accent:    #4b9cd3;
    --focus:     #14568c;
    /* Altmetric serves its donut as an image with the score painted in near-
       black. It can't be restyled, so in dark mode we put a light disc behind
       it instead. In light mode there is nothing to fix. */
    --badge-backdrop: transparent;

    --serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, "Times New Roman", serif;
    --sans:  -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;

    --maxw: 1180px;
    --gutter: clamp(1.125rem, 4vw, 3rem);
  }}

  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg:        #0d1521;
      --surface:   #17223200;
      --surface:   #172232;
      --text:      #e7ecf2;   /* 14.6:1 on --bg */
      --muted:     #a7b2c0;   /*  7.6:1 */
      --faint:     #8b97a6;   /*  5.5:1 */
      --heading:   #ffffff;
      --subhead:   #4b9cd3;   /* true Carolina Blue - 6.6:1 on the dark bg */
      --link:      #7cbdea;   /*  8.3:1 */
      --link-hover:#a8d5f5;
      --rule:      #26334a;
      --rule-2:    #35455f;
      --accent:    #4b9cd3;
      --focus:     #7cbdea;
      --badge-backdrop: #eaeef4;
    }}
  }}
  :root[data-theme="dark"] {{
    --bg:        #0d1521;
    --surface:   #172232;
    --text:      #e7ecf2;
    --muted:     #a7b2c0;
    --faint:     #8b97a6;
    --heading:   #ffffff;
    --subhead:   #4b9cd3;
    --link:      #7cbdea;
    --link-hover:#a8d5f5;
    --rule:      #26334a;
    --rule-2:    #35455f;
    --accent:    #4b9cd3;
    --focus:     #7cbdea;
    --badge-backdrop: #eaeef4;
  }}

  @media (prefers-contrast: more) {{
    :root {{ --muted: var(--text); --faint: var(--text); --rule: var(--rule-2); }}
  }}

  *, *::before, *::after {{ box-sizing: border-box; }}

  html {{ scroll-behavior: smooth; -webkit-text-size-adjust: 100%; }}
  @media (prefers-reduced-motion: reduce) {{
    html {{ scroll-behavior: auto; }}
    *, *::before, *::after {{
      animation-duration: .001ms !important; animation-iteration-count: 1 !important;
      transition-duration: .001ms !important;
    }}
  }}

  body {{
    margin: 0;
    font-family: var(--sans);
    font-size: 1.0625rem;          /* 17px base for prose (bio, research, etc.) */
    line-height: 1.6;
    color: var(--text);
    background: var(--bg);
    -webkit-font-smoothing: antialiased;
  }}

  a {{ color: var(--link); text-decoration: none; }}
  a:hover {{ color: var(--link-hover); text-decoration: underline; }}
  /* Visible, high-contrast focus ring - keyboard users must be able to see it. */
  a:focus-visible, button:focus-visible, input:focus-visible,
  select:focus-visible, [tabindex]:focus-visible {{
    outline: 3px solid var(--focus);
    outline-offset: 2px;
    border-radius: 4px;
  }}

  img {{ max-width: 100%; height: auto; }}

  .sr-only {{
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap;
  }}
  .skip {{
    position: absolute; left: 50%; transform: translate(-50%, -140%);
    z-index: 100; background: var(--bg); color: var(--link);
    border: 2px solid var(--focus); border-radius: 0 0 6px 6px;
    padding: .65rem 1.25rem; font-weight: 600;
  }}
  .skip:focus {{ transform: translate(-50%, 0); }}

  .shell {{ max-width: var(--maxw); margin: 0 auto; padding-inline: var(--gutter); }}

  /* ---- nav --------------------------------------------------------------- */
  .topbar {{
    position: sticky; top: 0; z-index: 30;
    background: color-mix(in srgb, var(--bg) 90%, transparent);
    -webkit-backdrop-filter: saturate(180%) blur(10px);
    backdrop-filter: saturate(180%) blur(10px);
    border-bottom: 1px solid var(--rule);
  }}
  @supports not (background: color-mix(in srgb, red 50%, blue)) {{
    .topbar {{ background: var(--bg); }}
  }}
  .topbar .shell {{
    display: flex; align-items: center; gap: .35rem;
    min-height: 3.25rem;
  }}
  .navlink {{
    color: var(--muted); font-size: .9375rem;
    padding: .6rem .7rem; border-radius: 6px; line-height: 1;
  }}
  .navlink:hover {{ color: var(--text); background: var(--surface); text-decoration: none; }}
  .navlink:first-of-type {{ margin-left: calc(-1 * .7rem); }}
  .spacer {{ margin-left: auto; }}
  #theme {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 2.75rem; height: 2.75rem;           /* 44px touch target */
    background: none; border: 1px solid var(--rule); border-radius: 8px;
    color: var(--muted); cursor: pointer;
  }}
  #theme:hover {{ color: var(--text); border-color: var(--rule-2); background: var(--surface); }}
  #theme svg {{ width: 1.15rem; height: 1.15rem; }}
  :root[data-theme="dark"] #theme .i-sun,  .i-sun  {{ display: none; }}
  :root[data-theme="dark"] #theme .i-moon {{ display: block; }}
  .i-moon {{ display: block; }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) .i-moon {{ display: none; }}
    :root:not([data-theme="light"]) .i-sun  {{ display: block; }}
  }}
  :root[data-theme="dark"] .i-moon {{ display: none; }}
  :root[data-theme="dark"] .i-sun  {{ display: block; }}
  :root[data-theme="light"] .i-moon {{ display: block; }}
  :root[data-theme="light"] .i-sun  {{ display: none; }}

  /* ---- hero -------------------------------------------------------------- */
  .hero {{
    display: flex; align-items: stretch; gap: clamp(1.5rem, 4vw, 2.75rem);
    padding: clamp(2.5rem, 6vw, 4.5rem) 0 clamp(1rem, 2vw, 1.5rem);
  }}
  .hero-photo {{ flex: 0 0 auto; width: clamp(150px, 20vw, 260px); }}
  /* Photo spans exactly the height of the text column: top of image aligns
     with top of the name, bottom aligns with the bottom of the last line. */
  .hero-photo img {{
    width: 100%; height: 100%; object-fit: cover; object-position: center top;
    border-radius: 10px; display: block;
    background: var(--surface);
  }}
  .hero-body {{ min-width: 0; display: flex; flex-direction: column; }}
  h1 {{
    font-family: var(--serif); font-weight: 600;
    font-size: clamp(1.9rem, 4.2vw, 2.6rem); line-height: 1.12;
    letter-spacing: -.01em; color: var(--heading);
    margin: 0 0 .85rem;
  }}
  .bio {{ font-size: 1.0625rem; color: var(--text); }}
  .bio p {{ margin: 0 0 .7rem; }}
  .plinks {{ margin-top: auto; padding-top: 1rem; }}

  /* ---- author-level metrics (Google Scholar + OpenAlex) ------------------ */
  .author-metrics {{ margin: .9rem 0 0; display: flex; flex-direction: column; gap: .3rem; }}
  .metric-row {{
    margin: 0 0 .2rem; line-height: 1.55;
    font-size: .9375rem;         /* matches the profile links */
  }}
  /* Source name is a link styled exactly like the profile links (e.g. UNC). */
  .metric-src {{
    color: var(--link); text-decoration: underline; text-underline-offset: 2px;
    text-decoration-color: var(--rule-2); white-space: nowrap;
  }}
  .metric-src:hover {{ text-decoration-color: currentColor; }}
  .metric-nums {{ color: var(--muted); font-variant-numeric: tabular-nums; }}
  .metric-nums:not(:empty)::before {{ content: ": "; }}
  .plink {{ margin: 0 0 .2rem; font-size: .9375rem; line-height: 1.55; }}
  .plink a {{ text-decoration: underline; text-underline-offset: 2px;
              text-decoration-color: var(--rule-2); }}
  .plink a:hover {{ text-decoration-color: currentColor; }}
  .sep {{ margin: 0 .5rem; color: var(--faint); }}

  /* ---- sections ---------------------------------------------------------- */
  main section {{ padding-top: clamp(2.5rem, 5vw, 3.75rem); scroll-margin-top: 4.5rem; }}
  h2 {{
    font-family: var(--serif); font-weight: 600; color: var(--heading);
    font-size: clamp(1.45rem, 2.6vw, 1.75rem); letter-spacing: -.01em;
    margin: 0 0 1.25rem; padding-bottom: .5rem;
    border-bottom: 2px solid var(--accent);
  }}
  /* Section sub-headings ("Current grants", "Previous support", year headings)
     carry the UNC blue. In dark mode this becomes true Carolina Blue, which
     clears AA comfortably against the dark background. */
  h3 {{
    font-size: .8125rem; font-weight: 700; letter-spacing: .1em;
    text-transform: uppercase; color: var(--subhead);
    margin: 1.75rem 0 .75rem;
  }}
  h4 {{ font-size: 1rem; font-weight: 650; color: var(--heading); margin: 1.1rem 0 .25rem; }}
  main p {{ margin: 0 0 .6rem; }}
  main ul {{ margin: .5rem 0 0; padding-left: 1.25rem; }}
  main li {{ margin-bottom: .45rem; }}
  main li ul {{ margin-top: .45rem; }}
  #research h4 {{ margin-top: 1.35rem; }}
  #research h4 + p {{ color: var(--muted); }}
  /* Every section runs the full content width, same as the publication list. */

  /* ---- publications ------------------------------------------------------ */
  /* Plain text links, not buttons. */
  .yearnav {{
    font-size: .875rem; font-variant-numeric: tabular-nums;
    color: var(--faint); line-height: 1.9;
    margin: 0 0 .35rem;
  }}
  .yearnav a {{ color: var(--link); }}
  .yearnav a:hover {{ color: var(--link-hover); text-decoration: underline; }}
  .yearnav .sep {{ margin: 0 .3rem; color: var(--rule-2); }}

  h3.year {{
    font-size: .8125rem; margin: .45rem 0 .35rem;
    padding-bottom: .35rem; border-bottom: 1px solid var(--rule);
    /* Clears the sticky nav bar, so jumping to a year lands ON the heading
       rather than scrolling it up under the bar. */
    scroll-margin-top: 5rem;
  }}
  /* The year nav already sits directly above 2026 - no extra gap needed. */
  .year-block:first-child h3.year {{ margin-top: .2rem; }}
  ul.pubs {{ list-style: none; margin: 0; padding: 0; }}

  /* Grid, not flex: the metrics column is a fixed track, so every citation
     block is exactly the same width and the icons line up down the page. */
  /* Cite/PDF buttons | citation | badges */
  li.pub {{
    display: grid;
    grid-template-columns: 3.4rem minmax(0, 1fr) 8rem;
    align-items: start; column-gap: 0;
    margin: 0; padding: .6rem 0; border-radius: 8px;
    font-size: 1rem; line-height: 1.55;   /* publications stay at 16px */
    color: var(--text);           /* authors + journal read as body text */
  }}

  .pub-text {{
    min-width: 0;
    padding-left: .9rem;
    padding-right: 2.25rem;       /* breathing room after the citation */
  }}
  .pub-text p {{ margin: 0; }}
  .pub-text ul {{ margin-top: .4rem; }}
  /* "This article was published simultaneously in:" gets the same air as the
     gap between articles, and is indented to line up with the sub-citations
     below it (the sub-entry text sits 1.5rem further in than the parent text). */
  li.pub > .pub-text > p + p {{ margin-top: 1.2rem; margin-left: 1.5rem; }}
  .pub-text ul {{ padding-left: 1.1rem; }}
  .pub-text ul li {{ margin-bottom: .2rem; }}
  .pub-text strong {{ font-weight: 650; }}
  .pub-text em {{ color: inherit; }}
  /* Every hyperlink in a citation - title, PMID, protocol - is blue. */
  .pub-text a {{ color: var(--link); text-decoration: none; }}
  .pub-text a:hover {{ color: var(--link-hover); text-decoration: underline; }}
  /* Parent-article title is a block, so the authors always begin on the next
     line - whether the title is a link or (for a few book chapters) plain bold.
     Scoped to li.pub > so it never applies to the sub-entries inside a
     "published simultaneously in" list, which must stay on one line. */
  li.pub > .pub-text > p:first-child > a:first-child,
  li.pub > .pub-text > p:first-child > strong:first-child {{
    display: block; margin-bottom: .1rem;
  }}

  /* Two fixed-width slots. A badge that hides itself (zero citations, zero
     Altmetric mentions) leaves its slot standing, so the donuts on every other
     row stay in the same two columns. */
  .metrics {{
    display: grid; grid-template-columns: 3.25rem 3.25rem;
    align-items: center; column-gap: 1rem; min-height: 2.4rem;
  }}
  .slot {{
    display: flex; align-items: center; justify-content: center;
    min-width: 3.25rem; min-height: 2.4rem; line-height: 0;
  }}
  /* Both vendors inject their own markup; keep it inside its slot. */
  .slot > * {{ margin: 0 !important; }}

  /* Dark mode: the Altmetric donut's score is painted into the image in near-
     black, which vanishes on a dark background. Give the image a light disc to
     sit on. The donut's coloured ring is unaffected. */
  .altmetric-embed img,
  .altmetric-embed a img {{
    background: var(--badge-backdrop);
    border-radius: 50%;
  }}

  /* "Also published in" sub-entries get their own donuts, aligned to the same
     two columns as the parent article. The sub-list is pulled out to the right
     edge of the row (negative margin = metrics track + gap) so its metrics
     column lands exactly under the parent's. */
  /* The sub-list is pulled back out to the full row width - left edge and right
     edge both - so a sub-entry's buttons and donuts land in exactly the same
     columns as a parent article's. Only the citation TEXT is indented, which is
     what actually signals "this is a sub-entry". */
  .pub-text ul {{
    list-style: none;
    padding-left: 0;
    margin-left: -4.3rem;                             /* 3.4rem col + .9rem pad */
    margin-right: calc(-1 * (8rem + 2.25rem));        /* metrics col + gap */
  }}
  li.subpub {{
    display: grid;
    grid-template-columns: 3.4rem minmax(0, 1fr) 8rem;
    align-items: start; column-gap: 0;
    padding: .6rem 0;           /* same rhythm as the gap between articles */
  }}
  li.subpub:last-child {{ padding-bottom: 0; }}
  li.subpub > .metrics {{ min-height: 2rem; }}
  li.subpub > .pub-text {{
    padding-left: 2.4rem;       /* .9rem base + 1.5rem indent */
    padding-right: 2.25rem;
  }}
  /* Journal, volume, PMID all on one line for a sub-entry. */
  li.subpub > .pub-text p {{ margin: 0; display: block; }}
  li.subpub > .pub-text a {{ display: inline; }}

  @media (max-width: 47.99rem) {{
    .pub-text ul {{
      list-style: disc; padding-left: 1.1rem;
      margin-left: 0; margin-right: 0;
    }}
    li.subpub {{ display: list-item; }}
    li.subpub > .pub-text {{ padding: 0; }}
  }}

  /* ---- citation / PDF buttons -------------------------------------------- */
  /* Left column: "Cite" on top, "PDF" (open-access full text) beneath. */
  .cite-col {{
    display: flex; flex-direction: column; align-items: stretch;
    gap: .25rem;
  }}
  /* Shared pill styling for both buttons. */
  .cite-dl summary, .oa-pdf {{
    display: inline-flex; align-items: center; justify-content: center;
    gap: .25rem; padding: .22rem .3rem; min-height: 1.55rem;
    border: 1px solid var(--rule-2); border-radius: 6px;
    background: var(--bg); color: var(--muted);
    font-size: .72rem; font-weight: 600; line-height: 1;
    cursor: pointer; white-space: nowrap;
  }}
  .cite-dl summary svg, .oa-pdf svg {{ width: .8rem; height: .8rem; flex: none; }}
  .btn-label {{ letter-spacing: .01em; }}

  .oa-pdf:hover {{ color: #1a7a48; border-color: #1a7a48; text-decoration: none; }}
  :root[data-theme="dark"] .oa-pdf:hover {{ color: #5fce9a; border-color: #3a7a5c; }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) .oa-pdf:hover {{ color: #5fce9a; border-color: #3a7a5c; }}
  }}
  .oa-pdf[hidden], .oa-empty {{ display: none; }}

  .cite-dl {{ position: relative; }}
  .cite-dl summary {{ list-style: none; }}
  .cite-dl summary::-webkit-details-marker {{ display: none; }}
  .cite-dl summary::marker {{ content: ""; }}
  .cite-dl summary:hover {{ color: var(--link); border-color: var(--link); }}
  .cite-dl[open] summary {{ color: var(--link); border-color: var(--link); }}

  .cite-menu {{
    position: absolute; top: 2rem; left: 0; z-index: 15;
    display: flex; flex-direction: column; min-width: 7rem;
    background: var(--bg); border: 1px solid var(--rule-2);
    border-radius: 8px; padding: .25rem;
    box-shadow: 0 6px 20px rgba(0, 0, 0, .12);
  }}
  .cite-menu button {{
    font: inherit; font-size: .8125rem; text-align: left;
    background: none; border: 0; border-radius: 5px; cursor: pointer;
    color: var(--text); padding: .45rem .55rem; min-height: 2rem;
  }}
  .cite-menu button:hover {{ background: var(--surface); color: var(--link); }}
  .cite-menu button[disabled] {{ opacity: .55; cursor: default; }}

  /* "Download citations" bulk button, right-justified on the heading line. */
  .pubhead {{
    display: flex; align-items: center; gap: .5rem;
    margin-bottom: 1.25rem;
    padding-bottom: .5rem; border-bottom: 2px solid var(--accent);
  }}
  .pubhead h2 {{ margin: 0; padding: 0; border: 0; }}
  .cite-all {{ margin-left: auto; }}          /* push to the right end */
  .cite-all summary {{ min-height: 1.9rem; padding: .3rem .6rem; }}
  .cite-all summary svg {{ width: .95rem; height: .95rem; }}
  .cite-all .cite-menu {{ top: 2.4rem; left: auto; right: 0; }}  /* open leftwards */
  .cite-all .cite-menu button {{ min-width: 8.5rem; }}

  /* Desktop only, like the badges. */
  @media (max-width: 47.99rem) {{
    .cite-dl, .cite-dl-empty {{ display: none; }}
    .pubhead {{ display: block; }}
  }}

  /* Badges are desktop-only - see the loader script. Reclaim the column so a
     phone gets the full width for the citation itself. */
  @media (max-width: 47.99rem) {{
    .metrics {{ display: none; }}
  }}
  .altmetric-lazy {{ line-height: 0; }}
  .altmetric-embed {{ line-height: 0; }}

  [hidden], .hidden {{ display: none !important; }}

  /* ---- footer ------------------------------------------------------------ */
  footer {{
    margin-top: clamp(3rem, 7vw, 5rem);
    border-top: 1px solid var(--rule);
    padding: 1.25rem 0 3rem;
    font-size: .875rem; color: var(--faint);
  }}

  /* ---- responsive --------------------------------------------------------- */
  @media (max-width: 46rem) {{
    .navlink {{ display: none; }}
    .topbar .shell {{ justify-content: flex-end; }}
    .hero {{ flex-direction: column; align-items: flex-start; }}
    .hero-photo {{ width: 132px; height: 132px; }}
    li.pub {{ grid-template-columns: minmax(0, 1fr); row-gap: .5rem; }}
    .pub-text {{ padding-left: 0; padding-right: 0; }}
  }}

  /* ---- print --------------------------------------------------------------- */
  @media print {{
    .topbar, .metrics, .skip {{ display: none !important; }}
    li.pub {{ grid-template-columns: minmax(0, 1fr); }}
    body {{ color: #000; background: #fff; font-size: 10.5pt; }}
    a {{ color: #000; text-decoration: underline; }}
    li.pub {{ page-break-inside: avoid; }}
  }}
</style>
</head>
<body>

<a class="skip" href="#main">Skip to content</a>

<header class="topbar">
  <nav class="shell" aria-label="Sections">
    <a class="navlink" href="#research">Research</a>
    <a class="navlink" href="#teaching">Teaching</a>
    <a class="navlink" href="#service">Service</a>
    <a class="navlink" href="#publications">Publications</a>
    <span class="spacer"></span>
    <button id="theme" type="button" aria-pressed="false"
            aria-label="Switch to dark theme" title="Switch theme">
      <svg class="i-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"
           aria-hidden="true" focusable="false">
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>
      </svg>
      <svg class="i-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"
           aria-hidden="true" focusable="false">
        <circle cx="12" cy="12" r="4.2"/>
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>
      </svg>
    </button>
  </nav>
</header>

<main id="main" class="shell">

  <div class="hero">
    <div class="hero-photo">
      <img src="{photo}" alt="{photo_alt}" width="600" height="600" fetchpriority="high">
    </div>
    <div class="hero-body">
      <h1>{name}</h1>
      <div class="bio">{bio}</div>

      <!-- Author-level metrics. Populated from OpenAlex once per day; if the
           request fails the whole block simply never appears. -->
      <!-- Two citation summaries. Google Scholar comes from the committed
           scholar-stats.json (refreshed by a scheduled GitHub Action, al-folio
           style); OpenAlex is fetched live. Each row hides until its data is
           available, so a failure of either never leaves an empty label. -->
      <!-- The source name is the link (styled like the profile links above);
           the citation figures follow. -->
      <div class="author-metrics">
        <p class="metric-row" id="gs-row">
          <a class="metric-src" href="{scholar}" target="_blank"
             rel="noopener noreferrer">Google Scholar</a>
          <span class="metric-nums" id="gs-line"></span>
        </p>
        <p class="metric-row" id="oa-row" hidden>
          <a class="metric-src" id="oa-profile"
             href="https://openalex.org/works?filter=authorships.author.orcid:{orcid}"
             target="_blank" rel="noopener noreferrer">OpenAlex</a>
          <span class="metric-nums" id="stat-line"></span>
        </p>
      </div>

      <div class="plinks">{links}</div>
    </div>
  </div>

  <section id="research" aria-labelledby="h-research">
    <h2 id="h-research">Research</h2>
    {research}
  </section>

  <section id="teaching" aria-labelledby="h-teaching">
    <h2 id="h-teaching">Teaching</h2>
    {teaching}
  </section>

  <section id="service" aria-labelledby="h-service">
    <h2 id="h-service">Service</h2>
    {service}
  </section>

  <script type="application/json" id="csl-extra">{cslextra}</script>

  <section id="publications" aria-labelledby="h-publications">
    <div class="pubhead">
      <h2 id="h-publications">Publications</h2>
      <details class="cite-dl cite-all">{citemenu_all}</details>
    </div>
    <nav class="yearnav" aria-label="Jump to a publication year">
      {yearnav}
    </nav>
    <div id="publist">{publications}</div>
  </section>

</main>

<footer class="shell">
  <span>Updated {updated}</span>
</footer>

<script>
/* ------------------------------------------------------------------ theme */
(function () {{
  var btn  = document.getElementById("theme"),
      root = document.documentElement;

  function current() {{
    var set = root.getAttribute("data-theme");
    if (set) return set;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }}
  function sync() {{
    var dark = current() === "dark";
    btn.setAttribute("aria-pressed", String(dark));
    btn.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
  }}
  btn.addEventListener("click", function () {{
    var next = current() === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try {{ localStorage.setItem("theme", next); }} catch (e) {{}}
    sync();
  }});
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", sync);
  sync();
}})();

/* -------------------------------------------- author-level metrics (OpenAlex)
   Exactly ONE request, and at most one per 24 hours per visitor.

   The whole result is written to localStorage with a timestamp. On any reload
   inside that window we render straight from the cache and make no network
   call at all - which is what stops OpenAlex from throttling a page that gets
   refreshed repeatedly. A *failed* attempt is also stamped (with a shorter
   backoff), so a rejected request is not retried on the very next reload.
---------------------------------------------------------------------------- */
(function () {{
  var KEY      = "oa-author-v5",
      TTL      = 24 * 60 * 60 * 1000,   // success: refresh at most once a day
      BACKOFF  = 6 * 60 * 60 * 1000,    // failure: don't try again for 6 hours
      ORCID    = "{orcid}",
      box      = document.getElementById("oa-row"),
      lineEl   = document.getElementById("stat-line");

  if (!box || !window.fetch) return;

  // A result is only worth showing - or caching - if it actually has numbers in
  // it. OpenAlex can answer 200 OK with an empty author record, and the old code
  // happily rendered and cached that, which is why the line read all zeros and
  // then stayed that way: the zeros were sitting in localStorage.
  function valid(s) {{
    return !!s && s.cites > 0 && s.h > 0;
  }}

  function render(s) {{
    if (!valid(s)) return;
    lineEl.textContent =
      s.cites.toLocaleString() + " citations \\u00b7 h-index " + s.h +
      " \\u00b7 i10-index " + s.i10;
    // Upgrade the OpenAlex profile link to the canonical author page (e.g.
    // https://openalex.org/A5012345678) once we know the id; the static
    // fallback is a works search by ORCID.
    if (s.id) {{
      var link = document.getElementById("oa-profile");
      if (link) link.href = s.id;
    }}
    box.hidden = false;
  }}

  var store;
  try {{ store = JSON.parse(localStorage.getItem(KEY) || "null"); }} catch (e) {{}}

  if (store && store.ts) {{
    var age = Date.now() - store.ts;
    if (valid(store.s) && age < TTL) {{ render(store.s); return; }}  // fresh: no call
    if (!valid(store.s) && age < BACKOFF) return;                    // recently failed
    if (valid(store.s)) render(store.s);   // stale but usable - show, then refresh
  }}

  function remember(s) {{
    // Never cache an empty result as if it were a real one.
    var payload = valid(s) ? s : null;
    try {{
      localStorage.setItem(KEY, JSON.stringify({{ ts: Date.now(), s: payload }}));
    }} catch (e) {{}}
  }}

  function stats(a) {{
    var st = (a && a.summary_stats) || {{}};
    return {{
      id:    a && a.id,
      cites: a && a.cited_by_count,
      h:     st.h_index,
      i10:   st.i10_index
    }};
  }}

  function get(url) {{
    return fetch(url + "&mailto=" + encodeURIComponent("{email}"))
      .then(function (r) {{ if (!r.ok) throw 0; return r.json(); }});
  }}

  var BASE = "https://api.openalex.org/authors";

  // 1. Direct ORCID lookup. Usually enough.
  get(BASE + "/orcid:" + ORCID + "?")
    .then(function (a) {{
      var s = stats(a);
      if (valid(s)) return s;

      // 2. That record was empty. An ORCID can map to more than one OpenAlex
      //    author entity (a merged or stub duplicate). Search instead and take
      //    the entity with the most citations.
      return get(BASE + "?filter=orcid:" + ORCID + "&per-page=25")
        .then(function (d) {{
          var best = (d.results || []).reduce(function (acc, cur) {{
            return (!acc || (cur.cited_by_count || 0) > (acc.cited_by_count || 0))
              ? cur : acc;
          }}, null);
          return stats(best || {{}});
        }});
    }})
    .then(function (s) {{
      render(s);
      remember(s);   // a still-empty result is stored as a failure, not as zeros
    }})
    .catch(function () {{ remember(null); }});   // stamp the failure, back off
}})();

/* ------------------------------------------------ Google Scholar citations
   Google Scholar has no API, so - exactly as the al-folio Jekyll theme does -
   the number is produced out of band by a scheduled GitHub Action that scrapes
   the profile and commits scholar-stats.json. This page just reads that file
   (same-origin, no rate limit) and drops the count into the button. If the file
   is missing or the count is zero, the button still links to the profile.
---------------------------------------------------------------------------- */
(function () {{
  var row = document.getElementById("gs-row"),
      el  = document.getElementById("gs-line");
  if (!row || !el || !window.fetch) return;
  fetch("scholar-stats.json", {{ cache: "no-cache" }})
    .then(function (r) {{ if (!r.ok) throw 0; return r.json(); }})
    .then(function (d) {{
      if (!d || !(d.citations > 0)) return;
      var parts = [d.citations.toLocaleString() + " citations"];
      if (d.hindex)   parts.push("h-index " + d.hindex);
      if (d.i10index) parts.push("i10-index " + d.i10index);
      el.textContent = parts.join(" \\u00b7 ");
      row.hidden = false;
    }})
    .catch(function () {{}});
}})();

/* ------------------------------------------------------- download citation
   Formats are generated in the browser from CSL-JSON, so one fetch per article
   serves every format, and everything is cached for 30 days.

   Getting the CSL is the fiddly part, because the two obvious sources behave
   differently in a browser:

     * Crossref  - keyed on DOI. Sends CORS headers. Reliable.
     * NCBI ctxp - keyed on PMID. Does NOT reliably send CORS headers, which is
                   why the first version of this failed for every PubMed-indexed
                   article (i.e. most of them).

   So the chain is: try ctxp, and if the browser blocks it, fall back to NCBI
   E-utilities (which does send CORS) purely to translate PMID -> DOI, then go
   to Crossref. Every path ends in CSL-JSON.
---------------------------------------------------------------------------- */
(function () {{
  var CACHE = "csl-v2",
      TTL   = 30 * 24 * 60 * 60 * 1000,
      GAP   = 250;      // ms between sequential Crossref calls

  /* --- cache ------------------------------------------------------------- */

  function readCache() {{
    try {{ return JSON.parse(localStorage.getItem(CACHE) || "{{}}"); }}
    catch (e) {{ return {{}}; }}
  }}
  function writeCache(all) {{
    try {{ localStorage.setItem(CACHE, JSON.stringify(all)); }} catch (e) {{}}
  }}
  function cacheGet(id) {{
    var hit = readCache()[id];
    return (hit && (Date.now() - hit.ts) < TTL) ? hit.d : null;
  }}
  function cacheSet(map) {{
    var all = readCache();
    Object.keys(map).forEach(function (k) {{ all[k] = {{ ts: Date.now(), d: map[k] }}; }});
    writeCache(all);
  }}

  // Hand-written records for items with no PMID and no DOI (NICE monographs,
  // book chapters, the PCORI report). Baked into the page, so no fetch at all.
  var EXTRA = {{}};
  try {{
    EXTRA = JSON.parse(document.getElementById("csl-extra").textContent) || {{}};
  }} catch (e) {{}}

  function idOf(it) {{
    if (it.pmid) return "pmid:" + it.pmid;
    if (it.doi)  return "doi:" + String(it.doi).toLowerCase();
    return "csl:" + it.csl;
  }}

  /* --- sources ----------------------------------------------------------- */

  function json(url) {{
    return fetch(url, {{ headers: {{ "Accept": "application/json" }} }})
      .then(function (r) {{ if (!r.ok) throw new Error(r.status); return r.json(); }});
  }}

  function ctxp(pmids) {{
    return json("https://api.ncbi.nlm.nih.gov/lit/ctxp/v1/pubmed/?format=csl&id=" +
                pmids.join(","))
      .then(function (d) {{ return [].concat(d).filter(Boolean); }});
  }}

  function pmidToDoi(pmids) {{
    return json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi" +
                "?db=pubmed&retmode=json&id=" + pmids.join(","))
      .then(function (d) {{
        var res = (d && d.result) || {{}}, map = {{}};
        pmids.forEach(function (p) {{
          var ids = (res[p] && res[p].articleids) || [];
          for (var i = 0; i < ids.length; i++) {{
            if (ids[i].idtype === "doi" && ids[i].value) {{ map[p] = ids[i].value; break; }}
          }}
        }});
        return map;
      }});
  }}

  function crossref(doi) {{
    return json("https://api.crossref.org/works/" + encodeURIComponent(doi) +
                "/transform/application/vnd.citationstyles.csl+json");
  }}

  function chunk(a, n) {{
    var out = [];
    for (var i = 0; i < a.length; i += n) out.push(a.slice(i, i + n));
    return out;
  }}

  function sleep(ms) {{
    return new Promise(function (r) {{ setTimeout(r, ms); }});
  }}

  /*  items: [{{pmid, doi}}]  ->  Promise<{{id: cslObject}}>  */
  function getCSL(items, onProgress) {{
    var found = {{}}, need = [];

    items.forEach(function (it) {{
      var id = idOf(it);
      if (it.csl && EXTRA[it.csl]) {{ found[id] = EXTRA[it.csl]; return; }}
      var hit = cacheGet(id);
      if (hit) found[id] = hit; else need.push(it);
    }});

    var done = items.length - need.length;
    function tick() {{ if (onProgress) onProgress(++done, items.length); }}

    if (!need.length) return Promise.resolve(found);

    var pmids = need.filter(function (i) {{ return i.pmid; }})
                    .map(function (i) {{ return i.pmid; }}),
        dois  = need.filter(function (i) {{ return !i.pmid && i.doi; }})
                    .map(function (i) {{ return i.doi; }});

    // Step 1: try NCBI's citation exporter in batches of 50.
    var step1 = pmids.length
      ? Promise.all(chunk(pmids, 50).map(ctxp))
          .then(function (groups) {{
            var got = {{}};
            groups.forEach(function (g) {{
              g.forEach(function (d) {{
                var pm = d && (d.PMID || d.pmid);
                if (pm && d.title) {{ got["pmid:" + pm] = d; }}
              }});
            }});
            // Anything ctxp didn't answer for still needs handling.
            var missing = pmids.filter(function (p) {{ return !got["pmid:" + p]; }});
            Object.keys(got).forEach(function (k) {{ found[k] = got[k]; tick(); }});
            return missing;
          }})
          .catch(function () {{ return pmids; }})   // CORS-blocked: all of them
      : Promise.resolve([]);

    // Step 2: whatever PubMed couldn't serve, translate PMID -> DOI and use
    //         Crossref instead.
    return step1
      .then(function (missing) {{
        if (!missing.length) return [];
        return Promise.all(chunk(missing, 100).map(pmidToDoi))
          .then(function (maps) {{
            var pairs = [];
            maps.forEach(function (m) {{
              Object.keys(m).forEach(function (p) {{
                pairs.push({{ id: "pmid:" + p, doi: m[p] }});
              }});
            }});
            return pairs;
          }})
          .catch(function () {{ return []; }});
      }})
      .then(function (pairs) {{
        dois.forEach(function (d) {{
          pairs.push({{ id: "doi:" + String(d).toLowerCase(), doi: d }});
        }});

        // Step 3: Crossref, sequentially and politely.
        return pairs.reduce(function (chain, p) {{
          return chain.then(function () {{
            return crossref(p.doi)
              .then(function (d) {{ if (d && d.title) found[p.id] = d; }})
              .catch(function () {{}})
              .then(function () {{ tick(); return sleep(GAP); }});
          }});
        }}, Promise.resolve());
      }})
      .then(function () {{
        cacheSet(found);
        return found;
      }});
  }}

  /* --- CSL-JSON -> output formats ---------------------------------------- */

  function first(v) {{ return Array.isArray(v) ? v[0] : v; }}

  function authors(d) {{
    return (d.author || []).map(function (a) {{
      if (a.literal) return a.literal;
      var fam = a.family || "", giv = a.given || "";
      return fam + (giv ? ", " + giv : "");
    }});
  }}
  function year(d) {{
    var p = d.issued && d.issued["date-parts"] && d.issued["date-parts"][0];
    return p && p[0] ? String(p[0]) : "";
  }}
  function journal(d) {{ return first(d["container-title"]) || ""; }}
  function titleOf(d) {{ return first(d.title) || ""; }}

  function toRIS(d) {{
    var L = ["TY  - JOUR"];
    authors(d).forEach(function (a) {{ L.push("AU  - " + a); }});
    if (titleOf(d)) L.push("TI  - " + titleOf(d));
    if (journal(d)) {{ L.push("JO  - " + journal(d)); L.push("T2  - " + journal(d)); }}
    if (year(d))    L.push("PY  - " + year(d));
    if (year(d))    L.push("DA  - " + year(d) + "///");
    if (d.volume)   L.push("VL  - " + d.volume);
    if (d.issue)    L.push("IS  - " + d.issue);
    if (d.page)     L.push("SP  - " + d.page);
    if (d.DOI)      L.push("DO  - " + d.DOI);
    if (d.PMID)     L.push("AN  - " + d.PMID);
    if (d.URL)      L.push("UR  - " + d.URL);
    L.push("ER  - ");
    L.push("");
    return L.join("\\r\\n");
  }}

  function toENW(d) {{
    var L = ["%0 Journal Article"];
    authors(d).forEach(function (a) {{ L.push("%A " + a); }});
    if (titleOf(d)) L.push("%T " + titleOf(d));
    if (journal(d)) L.push("%J " + journal(d));
    if (year(d))    L.push("%D " + year(d));
    if (d.volume)   L.push("%V " + d.volume);
    if (d.issue)    L.push("%N " + d.issue);
    if (d.page)     L.push("%P " + d.page);
    if (d.DOI)      L.push("%R " + d.DOI);
    if (d.PMID)     L.push("%M " + d.PMID);
    if (d.URL)      L.push("%U " + d.URL);
    L.push("");
    return L.join("\\r\\n");
  }}

  function bibKey(d) {{
    var a = (d.author && d.author[0] && (d.author[0].family || d.author[0].literal)) || "ref";
    return String(a).replace(/[^A-Za-z]/g, "") + (year(d) || "");
  }}
  function bibClean(s) {{ return String(s).replace(/[{{}}]/g, ""); }}

  function toBIB(d) {{
    var f = [];
    if (d.author && d.author.length)
      f.push("  author = {{" + bibClean(authors(d).join(" and ")) + "}}");
    if (titleOf(d)) f.push("  title = {{" + bibClean(titleOf(d)) + "}}");
    if (journal(d)) f.push("  journal = {{" + bibClean(journal(d)) + "}}");
    if (year(d))    f.push("  year = {{" + year(d) + "}}");
    if (d.volume)   f.push("  volume = {{" + d.volume + "}}");
    if (d.issue)    f.push("  number = {{" + d.issue + "}}");
    if (d.page)     f.push("  pages = {{" + bibClean(d.page) + "}}");
    if (d.DOI)      f.push("  doi = {{" + d.DOI + "}}");
    if (d.URL)      f.push("  url = {{" + d.URL + "}}");
    return "@article{{" + bibKey(d) + ",\\n" + f.join(",\\n") + "\\n}}\\n";
  }}

  function toCSL(d) {{ return JSON.stringify(d, null, 2) + "\\n"; }}

  var FORMATS = {{
    ris: {{ ext: "ris",  join: "",   make: toRIS,
           wrap: null,  label: "RIS" }},
    bib: {{ ext: "bib",  join: "\\n", make: toBIB,  wrap: null,  label: "BibTeX" }},
    enw: {{ ext: "enw",  join: "\\r\\n", make: toENW, wrap: null, label: "EndNote" }},
    csl: {{ ext: "json", join: null, make: toCSL,  wrap: "json", label: "CSL-JSON" }}
  }};

  /* --- download ----------------------------------------------------------- */

  function save(text, name) {{
    // text/plain is what every browser handles predictably; the extension is
    // what Zotero / EndNote / Mendeley actually key off.
    var blob = new Blob([text], {{ type: "text/plain;charset=utf-8" }}),
        url  = URL.createObjectURL(blob),
        a    = document.createElement("a");
    a.href = url;
    a.download = name;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () {{ URL.revokeObjectURL(url); }}, 2000);
  }}

  function serialise(fmt, records) {{
    var spec = FORMATS[fmt];
    if (spec.wrap === "json") {{
      return JSON.stringify(records, null, 2) + "\\n";
    }}
    return records.map(spec.make).join(spec.join || "");
  }}

  function itemsOf(el) {{
    return [].map.call(el.querySelectorAll(".cite-dl"), function (n) {{
      return {{
        pmid: n.dataset.pmid || "",
        doi:  n.dataset.doi  || "",
        csl:  n.dataset.csl  || ""
      }};
    }});
  }}

  /* --- single-article menus ----------------------------------------------- */

  document.addEventListener("click", function (ev) {{
    var inMenu = ev.target.closest && ev.target.closest(".cite-dl");
    [].forEach.call(document.querySelectorAll(".cite-dl[open]"), function (d) {{
      if (d !== inMenu) d.open = false;
    }});

    var btn = ev.target.closest && ev.target.closest(".cite-menu button");
    if (!btn || btn.disabled) return;

    var box  = btn.closest(".cite-dl"),
        fmt  = btn.dataset.fmt,
        spec = FORMATS[fmt];
    if (!box || !spec) return;

    var label = btn.textContent, bulk = box.classList.contains("cite-all");

    var items = bulk
      ? itemsOf(document.getElementById("publist"))
      : [{{ pmid: box.dataset.pmid || "", doi: box.dataset.doi || "",
            csl: box.dataset.csl || "" }}];

    // De-duplicate (an article can appear as both parent and sub-entry key).
    var seen = {{}};
    items = items.filter(function (it) {{
      if (!it.pmid && !it.doi && !it.csl) return false;
      var k = idOf(it);
      if (seen[k]) return false;
      seen[k] = 1;
      return true;
    }});
    if (!items.length) return;

    btn.disabled = true;
    btn.textContent = bulk ? "0%" : "…";

    getCSL(items, function (done, total) {{
      if (bulk) btn.textContent = Math.round((done / total) * 100) + "%";
    }})
      .then(function (map) {{
        var records = items
          .map(function (it) {{ return map[idOf(it)]; }})
          .filter(Boolean);

        if (!records.length) throw new Error("none");

        var name = bulk
          ? "mayo-wilson-publications." + spec.ext
          : (bibKey(records[0]) || "citation") + "." + spec.ext;

        save(serialise(fmt, records), name);

        btn.textContent = label;
        btn.disabled = false;
        box.open = false;
      }})
      .catch(function () {{
        btn.textContent = "Failed";
        setTimeout(function () {{
          btn.textContent = label;
          btn.disabled = false;
        }}, 2000);
      }});
  }});

  document.addEventListener("keydown", function (ev) {{
    if (ev.key !== "Escape") return;
    [].forEach.call(document.querySelectorAll(".cite-dl[open]"), function (d) {{
      d.open = false;
    }});
  }});
}})();

/* --------------------------------------------------- open-access full text
   Unpaywall indexes only LEGALLY free copies: publisher open access, PubMed
   Central, and author manuscripts in institutional repositories. It is not a
   paywall bypass, and nothing is re-hosted here - the button is a link to the
   copy the publisher or repository already makes free.

   Articles with no free copy simply never show the button, which is why it
   starts hidden. Resolved lazily, in small batches, cached for 30 days.
---------------------------------------------------------------------------- */
(function () {{
  var KEY   = "oa-links-v1",
      TTL   = 30 * 24 * 60 * 60 * 1000,
      GAP   = 200,
      EMAIL = "{email}";

  var nodes = [].slice.call(document.querySelectorAll(".oa-pdf"));
  if (!nodes.length || !window.fetch) return;

  var store = {{}};
  try {{ store = JSON.parse(localStorage.getItem(KEY) || "{{}}"); }} catch (e) {{}}

  function fresh(rec) {{ return rec && (Date.now() - rec.ts) < TTL; }}

  function show(el, url) {{
    if (!url) return;
    el.href = url;
    el.dataset.pdf = url;
    el.hidden = false;
  }}

  function keyFor(el) {{
    return el.dataset.doi
      ? "doi:" + el.dataset.doi.toLowerCase()
      : "pmid:" + el.dataset.pmid;
  }}

  // Clicking should DOWNLOAD the PDF, not navigate to it. We try to fetch it as
  // a blob and save it; many OA hosts (PMC, Europe PMC, most repositories) allow
  // this. If the host blocks cross-origin reads, we fall back to opening it in a
  // new tab so the click is never dead.
  document.addEventListener("click", function (ev) {{
    var a = ev.target.closest && ev.target.closest(".oa-pdf");
    if (!a || !a.dataset.pdf) return;
    ev.preventDefault();
    var url = a.dataset.pdf,
        name = (a.dataset.doi || a.dataset.pmid || "article")
                 .replace(/[^\\w.-]+/g, "_") + ".pdf",
        lbl = a.querySelector(".btn-label"),
        was = lbl ? lbl.textContent : "";
    if (lbl) lbl.textContent = "\\u2026";
    fetch(url).then(function (r) {{
      if (!r.ok) throw 0; return r.blob();
    }}).then(function (blob) {{
      var u = URL.createObjectURL(blob), t = document.createElement("a");
      t.href = u; t.download = name;
      document.body.appendChild(t); t.click(); document.body.removeChild(t);
      setTimeout(function () {{ URL.revokeObjectURL(u); }}, 2000);
      if (lbl) lbl.textContent = was;
    }}).catch(function () {{
      window.open(url, "_blank", "noopener");   // CORS-blocked: open instead
      if (lbl) lbl.textContent = was;
    }});
  }});

  // Paint anything already known.
  var pending = [];
  nodes.forEach(function (el) {{
    var rec = store[keyFor(el)];
    if (fresh(rec)) {{ show(el, rec.url); return; }}
    pending.push(el);
  }});

  if (!pending.length) return;

  function save() {{
    try {{ localStorage.setItem(KEY, JSON.stringify(store)); }} catch (e) {{}}
  }}

  // Unpaywall is keyed on DOI only. For PMID-only records we would need an
  // extra hop, so we let the citation-download path warm the cache instead and
  // only resolve the ones we can resolve directly.
  function unpaywall(doi) {{
    return fetch("https://api.unpaywall.org/v2/" + encodeURIComponent(doi) +
                 "?email=" + encodeURIComponent(EMAIL))
      .then(function (r) {{ if (!r.ok) throw 0; return r.json(); }})
      .then(function (d) {{
        var loc = d && d.best_oa_location;
        return (loc && (loc.url_for_pdf || loc.url)) || "";
      }});
  }}

  function pmidToDoi(pmids) {{
    return fetch("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi" +
                 "?db=pubmed&retmode=json&id=" + pmids.join(","))
      .then(function (r) {{ if (!r.ok) throw 0; return r.json(); }})
      .then(function (d) {{
        var res = (d && d.result) || {{}}, map = {{}};
        pmids.forEach(function (p) {{
          var ids = (res[p] && res[p].articleids) || [];
          for (var i = 0; i < ids.length; i++) {{
            if (ids[i].idtype === "doi" && ids[i].value) {{ map[p] = ids[i].value; break; }}
          }}
        }});
        return map;
      }})
      .catch(function () {{ return {{}}; }});
  }}

  function run() {{
    var pmids = pending.filter(function (e) {{ return !e.dataset.doi; }})
                       .map(function (e) {{ return e.dataset.pmid; }});

    var step = pmids.length
      ? (function () {{
          var chunks = [];
          for (var i = 0; i < pmids.length; i += 100) chunks.push(pmids.slice(i, i + 100));
          return Promise.all(chunks.map(pmidToDoi)).then(function (maps) {{
            var all = {{}};
            maps.forEach(function (m) {{
              Object.keys(m).forEach(function (k) {{ all[k] = m[k]; }});
            }});
            return all;
          }});
        }})()
      : Promise.resolve({{}});

    step.then(function (pmid2doi) {{
      pending.reduce(function (chain, el) {{
        var doi = el.dataset.doi || pmid2doi[el.dataset.pmid];
        if (!doi) {{
          store[keyFor(el)] = {{ ts: Date.now(), url: "" }};
          return chain;
        }}
        return chain.then(function () {{
          return unpaywall(doi)
            .then(function (url) {{
              store[keyFor(el)] = {{ ts: Date.now(), url: url }};
              show(el, url);
            }})
            .catch(function () {{}})
            .then(function () {{
              return new Promise(function (r) {{ setTimeout(r, GAP); }});
            }});
        }});
      }}, Promise.resolve()).then(save);
    }});
  }}

  if ("requestIdleCallback" in window) {{
    requestIdleCallback(run, {{ timeout: 4000 }});
  }} else {{
    setTimeout(run, 2000);
  }}
}})();

/* --------------------------------------------- article badges (lazy-loaded)
   Two third-party badges per article, both from Digital Science:

     * Dimensions  - citation count. data-hide-zero-citations means an uncited
                     paper renders nothing, and its fixed-width slot holds the
                     column open so every other donut stays aligned.
     * Altmetric   - attention score. data-hide-no-mentions does the same.

   Neither script is fetched until the publication list is close to the
   viewport, and each is fetched only once. If either script fails to load the
   page is unaffected - the badges simply never appear. No API calls of our own
   are made here, so there is nothing to rate-limit and nothing to cache.
---------------------------------------------------------------------------- */
(function () {{
  var list = document.getElementById("publist");
  if (!list) return;

  // Desktop only. On a phone the badges are hidden by CSS anyway, so loading
  // two third-party scripts there would cost bandwidth for nothing. Matches
  // the 47.99rem CSS breakpoint. Checked once, on load - rotating a phone to
  // landscape does not pull them in.
  if (window.matchMedia && !window.matchMedia("(min-width: 48rem)").matches) return;

  var started = false;

  function load(src, onload) {{
    var s = document.createElement("script");
    s.src = src;
    s.async = true;
    s.charset = "utf-8";
    if (onload) s.onload = onload;
    s.onerror = function () {{}};
    document.head.appendChild(s);
  }}

  function start() {{
    if (started) return;
    started = true;

    // Dimensions: badge.js scans for .__dimensions_badge_embed__ on load.
    load("https://badge.dimensions.ai/badge.js");

    // Altmetric: promote the placeholders, then let embed.js scan for them.
    [].forEach.call(document.querySelectorAll(".altmetric-lazy"), function (el) {{
      el.classList.remove("altmetric-lazy");
      el.classList.add("altmetric-embed");
    }});
    load("https://d1bxh8uas1mnw7.cloudfront.net/assets/embed.js", function () {{
      if (window._altmetric && typeof window._altmetric.embed_init === "function") {{
        window._altmetric.embed_init();
      }}
    }});
  }}

  if (!("IntersectionObserver" in window)) {{ start(); return; }}

  var io = new IntersectionObserver(function (entries) {{
    if (entries.some(function (e) {{ return e.isIntersecting; }})) {{
      io.disconnect();
      start();
    }}
  }}, {{ rootMargin: "400px 0px" }});

  io.observe(list);
}})();
</script>
{analytics}
</body>
</html>
"""

ANALYTICS = (
    '<!-- Cloudflare Web Analytics: cookie-free, no consent banner needed. -->\n'
    '<script defer src="https://static.cloudflareinsights.com/beacon.min.js" '
    "data-cf-beacon='{{\"token\": \"{token}\"}}'></script>\n"
)


def main():
    p = parse_profile()
    years = parse_publications()

    OUT.mkdir(exist_ok=True)

    page = PAGE.format(
        name=p["name"],
        photo=p["photo"],
        photo_alt=p["photo_alt"],
        email=p["email"],
        domain=DOMAIN,
        scholar=html.escape(SCHOLAR_PROFILE, quote=True),
        orcid=ORCID,
        openalex_author=OPENALEX_AUTHOR,
        desc=("Evan Mayo-Wilson, Associate Professor of Epidemiology at the UNC "
              "Gillings School of Global Public Health. Research on the benefits "
              "and harms of health interventions, clinical trial and systematic "
              "review methods, and research transparency."),
        bio=render("bio"),
        research=section("research"),
        teaching=section("teaching"),
        service=section("service"),
        links=profile_links_html(p),
        publications=publications_html(years),
        pubcount=sum(len(e) for _, e in years),
        citemenu_all=cite_menu(bulk=True),
        cslextra=json.dumps(CSL_EXTRA, ensure_ascii=False).replace("</", "<\\/"),
        yearnav='<span class="sep" aria-hidden="true">·</span>'.join(
            f'<a href="#y{y}">{y}</a>'
            for y, _ in years
            if int(y) != datetime.date.today().year   # skip the current year
        ),
        updated=datetime.date.today().strftime("%-d %B %Y")
                if os.name != "nt" else datetime.date.today().strftime("%d %B %Y"),
        analytics=(ANALYTICS.format(token=CLOUDFLARE_ANALYTICS_TOKEN)
                   if CLOUDFLARE_ANALYTICS_TOKEN else ""),
    )

    page = open_links_in_new_tab(page)
    (OUT / "index.html").write_text(page, encoding="utf-8")
    (OUT / "CNAME").write_text(DOMAIN + "\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    (OUT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: https://{DOMAIN}/sitemap.xml\n",
        encoding="utf-8",
    )
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>https://{DOMAIN}/</loc></url>\n"
        "</urlset>\n",
        encoding="utf-8",
    )

    src_img = ROOT / "images"
    if src_img.exists():
        shutil.copytree(src_img, OUT / "images", dirs_exist_ok=True)

    # Google Scholar stats: seed the file once, but never overwrite it on a
    # rebuild - the GitHub Action keeps it current, and clobbering it here would
    # wipe the latest count on every build.
    stats = OUT / "scholar-stats.json"
    if not stats.exists():
        stats.write_text(
            '{"citations": 0, "hindex": 0, "i10index": 0, "updated": ""}\n',
            encoding="utf-8",
        )

    n = sum(len(e) for _, e in years)
    with_pmid = sum(
        1 for _, es in years for e in es if PMID_RE.search(e)
    )
    print(f"Built {n} publications across {len(years)} years "
          f"({with_pmid} with PMIDs -> badges).")
    print(f"  {OUT / 'index.html'}")


if __name__ == "__main__":
    main()
