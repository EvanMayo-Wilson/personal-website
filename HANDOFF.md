# Handoff — evanmayo-wilson.org

_Point-in-time snapshot for picking up mid-project. The durable, always-current
reference is `CLAUDE.md`; if the two disagree, trust `CLAUDE.md` and treat this
as stale._

## 2026-11-24 — Viewing stats: data-centre visits shown apart

Desk step `pw-datacentre-visits`. `fetch_web_analytics.py`: `DATA_CENTRE` network regex; `daily.json` has `dataCentreVisits`, `visits` excludes it (from 2026-11-02); countries/places exclude it; `--regeo-days N` redoes stored days.
- Last 7 days (17-23 Nov): 57 visits before, 44 after (13 data-centre). 28-day data-centre total: 42.
- Dashboard: page (KPI line, tooltip, notes bullets) and new daily/countries files published; page not seen rendering (no open tab).
- Pre-change history backup: `.analytics/history.pre-dc.json` (gitignored). Not pushed.

## 2026-11-23 — Viewing stats: where visitors are (state/region → city, network)

Session "machine-config: traffic page geo drill-down" (cli:d0b09725), Desk step `prompt-p-mwsdi87u`.
- `fetch_web_analytics.py` (`fb73dea`, review fixes `e1a3504`): photo-load `clientIP`s looked up locally in
  DB-IP Lite (CC BY 4.0) → `places`/`networks` per day in `.analytics/history.json` (Mac mini); IPs never written.
  `countries.json` rows now carry `key`/`level` (country, region, city, network). The scheduled task needs no change.
- Dashboard https://claude.ai/artifact/8kmmuNGYc2Wx11GtWBixMi: "Where visitors are" expandable table, notes
  bullet with DB-IP attribution. Detail from 2026-11-02 only; earlier visits show as "No location detail".
- Free plan refuses `clientASNDescription`, referrer and region fields; counties exist in no free source.
- Not pushed (public repo): check with `git status -sb`; see Desk `mc-push-publish-cv-path`.
- Finding, not acted on: many "visits" come from data-centre networks (Amazon/Ashburn, Google LLC, EGIHosting, M247),
  so the visit count includes automated browsers; Fastly/Cloudflare are probably iCloud Private Relay users.
  See them by expanding United States → Networks on the dashboard.

## 2026-11-18 — Desk sweep: PDFs, checker, EndNote, profiles (READ FIRST)

Session "personal-website: outstanding Desk work" (Opus 5.5). Re-derive status with the commands, not this text.

- **Ninan 2026:** still not on PubMed or Crossref as a JAMA Netw Open article (checked 2026-11-18;
  `curl -s "https://api.crossref.org/works?query.author=Ninan&query.bibliographic=outcome+definitions+registrations&filter=from-pub-date:2026-09-01&rows=5"`).
  Entry unchanged; this is the one open site item (Desk `personal-website` claude_next).
- **Checker:** `python3 check_publications.py` and `--online`: 175 entries, 0 errors, 0 warnings. The 7
  offline warnings of 11-04 were cleared by `6a1ae93` and later fixes.
- **EndNote (Desk `pw-endnote`, done):** TOP 2025 and the npj automated-approach paper are in both Drive
  libraries with PDFs since the 2026-10-20 rebuild, and both have site PDF buttons. The repo's local
  `Papers/` library is the old July copy; the live libraries are under `~/My Drive/Endnote/`.
- **PDF buttons (`bbd7a4d`, `d9a9dd7`, `5e4efbc`):** CD010544 links the UNC CDR copy; the 3 NICE
  monographs link NICE's own full-guideline PDF (`nice_full_guideline_pdf()`; Bookshelf is bot-walled);
  the NASEM 2022 letter report is hosted in `docs/papers/` (Evan's approval). Still none (no legal copy):
  Puljak 2026 (Elsevier closed), the APA and Russell Sage chapters, the HomVEE MetaArXiv preprint (OSF
  serves only a .docx). If the daily Action can't reach nice.org.uk the NICE buttons will drop: check
  `python3 -c "import json;print(json.load(open('docs/pub-stats.json'))['pmid:29718639'])"`.

## 2026-11-04 — refresh from the 27 Oct–4 Nov work (READ FIRST)

Doc-only refresh; no site change. Everything below is committed on `main`; tip at writing was
`6d12490` (run `git log -1` for the current one). The daily stats commits are noise.

- **Publications (27–30 Oct):** accuracy and style pass against PubMed/Crossref, six preprints
  added (`719d310`); Handbook of Research Synthesis chapter (2019) and the NASEM 2022 letter report
  added, Ninan 2026 noted as accepted at JAMA Netw Open (`6aad8ad`); Das 2026 published, JAMIA Open
  9(5):ooag197, PMID 42960168, medRxiv preprint kept as a bracket link (`c886f33`).
- **2 Nov:** MUDS PCORI report (PMID 37043591) moved from 2017 to 2018, its issue year (`3b9d5aa`).
- **4 Nov:** Teaching page course code EDIP 720 -> EPID 702, on Evan's approval (`0cb6b83`).
- **New checker:** `check_publications.py` (PubMed/Crossref accuracy plus house-style lint);
  `--online` compares with PubMed. Deliberate deviations go in `content/citation-exceptions.json`
  (NICE titles kept by Evan's decision, `489bee4`). The rules are in `CLAUDE.md` "Accuracy rules".
- **Privacy page** for the AI Drive Retention OAuth app: noindex and unlinked (`cde8270`).
- **Scholar stats:** the Mac Mini launchd job is the only scheduled writer; the Action is
  manual-only (`40faaaa`, `a5add83`). Details in `CLAUDE.md`.
- **Check at writing:** `python3 build.py` builds cleanly (159 publications, 21 years, 124 with
  PMIDs); `check_publications.py` offline: 173 entries, 0 errors, 7 warnings (not triaged here).
- **Still open:** update the Ninan 2026 entry once its JAMA Netw Open citation appears. The July
  items below (PDFs for Cloudflare-blocked articles; EndNote references for the TOP statement and
  the npj paper) are unchanged.

---

## 2026-07-22 — post-migration cleanup (READ FIRST)

Second session on this date, after the workspace move below. Deleted files that
were migration-era leftovers or local junk; **no change to the live site** (none
of the removed files feed `build.py`). All committed + pushed to `main` in
**`68d2fd1`**.

- **Removed from the repo (tracked; recoverable from git history):**
  - `GUIDE.md` — the one-time migration walkthrough (domain lookup, cost,
    deploy, DNS repoint). Superseded by `CLAUDE.md`, and partly stale (it still
    described NS1/`*.nsone.net` nameservers; the site is on Cloudflare now).
  - `squarespace-support-email.md` — an obsolete 14-July support-email draft
    about a nameserver-propagation snag during the migration; long resolved.
- **Deleted from disk only (were gitignored — not in any commit):**
  - `ordering-preview.html` — a 412K one-off preview from the publication-
    ordering work; not part of the site.
  - Six `.DS_Store` files and `__pycache__/` — macOS/Python junk, auto-regenerated.
- **Pruned three dead `.gitignore` entries** for files no longer on disk:
  `site-classic/`, `site-refresh/`, `ICANN Lookup.pdf`.
- **`git gc`** — packed 438 loose objects; `.git` shrank 64.7 → 58.4 MiB
  (modest, since the `docs/papers/` PDFs already in history are compressed).
- **Kept deliberately** (surfaced, confirmed): `Papers/` (823M EndNote library,
  gitignored — source of `docs/papers/`), `docs/papers/`, top-level `images/`
  (build copies it into `docs/images/`), `content/`, `.github/`, the build
  scripts, `CLAUDE.md`, `HANDOFF.md`.

## 2026-07-22 — workspace move

The repo was **relocated** as part of a workspace reorg:

- **New path:** `~/Code/personal-website` (was `~/Code/personal-website` at
  session start, and historically `~/Claude/Personal website` — that old path
  no longer exists).
- **Remote:** `https://github.com/EvanMayo-Wilson/personal-website.git`
  (`origin`, fetch + push) — confirmed.
- The repo **briefly passed through Google Drive** during the move.
  **Integrity was verified before committing:**
  - `git fsck` → exit 0, only **dangling commits** reported (normal
    GC-pending objects from past amends/rebases; no `error`/`missing`/`corrupt`
    /`broken` entries).
  - `git status` → clean working tree on `main`, up to date with `origin/main`.
  - Functional check: `python3 build.py` runs cleanly and reproduces the
    committed `docs/index.html` exactly apart from the footer's build-date
    stamp (expected). The pipeline survived the round-trip intact.
- **Path audit** (`grep /Users/evanmw/Claude` and `Projects/cv/source`): **no
  tracked build/script/content file contains a hardcoded old path** — the site
  code uses relative paths. The only stale-path hits were this HANDOFF (now
  rewritten) and files inside the untracked local `Papers/` library backups
  (Evan's personal data — deliberately not touched).
- **`.gitignore` hardened:** `Papers/` and `docs/images/Square_Headshot.jpeg`
  are now ignored. Both were always *meant* to be untracked/local-only (CLAUDE.md
  already described `Papers/` as "gitignored"), but weren't actually ignored —
  a real risk of accidentally publishing Evan's EndNote library via `git add -A`.
  Files remain on disk; `generate_pub_stats.py` still reads `Papers/`.

**This session did NOT change the site.** Its actual work was on **Larissa's
website** (a sibling project), not this repo — see next note.

### Larissa's website (sibling project — for cross-reference)

This session's work happened in Larissa Jennings Mayo-Wilson's site, now a
sibling repo freshly cloned at **`~/Code/larissa-website`** (remote
`EvanMayo-Wilson/larissa-website`, private). What landed there (all committed +
pushed to its `main`, tip `4660399`): section-divider waves changed to a uniform
`6vw` height to match the live Squarespace site, and the Research grant order
verified as already-correct (no change). That repo's own `HANDOFF.md`/`CLAUDE.md`
have the details. **Nothing about it needs doing from this repo.** Its one open
item is publishing (GitHub Pages intentionally OFF, needs Evan's go-ahead).

## What this project is

Evan Mayo-Wilson's academic personal site — static HTML generated by `build.py`
from `content/*.md`, served from `docs/` via GitHub Pages at
`https://www.evanmayo-wilson.org`. No test suite/linter/branching model: direct
commits to `main`, plus two scheduled Actions that auto-commit
(`scholar-stats.yml` weekly, `pub-stats.yml` daily). Because of those Actions,
**always `git pull --rebase` before pushing.**

## Current state

- Branch `main` (no session branches — this repo commits direct to `main`),
  clean working tree. Current tip: **`68d2fd1`** (post-migration cleanup); the
  workspace move was `db3e443`.
- **Verification (no test suite/linter exists):** `python3 build.py` builds
  cleanly — 147 publications across 21 years, 120 with PMIDs; unchanged by the
  cleanup (removed files aren't build inputs). Date: 2026-07-22. `.git` was
  repacked with `git gc` (438 objects, ~58 MiB packed).
- Intentional local-only files (gitignored): `Papers/` (Evan's EndNote
  library, the source of `docs/papers/` PDFs) and
  `docs/images/Square_Headshot.jpeg`.

## Top 3 next steps

1. **Nothing is pending on the site itself** — no open bugs known. First real
   action next session: `cd ~/Code/personal-website`, `git pull --rebase`, read
   `CLAUDE.md`, and ask Evan what he wants next.
2. If Evan supplies more redistributable PDFs for Cloudflare-blocked articles
   (SAGE/JAMA/BMJ/Wiley-Cochrane/PMC), drop them in `docs/papers/<doi-slug>.pdf`
   and re-run `generate_pub_stats.py` — but only when asked.
3. Two supplied papers (the TOP statement, the in-press "npj automated approach"
   paper) still have no reference in the EndNote library and sit in
   `Papers/PDFs to attach/`; creating those EndNote references is Evan's to do
   (hand-editing EndNote's SQLite DB risks corrupting its index).

## Gotchas

- **`git pull --rebase` before every push** — the daily/weekly Actions
  auto-commit, so the remote is often ahead.
- **Never commit `Papers/`** — Evan's personal EndNote library (now gitignored,
  but be careful with `git add -f`). Not all its PDFs are redistributable.
- The rest live in `CLAUDE.md`'s own "Gotchas" section (read it first): verify
  every PDF candidate incl. `url_for_pdf` against the `%PDF-` magic number; CSS
  `font:` shorthand resets `line-height` if placed after it; the site-wide
  `[hidden]{display:none!important}` rule needs `!important` to keep a hidden
  element in-flow; SQLite `LIKE` treats `_` as a wildcard; a `function` declared
  in one `if`/`else` branch isn't reliably hoisted for earlier use.
- No test suite/linter — "verify" = rebuild cleanly, `node --check` the
  extracted inline `<script>` if you touched the JS, and load the page.

## Environment

- macOS, Python 3 (`pip3 install markdown` once), Node available for
  `node --check`. No build/bundle step — JS lives inline in `build.py`.
- `generate_pub_stats.py` / `generate_csl_cache.py` hit public keyless APIs
  (Unpaywall, OpenAlex, NCBI, Crossref). One Cloudflare Analytics token is
  already in `build.py`. No secrets required for the build.

## Resume instruction (paste to start a fresh session)

```
Continuing work on evanmayo-wilson.org at ~/Code/personal-website
(remote: EvanMayo-Wilson/personal-website.git; the repo moved here from
~/Claude/Personal website in a workspace reorg).

cd ~/Code/personal-website, run `git pull --rebase` (scheduled Actions
auto-commit, so main is often ahead), then read CLAUDE.md first — it's the
single binding house-style + feature reference — and HANDOFF.md for the move +
cleanup notes. Direct commits to main; no branches. No open site bugs at handoff;
ask Evan what's next. (Larissa's separate site lives at ~/Code/larissa-website
and is fully handed off there — nothing to do from this repo.)
```
