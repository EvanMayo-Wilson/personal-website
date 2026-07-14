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
- **Identifiers come only from the article's own title/journal links**, never
  from bracketed `[Published protocol]` / `[Preprint]` links. So an in-press
  paper with only a protocol link has **no title link and no download buttons**
  — that's intentional.
- "Also published in" items go in a nested markdown list under
  `This article was published simultaneously in:` and each becomes its own
  sub-entry with its own badges.

## Features wired up

- **Dimensions + Altmetric** citation/attention donuts (desktop only, hidden at
  zero) via each article's PMID or DOI.
- **Cite** button: downloads RIS / BibTeX / EndNote / CSL-JSON (built in-browser
  from CSL fetched from NCBI/Crossref). **PDF** button: open-access full text via
  Unpaywall. Both desktop-only.
- **Author metrics** below the Publications heading: Google Scholar (from
  `docs/scholar-stats.json`, refreshed by the Action) and OpenAlex (fetched
  live).
- **Cloudflare Web Analytics** (token in `build.py`, `CLOUDFLARE_ANALYTICS_TOKEN`).

## Domain / hosting notes

- Registrar: Tucows via Squarespace. Nameservers: `ns01–04.squarespacedns.com`.
- DNS records point the apex + `www` at GitHub Pages. Custom domain + HTTPS are
  set in the repo's Settings → Pages.
- Do **not** cancel the Squarespace domain registration (renews through 2027);
  only the website plan was dropped.

## Common tasks

- **Add a publication:** edit `content/publications.md`, place it in the right
  year and author-position slot, `python3 build.py`, commit, push.
- **Update bio/research/etc.:** edit the relevant `content/*.md`, rebuild, push.
- **Change layout/colors:** edit `build.py` (CSS is in the page template), rebuild.
