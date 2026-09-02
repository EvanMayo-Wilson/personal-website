# evanmayo-wilson.org

Public static academic website. A push to `main` can publish externally; inspect
the exact diff and obtain any required content/publication approval first.

## Source and generated output

- Edit prose and publication records in `content/`.
- Edit HTML, CSS, JavaScript, and build behavior in `build.py`.
- `docs/index.html` is generated; never hand-edit it.
- `generate_csl_cache.py` and `generate_pub_stats.py` make separate networked
  updates. An ordinary build must not overwrite their caches.
- `docs/papers/` contains only copies already cleared for public redistribution.

Build from the repository root with `python3.14 build.py`. For reproducible
validation, set `SITE_UPDATED_DATE=YYYY-MM-DD`; omit it for the intended current
date on a real content update.

## Required validation

1. Pull/rebase before editing because GitHub Actions commit statistics to main.
2. Build twice with one fixed `SITE_UPDATED_DATE`; require byte-identical output.
3. Inspect all generated differences, including publication metadata and the
   footer date.
4. Extract inline JavaScript and run `node --check`.
5. Validate JSON, local asset references, paper links, PDF signatures, and DOCX
   package structure.
6. Preview `docs/` at desktop and mobile sizes and require zero console errors.
7. Do not push during a migration dry run.

## Boundaries

- Preserve the public site's existing design and content unless the task asks
  for a change.
- Do not add researcher records, credentials, acquired full text, or other
  private project data.
- Keep `CLAUDE.md` during Claude/Codex coexistence.
- Stage explicit paths; never sweep unrelated GitHub Action changes into a
  commit.
