# evanmayo-wilson.org — design, deployment, and domain notes

---

## 1. Your domain: what the ICANN lookup actually tells us

| Field | Value | What it means |
|---|---|---|
| Registrar | **TUCOWS.COM, CO.** (IANA 69) | Tucows/OpenSRS is the wholesale registrar **behind Squarespace Domains**. Squarespace resells through them. |
| Nameservers | `dns1–4.p05.nsone.net` | **NS1** — this is Squarespace's DNS. Your DNS is managed in the Squarespace panel today. |
| Status | `clientTransferProhibited`, `clientUpdateProhibited` | The domain is **locked**. Normal — but you must unlock it in Squarespace before any transfer. |
| Registrant | Contact Privacy Inc. (Toronto) | WHOIS privacy, provided by Tucows. Fine, and it comes free at most registrars. |
| Created | 2018-05-28 | |
| **Expires** | **2027-05-28** | You have ~10 months of runway. No rush, but see the warning below. |

### The one thing to be careful about

Because the domain sits inside Squarespace, **cancelling your Squarespace subscription and letting the domain lapse are easy to confuse.** Do them in this order:

1. Build + deploy the new site (Sections 3–4).
2. Repoint DNS to the new host, confirm the site loads.
3. *Then* cancel the Squarespace **website plan**.
4. Separately, either keep paying Squarespace's domain-only renewal (~$20/yr), or transfer the domain out (Section 5) for ~$10–12/yr.

Do **not** cancel first. If the domain expires you can lose the name.

**What you still need to check (I can't see it):** log in to Squarespace → **Settings → Domains** and confirm whether the domain renewal is billed as a separate line item from the website plan. That determines whether step 3 above is safe to do on its own. Tell me what you see and I'll confirm.

---

## 2. Cost

| | Squarespace today | After the move |
|---|---|---|
| Website software | ~$16–23/mo | **$0** |
| Hosting + SSL | included | **$0** (GitHub Pages) |
| Domain | ~$20/yr | ~$10–12/yr (Cloudflare, at cost) |
| **Total** | **~$220–300/yr** | **~$10–12/yr** |

---

## 3. Design: what was built and why

### Standards the page meets

- **WCAG 2.2 level AA** for colour contrast. This is the reason the page does *not* use Carolina Blue for text: `#4B9CD3` on white is only ~2.4:1, well under the 4.5:1 minimum. Carolina Blue is used as an *accent* (section rules, focus rings, hover) and the readable navy `#14568C` / `#13294B` carries the text and links. In dark mode, links shift to `#7CBDEA` (~8:1 on the dark navy background).
- **Semantic HTML** — real `<header>`, `<nav>`, `<main>`, `<section>`, `<footer>`; heading levels never skip; every section is `aria-labelledby` its own heading. This is what screen readers navigate by.
- **Keyboard accessible** — a "Skip to content" link, visible 3px focus rings on every interactive element, 44×44px minimum touch targets.
- **`prefers-color-scheme`** — follows the OS light/dark setting automatically, with a manual override button that persists in `localStorage`. Theme is applied *before first paint*, so there's no white flash on a dark-mode device.
- **`prefers-reduced-motion`** and **`prefers-contrast: more`** are both respected.
- **Progressive enhancement** — all 137 publications are in the HTML. If JavaScript fails, the page still reads perfectly; only the metric badges go away.
- **Semantic zoom** — everything is in `rem`, so browser text-zoom works properly.
- **Schema.org `Person` JSON-LD**, Open Graph tags, `sitemap.xml`, `robots.txt` — helps Google and academic indexers.
- **Print stylesheet** — prints as a clean CV-style bibliography.

### Browser support

Chrome, Safari, Edge, Firefox — current and ~2 versions back. Nothing exotic is used; `color-mix()` (the translucent nav bar) has a `@supports` fallback to a solid background, and `backdrop-filter` is prefixed for Safari. No build tooling, no frameworks, no polyfills.

### Your specific requests

| Request | Done |
|---|---|
| Remove name from top-left | ✅ nav is just the section links + theme toggle |
| Remove "A picture of…" and "Email" buttons | ✅ that button was a bug — the image's alt text was being parsed as a link |
| Profile links as links, not buttons | ✅ UNC on line 1; PubMed \| ORCID \| Google Scholar on line 2; email on line 3 — as on your current site |
| Photo top aligns with name, bottom with end of text | ✅ hero is a flexbox with `align-items: stretch`; the photo column spans exactly the text column's height |
| UNC colour palette | ✅ Carolina Blue + Navy, contrast-corrected (see above) |
| Previous support not bold | ✅ they were `####` headings in the scraped markdown; now a plain list |
| "Descriptive epidemiology…" title formatting | ✅ Squarespace had split it into two links mid-word (`Descr` + `iptive…`), the first pointing at the *wrong* paper. Merged and repointed. |
| Publications widen on large screens | ✅ container is now 1180px and the citation column is fluid |
| Remove per-year article counts | ✅ |
| Citation + Altmetric icons | ✅ see below |

I also fixed a typo carried over from Squarespace: "intramuscular vaccine administration**ran**" → "administration".

### The two metric icons

**Altmetric donut** — official `embed.js`, `data-badge-popover="right"`, `data-hide-no-mentions="true"` so a score of 0 renders nothing at all, exactly as you asked. Badges are keyed on PMID.

**Citation count** — the small bar-chart chip. Data comes from **OpenAlex**; clicking it opens Google Scholar for that title.

> Why not Google Scholar directly? Scholar has no public API and its terms prohibit scraping. No website can legitimately show live Scholar counts. OpenAlex is the standard open substitute. **Its numbers will read somewhat lower than Scholar's**, because Scholar also counts theses, slide decks, and grey literature. That's expected, not a bug.

**Being polite to OpenAlex.** OpenAlex throttles aggressively and will put a noisy client in a temporary penalty box, so the page is deliberately gentle:

- **batched** — up to 50 PMIDs per request (3 requests total, not 110)
- **polite pool** — `mailto=` is sent, which puts us in OpenAlex's higher-priority queue
- **spaced** — ≥1.1s between requests, strictly sequential, never parallel
- **cached** — results held in `localStorage` for 7 days, so a returning visitor makes *zero* API calls
- **fail-quiet** — on a 429 or any error it stops immediately and never retries. Badges just don't appear. The page never breaks.

Altmetric badges are lazy-loaded with an `IntersectionObserver` — a visitor who never scrolls to 2009 never fires those requests.

**Coverage: 134 of 137.** Publications in PubMed are keyed on PMID. The other 27 are keyed on **DOI** instead — most DOIs are read straight out of the article URL, and the handful that hide it (F1000Research, OSF preprints, NAP, Nature) live in `content/dois.tsv`. Only 3 items have no badge at all, because no DOI exists: the APA Handbook chapter, the OUP desk-reference chapter, and the PCORI report.

When you add a new paper, badges appear automatically as long as the entry links to PubMed or to a URL containing the DOI. If neither, add one line to `content/dois.tsv`.

---

## 4. Analytics

Not required, and nothing about the site depends on it. If you want traffic numbers, **Cloudflare Web Analytics** is the right choice for an academic site:

- Free, no cookies, no fingerprinting, no consent banner needed (so no GDPR exposure)
- One line of HTML
- Gives you pageviews, referrers, top pages, countries — which is all you'd actually look at

It's already wired into `build.py`. To turn it on: sign up at [cloudflare.com/web-analytics](https://www.cloudflare.com/web-analytics/), add your site, copy the token, and paste it into the `CLOUDFLARE_ANALYTICS_TOKEN` line near the top of `build.py`. Re-run the build. To keep analytics off, leave it empty — nothing is loaded.

Avoid Google Analytics here: it requires a cookie banner in the EU and gives you nothing useful that Cloudflare doesn't.

---

## 5. Templates and visual editors you could use

You asked whether there are template or visual-editor options. Honest answer: for a single-page academic site, they mostly add moving parts. But here are the real ones, in the order I'd consider them:

**Academic-specific themes (free, purpose-built for exactly this):**

- **al-folio** — the most widely used academic Jekyll theme; publications, news, CV, dark mode built in. Deploys to GitHub Pages in one click via "Use this template".
- **Hugo Academic / Wowchemy (now "HugoBlox")** — the biggest one. Very featureful, arguably too much for your needs.
- **Jekyll Minimal Mistakes** — general-purpose, extremely well documented.
- **Quarto** — if you ever want the site to build from `.qmd`/RMarkdown alongside your analyses, this is the natural academic choice. Renders publication lists straight from a `.bib` file.

If you like the idea of your publications living in a **BibTeX file** rather than markdown, Quarto or al-folio are genuinely worth a look — export `.bib` from Zotero, and the list regenerates itself.

**Visual editors on top of a static site (free tiers):**

- **Decap CMS** (formerly Netlify CMS) — bolts a WYSIWYG admin onto a Git repo at `/admin`. Free, open-source. Closest thing to the Squarespace feel.
- **Pages CMS** — newer, simpler, nicer UI, also free and Git-backed.
- **Publii** — a desktop app: edit visually on your Mac, click publish, it pushes static files to GitHub. No web admin to secure.

**My recommendation:** stay with what you have now. Your content is six plain markdown files and one `build.py`. That's less machinery than any theme, you own all of it, and nothing can deprecate under you. If you later find yourself wanting to edit visually without me, **Publii** or **Pages CMS** can be added on top without rebuilding anything.

---

## 6. Deploy to GitHub Pages

No terminal needed.

1. Create the repo. On GitHub: **New repository** → name it `Personal website`… actually name it **`personal-website`** (GitHub dislikes spaces). Make it **Public**.
2. **Add file → Upload files.** Drag in the *contents* of the `site/` folder — `index.html`, `CNAME`, `.nojekyll`, `robots.txt`, `sitemap.xml`, and the `images/` folder. Commit.
3. **Settings → Pages** → Source: *Deploy from a branch*, branch `main`, folder `/ (root)`. Save.
4. Under **Custom domain**, enter `www.evanmayo-wilson.org`. Save. Tick **Enforce HTTPS** once it appears (up to an hour).

Your site is immediately live at `https://<username>.github.io/personal-website/`, and at your real domain once DNS is repointed.

> Tip: if you name the repo `<your-username>.github.io` instead, it serves from the root with no subpath. Either works.

---

## 7. Repoint DNS

Your DNS is currently on Squarespace's NS1 nameservers. In **Squarespace → Settings → Domains → evanmayo-wilson.org → DNS Settings**, remove the existing A/CNAME records that point at Squarespace and add:

| Type | Host | Value |
|---|---|---|
| CNAME | `www` | `<your-username>.github.io` |
| A | `@` | `185.199.108.153` |
| A | `@` | `185.199.109.153` |
| A | `@` | `185.199.110.153` |
| A | `@` | `185.199.111.153` |

Check propagation at [dnschecker.org](https://dnschecker.org). Usually minutes.

**Only once `https://www.evanmayo-wilson.org` shows the new site — cancel the Squarespace website plan.**

---

## 8. (Optional) Move the registration off Squarespace

Worth ~$8–10/yr and it fully cuts the cord.

1. Sign up at [cloudflare.com](https://cloudflare.com), add `evanmayo-wilson.org` (free plan).
2. In Squarespace: **unlock** the domain (this clears `clientTransferProhibited`), disable WHOIS privacy temporarily, and request the **authorization / EPP code**.
3. Cloudflare → **Domain Registration → Transfer Domains** → paste the code.
4. Approve the confirmation email. ~5 days. The site stays up throughout.

Cloudflare Registrar sells at wholesale cost with no markup and no upsells. Your expiry (2027-05-28) carries over and gains a year.

---

## 9. Keeping the site updated

```
content/
  profile.md        name, photo, profile links, email
  bio.md            the two-sentence bio
  research.md       grants + previous support
  teaching.md
  service.md
  publications.md   all 137 papers, grouped by year
images/             your headshot
build.py            regenerates site/
site/               ← this is what gets uploaded to GitHub
```

**Easiest:** tell me. "Add this paper," "new grant," "update my bio" — I edit the markdown, rebuild, and push. Live in ~30 seconds.

**Yourself:** edit `content/publications.md` in GitHub's web editor, copying the shape of an existing entry, then run `python3 build.py`. New papers pick up citation and Altmetric badges automatically as long as the PubMed link is there.

**No lock-in.** It's one HTML file. Any host on earth will serve it.
