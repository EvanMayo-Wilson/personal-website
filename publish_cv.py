"""Put an approved public CV on the site: docs/cv.pdf plus a cache-busting version in docs/cv/index.html.

Usage: python3.14 publish_cv.py [path/to/CV public_YYYYMMDD.docx] [--push]
Default source: the newest "CV public_<date>.docx" in ~/My Drive/CV/ (cv-and-biosketch's approved clean export).
--push commits docs/cv.pdf and docs/cv/index.html (only those) and pushes main.

Why the version stamp (Evan, 2026-11-12: "Whenever I approve a public CV, I want it to replace the old version on the
website"): GitHub Pages/Cloudflare send cv.pdf with max-age=14400, so a browser kept showing the previous CV for up to
4 hours after a push. The viewer page (max-age=600) now asks for cv.pdf?v=<sha256[:10]>, a new URL for every new PDF.
cv-and-biosketch's export_drive.py runs this with --push after `--clean ... "CV public"`.
"""
import glob, hashlib, os, re, shutil, subprocess, sys, tempfile

SITE = os.path.dirname(os.path.abspath(__file__))
SOFFICE = shutil.which("soffice") or "/Applications/LibreOffice.app/Contents/MacOS/soffice"
args = [a for a in sys.argv[1:] if a != "--push"]; push = "--push" in sys.argv[1:]
if args:
    src = args[0]
else:
    cands = sorted(glob.glob(os.path.expanduser("~/My Drive/CV/CV public_[0-9]*.docx")))
    assert cands, "no CV public_<date>.docx in ~/My Drive/CV"
    src = cands[-1]
assert os.path.basename(src).startswith("CV public_"), f"not a public CV: {src}"
tmp = tempfile.mkdtemp(prefix="publish-cv-")
subprocess.run([SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", tmp, src], check=True, capture_output=True)
pdf = os.path.join(tmp, os.path.splitext(os.path.basename(src))[0] + ".pdf")
assert os.path.getsize(pdf) > 50_000, pdf
dst = os.path.join(SITE, "docs/cv.pdf")
shutil.copyfile(pdf, dst)
ver = hashlib.sha256(open(dst, "rb").read()).hexdigest()[:10]

page = os.path.join(SITE, "docs/cv/index.html")
html = open(page).read()
new, n = re.subn(r'\.\./cv\.pdf(?:\?v=[0-9a-f]+)?', f"../cv.pdf?v={ver}", html)
assert n >= 3, f"expected 3+ cv.pdf references in {page}, found {n}"
open(page, "w").write(new)
print(f"docs/cv.pdf <- {os.path.basename(src)} (v={ver}); {n} references stamped")

if push:
    g = ["git", "-C", SITE]
    subprocess.run(g + ["pull", "--no-rebase", "-q"], check=True)
    subprocess.run(g + ["add", "docs/cv.pdf", "docs/cv/index.html"], check=True)
    if subprocess.run(g + ["diff", "--cached", "--quiet"]).returncode == 0:
        print("site already has this CV; nothing to commit"); sys.exit(0)
    msg = (f"cv.pdf from {os.path.basename(src)} (v={ver})\n\n"
           "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
    subprocess.run(g + ["commit", "-q", "-m", msg, "--", "docs/cv.pdf", "docs/cv/index.html"], check=True)
    subprocess.run(g + ["push", "-q"], check=True)
    print("pushed")
