# evanmayo-wilson.org — project guide for Claude Code

This is Evan Mayo-Wilson's academic personal website. It is a **static site**
hosted free on **GitHub Pages**, serving at **https://www.evanmayo-wilson.org**.
It replaced a paid Squarespace site.

## How the site is built

- **All content lives in `content/*.md`** — never edit the HTML directly.
  - `content/profile.md` — name, photo, header profile links, email
  - `content/bio.md` — the two-sentence bio
  - `content/research.md`, `teaching.md`, `service.md`
  - `content/publications.md` — every publication, grouped by `## YEAR`
  - `content/dois.tsv` — DOI overrides for articles whose DOI isn't in the URL
  - `content/csl-extra.json` — hand-written citation metadata for items with no
    PMID/DOI (book chapters, NICE monographs, reports)
- **`build.py` generates the site** into **`docs/`** (which is what GitHub Pages
  serves). Run it after any content or template change:

  ```
  pip3 install markdown        # once
  python3 build.py
  ```

- `docs/index.html` is **generated — do not hand-edit it.** Change `build.py`
  (for structure/CSS/JS) or `content/*.md` (for text), then rebuild.

## Deploying = commit + push

GitHub Pages rebuilds automatically on push to `main`. So:

```
git pull --rebase      # ALWAYS pull first (see note below), then:
python3 build.py        # if you changed content or build.py
git add -A
git commit -m "…"
git push
```

**Always `git pull --rebase` before pushing.** A scheduled GitHub Action
(`.github/workflows/scholar-stats.yml`) commits `docs/scholar-stats.json` every
Monday, so the remote is often one commit ahead. Skipping the pull causes a
rejected push.

## Publications: house style (important)

- Within each year, entries are ordered by Evan's author position:
  **first author, then last author, then 2nd author, 3rd author, …**
- Each entry: `- [**Title**](article-url)` then a newline, then
  `Authors. *Journal* vol:pages. PMID: [n](pubmed-url).`  Bold **Mayo-Wilson E**.
  A blank line separates entries. The line break between title and authors
  can be a real markdown hard break (title line ending in two trailing
  spaces) or just a bare newline/no separator at all — `build.py` renders the
  title as its own block either way, so don't worry about matching this
  exactly; just don't insert a literal `<br>`-producing blank line between
  them (that would split it into two paragraphs).
- **Identifiers come only from the article's own title/journal links**, never
  from bracketed `[Published protocol]` / `[Preprint]` links. So an in-press
  paper with only a protocol link has **no title link and no download buttons**
  — that's intentional.
- PMID is written `PMID: [12345678](https://pubmed.ncbi.nlm.nih.gov/12345678/).`
  — number inside the link, period outside. DOI (only when there's no PMID)
  is written `DOI: [10.xxxx/yyyy](https://doi.org/10.xxxx/yyyy).` — same
  shape, and always capitalized "DOI", always hyperlinked to `doi.org`, even
  though the citation/badge code can technically read a DOI out of plain
  prose text as a fallback.
- If a DOI can't be read cleanly out of the article's own URL (e.g. the URL
  has a trailing `?journalCode=...` query string or a trailing `/full`
  path segment after the real DOI), **don't** try to fix the extraction
  regex in `build.py` for one entry — add an override line to
  `content/dois.tsv` instead (format documented at the top of that file).
  This is exactly what it's for.
- Items published in more than one place go in a nested markdown list under
  a `This article was published simultaneously in:` line, indented two
  spaces. Each sub-entry is a **full citation** in exactly the same shape as a top-level
  entry (own title link repeating the parent's title, own author list,
  its own journal/volume/pages/PMID-or-DOI) — not an abbreviated
  "*Journal*, vol:pages. PMID: n" fragment. Each sub-entry gets its own
  Cite/PDF buttons and citation badges.

## Adding a new paper

1. **Check for an existing placeholder first.** In-press/preprint/protocol
   versions of the same paper are often already on the site (e.g. an
   "In press" entry with only a `[Protocol on ...]` bracket link and no PMID,
   or a standalone protocol entry). Search `content/publications.md` for the
   title (or a close paraphrase — titles sometimes change slightly between
   preprint and final version) before adding a new bullet.
   - If the paper is already there as an in-press/protocol-only placeholder:
     **update that entry in place** with the final citation (journal, volume,
     pages, PMID) rather than adding a second entry for the same paper.
   - If there's a **separate standalone entry for the protocol** (its own
     bullet, own year), remove that standalone entry once the results paper
     is added, and instead append the protocol as a trailing bracket on the
     results entry: `... PMID: [n](url). [Published protocol]` (or
     `[Registered protocol]`), matching how every other protocol-then-results
     pair on the site is written. A protocol is cited standalone only when
     the results haven't been published yet.
2. Place the new entry in the right year and author-position slot (see house
   style above).
3. `python3 build.py`, then `python3 generate_csl_cache.py` and
   `python3 generate_pub_stats.py` to fetch the new entry's CSL record, PDF
   link, and citation count ahead of time (see each script's docstring) —
   optional, since both have live client-side fallbacks, but running them is
   what keeps the Cite button, the PDF button, and "Sort by Citations" instant
   for the new entry instead of waiting a day for the scheduled Actions.
4. Commit and push.

## Features wired up

- **Dimensions + Altmetric** citation/attention donuts (desktop only, hidden at
  zero) via each article's PMID or DOI. Purely visual/on-page - not used for
  sorting (see `docs/pub-stats.json` below).
- **Publications toolbar** (desktop only, above the scroll box), one row:
  the "Select all" `.pub-select` checkbox (open square, fills Carolina Blue
  with a white checkmark when checked), flush with the box's left border
  below it (`.cite-col-select-all` - no leading PDF slot here, unlike the
  per-article rows below); then the **Download selected citations** button;
  then, pushed to the right, the Year/Citations `.sort-btn` toggle (active
  mode filled Carolina Blue). None of the three buttons have a visible
  border. Per article, the same shape repeats: PDF button (icon-only,
  open-access full text, opens in a new tab via `target="_blank"` - always,
  regardless of the host's CORS policy, rather than downloading on some
  hosts and merely opening on others) to the left of its `.pub-select`
  checkbox - both are fixed-size slots (`.oa-empty`/`.cite-dl-empty`
  placeholders hold the space even when empty) so the column stays aligned
  regardless of whether a given article has a PDF.
  - Re-sorting (either direction) scrolls `.pub-scroll` back to the top.
  - "Citations" mode ranks the whole list by `docs/pub-stats.json`'s
    precomputed OpenAlex citation count (falls back to 0, i.e. sorts last,
    for anything added since the file was last refreshed), then year - see
    `generate_pub_stats.py` below. This used to force-load every Dimensions
    badge and scrape citation counts back out of the rendered DOM, which is
    why it was slow; that whole mechanism is gone. Simultaneous-publication
    sub-entries stay nested under their own parent article, sorted by the
    parent's count. Switching back to "Year" restores the exact original DOM
    order (each `<li>` remembers its original parent/position from load).
  - CSL-JSON for the downloads is looked up in this order: `content/csl-extra.json`
    (hand-written, for items with no PMID/DOI) → `docs/csl-cache.json`
    (pre-fetched for every other PMID/DOI by `generate_csl_cache.py` — this is
    what makes downloads feel instant) → the visitor's browser localStorage
    (30-day TTL) → a live fetch from NCBI ctxp, falling back to Crossref, which
    then gets cached. Re-run `python3 generate_csl_cache.py` after adding
    papers so new entries hit the fast path too (not required — the
    live-fetch fallback still works without it).
- **`docs/pub-stats.json`**, refreshed daily by `.github/workflows/pub-stats.yml`
  running `generate_pub_stats.py`: for every article with a PMID/DOI, a real
  open-access PDF link and an OpenAlex citation count. PDF resolution tries,
  in order: Unpaywall's `url_for_pdf`; a same-domain pattern for medRxiv/
  bioRxiv (`.full.pdf`) and OSF (`/download`); the publisher's own
  `<meta name="citation_pdf_url">` tag (the same convention Google Scholar
  reads - catches articles Unpaywall's own record is incomplete for, e.g. a
  fully-open BMC/Springer article whose Unpaywall entry has no `url_for_pdf`
  at all); NCBI Bookshelf's own PDF convention for the handful of PMIDs that
  are book records with no DOI (the NICE guideline monographs). Every
  candidate is verified by actually requesting its first few bytes and
  checking for the `%PDF-` magic number before being trusted - several hosts
  that genuinely serve a PDF send no distinguishing `Content-Type` at all
  (F1000Research, OSF both serve `application/octet-stream`), while a host
  blocking a paywalled PDF often serves an HTML page with a plain 200 rather
  than an error, so neither headers nor status code alone are reliable.
  Institutional-subscription APIs (Elsevier, Wiley TDM, Scopus, Springer -
  used by sibling projects on this machine for author-permitted research
  use) are deliberately not used here: they're gated on personal/UNC
  credentials and IP-based entitlement, which isn't appropriate for a public
  site's automated pipeline. A resolved PDF is never identical to the
  article's own title-link URL - that pairing gets dropped as redundant. Both the PDF buttons and "Sort by
  Citations" read this file first (see `PUB_STATS` in `build.py`'s inline
  script) and only fall back to a live per-article lookup (Unpaywall; nothing
  live for citations) for anything added since the last daily run. An id
  *present* in the file with no `pdf` field means "checked, nothing real
  exists" - don't confuse that with "not yet checked" (id absent entirely).
  Re-run `python3 generate_pub_stats.py` after adding papers for the same
  reason as the CSL cache above.
- **Author metrics** below the Publications heading, one line: Google Scholar
  (from `docs/scholar-stats.json`, refreshed by the Action) and OpenAlex
  (fetched live) - just a gap between them, no separator glyph. OpenAlex is
  desktop-only; mobile shows only Google Scholar.
- **Cloudflare Web Analytics** (token in `build.py`, `CLOUDFLARE_ANALYTICS_TOKEN`).
- **Mobile** (≤46rem): `.mobilenav`, a small sticky text nav, is the first
  thing in `<main>` (above the hero) and stays visible while scrolling. The
  hero photo uses a separate, already-cropped-to-face image
  (`images/Square_Headshot_Mobile.png`, `MOBILE_PHOTO` in `build.py`) instead
  of the full chest-up photo. Citation badges, the selection/sort toolbar, and
  the publications year-jump/scroll-box are desktop-only throughout. The
  desktop `.topbar` is hidden entirely on mobile - always just follows the
  system light/dark setting, no theme toggle there.
- **"Research" nav link** (both desktop `.topbar` and mobile `.mobilenav`)
  goes to the top of the page (`#top`, on `<body>`), not to the Research
  section.

## Domain / hosting notes

- Registrar: Tucows Domains Inc. (Squarespace's domain product is a Tucows/OpenSRS
  reseller). Registration is paid through **2027-05-28** - confirmed via
  `whois evanmayo-wilson.org` on 2026-07-15. Domain status was `ok` (unlocked)
  as of the same date, with an EPP/auth transfer code already in hand - see
  [[feedback_domain_transfer]] for the transfer walkthrough given when that
  came up.
- **Nameservers are Cloudflare's** (`*.ns.cloudflare.com`), not Squarespace's -
  confirmed via `dig NS` on 2026-07-15. DNS (apex + `www`) is managed in
  Cloudflare's dashboard and proxied (orange-cloud) in front of GitHub Pages,
  not pointed directly at GitHub's IPs. This means a registrar transfer away
  from Squarespace/Tucows does **not** touch live DNS at all, as long as
  nameservers aren't changed during the transfer.
- Custom domain + HTTPS are set in the repo's Settings → Pages (GitHub still
  needs the apex + `www` configured there regardless of where DNS lives).
- Do **not** cancel the domain registration - it's active and paid through
  2027 independent of the Squarespace *website* plan, which was already
  dropped earlier.

## Common tasks

- **Add a publication:** see "Adding a new paper" above (check for an
  existing in-press/protocol placeholder first).
- **Add a grant** (`content/research.md`): if the grant can be found on NIH
  RePORTER, hyperlink the whole `(FUNDER grant-number)` parenthetical to its
  RePORTER project page - e.g. `[(AHRQ R01HS029877)](https://reporter.nih.gov/search/.../projects)`,
  not just the grant number alone (too subtle to read as a link inside a bold
  heading). Search reporter.nih.gov for the grant number to get the URL.
- **Update bio/research/etc.:** edit the relevant `content/*.md`, rebuild, push.
- **Change layout/colors:** edit `build.py` (CSS is in the page template), rebuild.
