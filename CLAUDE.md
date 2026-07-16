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
- **The title link always goes to the journal/publisher's own page for the
  article** (or the monograph/report page for non-journal items) — never to
  PubMed. PMID gets its own separate hyperlink to PubMed (see below). If you
  ever find a title linking to PubMed instead of the publisher, that's a
  mistake to fix, not a style choice.
- A book chapter or item with no PMID/DOI at all (NICE monographs before they
  had real PMIDs, NASEM reports, book chapters) gets a hand-written record in
  `content/csl-extra.json` instead, keyed by its URL (or exact title if it has
  no link) — that's what feeds its citation-download formats since there's
  nothing to look up automatically.
- Every outbound link opens in a new tab automatically (site-wide behavior,
  not something to add per-link).
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
  Cite/PDF buttons and citation badges, and check its author order
  independently against its own published record — it's common for it to
  differ from the parent's. Sub-entries are ordered **most-cited to
  least-cited** (see the toolbar's "Sort by Citations" note below); when
  adding a new one, order by best current guess and the next re-sort will
  correct it.
- **Title capitalization: sentence case**, with three exceptions: the
  title's first word, the **first word after a colon** (e.g. "The PRISMA
  2020 statement: An updated guideline..."), and genuine
  acronyms/initialisms or proper nouns (`PRISMA`, `NIH`, `Johns Hopkins
  University`, a coined framework name like `TRUST Process`). A book's own
  title (as the container of a book chapter) stays in its own published
  title case, same as a journal name — the chapter's own title is still
  sentence-cased. Watch for the same generic word (`statement`, `extension`,
  `guidance`, `explanation and elaboration`) capitalized in one title and
  not another when it isn't actually part of an acronym/proper name either
  way — keep it lowercase throughout, matching the existing convention.

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
   - If there's a **separate standalone entry for the protocol**, what
     happens next depends on what kind of protocol it is:
     - A **preprint or registered protocol** (no independent journal
       publication — an OSF/MetaArXiv preprint, a PROSPERO registration)
       gets removed as a standalone entry once the results paper is added,
       folded instead into a trailing bracket on the results entry:
       `... PMID: [n](url). [Published protocol]` (or `[Registered
       protocol]`). Cited standalone only until the results are published.
     - A protocol **published as its own journal article** (its own
       PMID/DOI) keeps its standalone entry **permanently** — it's an
       independently citable output, not a placeholder. Add the same
       trailing bracket to the results entry too, but don't delete the
       protocol's own bullet.
2. Place the new entry in the right year and author-position slot (see house
   style above). If it's a simultaneous publication, order its sub-entries by
   citation count and double-check each sub-entry's own author order
   independently — it's common for author order to differ between the
   simultaneously-published versions.
3. Check the title against the capitalization rule above before committing it
   — sentence case, acronyms/proper-nouns excepted, capital after any colon.
4. Confirm the title link goes to the journal/publisher page (never PubMed)
   and that PMID/DOI are written in the format above.
5. `python3 build.py`, then `python3 generate_csl_cache.py` and
   `python3 generate_pub_stats.py` to fetch the new entry's CSL record, PDF
   link, and citation count ahead of time (see each script's docstring) —
   optional, since both have live client-side fallbacks, but running them is
   what keeps the Cite button, the PDF button, and "Sort by Citations" instant
   for the new entry instead of waiting a day for the scheduled Actions.
6. Commit and push.

## Features wired up

- **Dimensions + Altmetric** citation/attention donuts (desktop only, hidden at
  zero) via each article's PMID or DOI. Purely visual/on-page - not used for
  sorting (see `docs/pub-stats.json` below).
- **Publications toolbar** (desktop only, above the scroll box), one row
  laid out as a 3-column grid (`.pub-toolbar-row`: left group | search |
  right group) so the search box stays centered regardless of how wide the
  side groups are:
  - **Left**: the "Select all" `.pub-select` checkbox (open square, fills
    Carolina Blue with a white checkmark when checked), flush with the
    box's left border below it (`.cite-col-select-all` - no leading PDF
    slot here, unlike the per-article rows below), then the **Download**
    button (downloads selected citations as RIS/BibTeX/EndNote/CSL-JSON).
  - **Center**: a live search box (`#pub-search`) - filters the list as you
    type by year, author, title, or journal, with a light boolean grammar
    (bare words AND by default, `OR`, `NOT`/leading `-`, `"quoted
    phrases"`). Works the same whether the list is sorted by Year or
    Citations; re-applies after switching sort mode.
  - **Right**: the Year/Citations `.sort-btn` toggle (active mode filled
    Carolina Blue), flush with the box's right border.
  - None of the buttons (Download, Year, Citations) have a visible border
    or bold text - that inconsistency existed once and was deliberately
    removed.
  - Per article, the same shape repeats: PDF button (icon-only, open-access
    full text, opens in a new tab via `target="_blank"` - always, regardless
    of the host's CORS policy, rather than downloading on some hosts and
    merely opening on others) to the left of its `.pub-select` checkbox -
    both are fixed-size slots (`.oa-empty`/`.cite-dl-empty` placeholders
    hold the space even when empty) so the column stays aligned regardless
    of whether a given article has a PDF. The suggested download filename
    (`Author[_et_al]_Year_First_few_title_words.ext`, e.g.
    `Mayo-Wilson_2023_Harms_were_detected.pdf` - honored by browsers only for
    same-origin resources, so it's a best-effort, not a guarantee, for
    cross-origin publisher links) is set via the anchor's `download=""`
    attribute at build time (see `pdf_filename()` in `build.py`) but the
    *extension* isn't known until the client script resolves whether it's a
    real PDF or (rarely) a Word-doc preprint - see `show()`'s `type` param in
    the inline script.
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
  in order (see the script's own docstring for full detail): **(0)** a
  manually-supplied local copy in `docs/papers/`, keyed by DOI-slug filename
  (see below) - checked first, ahead of every live lookup; **(1)** Unpaywall's
  `url_for_pdf` - when an article has open-access copies at more than one
  location, a **publisher-hosted copy is always tried before a
  repository/university one** (Unpaywall's `host_type` field), even if
  Unpaywall's own "best" pick was the repository copy; this ordering applies
  to steps (1)-(3) here, all of which iterate the same location list;
  **(2)** a same-domain pattern for medRxiv/bioRxiv
  (`.full.pdf`) and OSF (`/download`); **(3)** the publisher's own
  `<meta name="citation_pdf_url">` tag (the same convention Google Scholar
  reads), tried against every OA location's own page, not just the DOI
  redirect; **(4)** NCBI Bookshelf's own PDF convention for book-type PMIDs
  with no DOI (the NICE guideline monographs); **(5)** the entry's own
  `[Preprint on X]` bracket link, PDF preferred, falling back to a genuine
  Word-doc manuscript (`"type": "docx"` in the JSON) only if no PDF exists
  anywhere. **Every candidate from (1)-(5) is verified** by requesting its
  first few bytes and checking for the `%PDF-` magic number (or, for a
  preprint fallback, a zip signature plus a `word/` internal folder for
  `.docx`) before being trusted - never from headers, status code, or a
  URL's `.pdf` suffix alone, and *including* `url_for_pdf` itself: Unpaywall's
  crawler can have found a real PDF once at a URL that a plain request can't
  reach today. A resolved PDF is never identical to the article's own
  title-link URL - that pairing gets dropped as redundant.
  - **A hard limit worth knowing about**: SAGE, JAMA, BMJ, Wiley/Cochrane,
    and PMC's own website all sit behind a Cloudflare-style bot challenge
    that blocks a plain script even at a URL that looks like, and once
    genuinely was, a direct PDF link (confirmed directly - `Cf-Mitigated:
    challenge` header, an interactive "Just a moment..." page). This script
    does not attempt to defeat that - it's bot-detection evasion, not
    something to build into an unattended public pipeline, even though a
    real browser passes it invisibly. Articles whose only free copy sits
    behind one of these are correctly left without a button.
  - **`docs/papers/`** holds PDFs Evan has personally confirmed are free to
    redistribute (mostly for articles stuck behind the bot walls above, with
    no other legal route to a working link), named `<doi-slug>.pdf` (see
    `doi_slug()`) and picked up automatically by `generate_pub_stats.py` on
    its next run. Only ever used to fill a genuine gap - an article that
    already resolves a real PDF through the normal chain keeps linking to
    that original source instead. As a same-origin file, its suggested
    download filename is fully honored by every browser, unlike the
    cross-origin publisher links above.
    - **Source of these files**: Evan's personal EndNote library at
      `Papers/` (repo root - untracked, gitignored, local-only; not the
      public site). The library's own attachment storage
      (`Papers/Evan's Papers.Data/PDF/<id>/<filename>`, indexed by
      `Papers/Evan's Papers.Data/sdb/sdb.eni`, a SQLite file - `refs` table's
      `electronic_resource_number` column has the DOI, `file_res` maps
      `refs_id` → attachment path) is the actual full set he's vetted as
      shareable - that's what "I added PDFs to an EndNote file" means each
      time he says it, not any one flat export folder that happened to sit
      alongside it on a given day. **Match against the whole attachment
      store, not just whatever folder was used last time** - a session once
      only used a 76-file flat export folder a sibling project had produced
      from a subset of the library, missed 25 further genuine gaps that were
      only attached directly inside the library itself, and had to be
      corrected in a later session. Match by DOI (case-insensitive), verify
      each candidate is a real PDF (`%PDF-` magic number) before copying,
      and only copy for entries with no existing working PDF.
  - Institutional-subscription APIs (Elsevier, Wiley TDM, Scopus, Springer -
    used by sibling projects on this machine for author-permitted research
    use) are deliberately not used here: they're gated on personal/UNC
    credentials and IP-based entitlement, which isn't appropriate for a
    public site's automated pipeline.
  - Both the PDF buttons and "Sort by Citations" read this file first (see
    `PUB_STATS` in `build.py`'s inline script) and only fall back to a live
    per-article lookup (Unpaywall; nothing live for citations) for anything
    added since the last daily run. An id *present* in the file with no
    `pdf` field means "checked, nothing real exists" - don't confuse that
    with "not yet checked" (id absent entirely). Re-run
    `python3 generate_pub_stats.py` after adding papers for the same reason
    as the CSL cache above.
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

## Gotchas

- **Verify every PDF candidate, no exceptions** - including ones that look
  authoritative (Unpaywall's `url_for_pdf` itself was trusted blindly once;
  a real bug, not hypothetical - see `generate_pub_stats.py`'s docstring).
  Check actual bytes (`%PDF-` magic number), not headers/status/URL shape.
- **CSS `font:` shorthand resets `line-height`** if it appears *after* an
  explicit `line-height` declaration in the same rule (shorthand expansion
  clobbers earlier longhands) - list `font: inherit;` first, then override
  `font-size`/`font-weight`/`line-height` after it, not before.
- A global `[hidden], .hidden { display: none !important; }` utility rule
  exists in the page CSS - any other rule that needs to keep a `[hidden]`
  element in-flow (e.g. a fixed-width slot that should reserve its space
  while invisible) must also use `!important` with higher specificity, or it
  silently loses.
- **SQLite `LIKE` treats `_` as a single-char wildcard** (and is
  case-insensitive by default) - matching a literal underscore-containing
  string (e.g. hunting for `GUI_` in a filename column) needs `ESCAPE` or an
  exact/`IN` match, not a bare `LIKE '%GUI_%'` (that also matches "Guid...").
- A JS `function name(){}` declared inside one branch of an `if/else` isn't
  safe to reference from code that runs *before* the block textually (sloppy-
  mode hoisting is implementation-quirky here) - declare `var name = function(){}`
  above the branch instead and reassign inside it.
- The in-app Browser preview tool is flaky specifically around scrolled
  screenshots (blank captures, hung `scroll`/`scroll_to` calls) and
  `window.innerWidth`/layout reads right after `navigate` (spuriously 0) -
  a fresh tab + a short `wait` usually clears it. `javascript_tool` DOM/
  computed-style reads are reliable throughout; prefer them over screenshots
  for verifying anything precise (alignment, colors, attribute values).
- No test suite or linter exists in this repo - "verify" means: rebuild
  (`python3 build.py`) cleanly, `node --check` the extracted inline
  `<script>` if you touched the JS, and actually load the page (a local
  `python3 -m http.server` + the Browser tool) to confirm the specific
  behavior you changed.

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
