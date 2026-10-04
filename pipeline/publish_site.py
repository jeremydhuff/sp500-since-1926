"""Publish the built site to GitHub Pages (the gh-pages branch).

    python pipeline/publish_site.py

The main branch stays code-only.  The gh-pages branch holds just the three files the page needs
(index.html, app.js, market.js), as a single fresh commit each time, so no data history builds up.

market.js contains CRSP-derived values from WRDS.  Only publish it if your institution's WRDS
Subscription Agreement allows displaying them publicly.  Build it first with
    python pipeline/refresh.py --fresh --wrds
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
FILES = ["index.html", "app.js", "market.js"]


def git(*args: str, cwd: Path, capture: bool = False) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=capture)
    return r.stdout.strip() if capture else ""


def main() -> None:
    missing = [f for f in FILES if not (SITE / f).exists()]
    if missing:
        sys.exit(f"missing {missing} in site/ - run: python pipeline/refresh.py --fresh --wrds")
    remote = git("remote", "get-url", "origin", cwd=ROOT, capture=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        for f in FILES:
            shutil.copy2(SITE / f, out / f)
        page = (out / "index.html").read_text(encoding="utf-8")
        for f in ("market.js", "app.js"):                         # new URL each publish, so browsers never serve stale data
            page = page.replace(f'src="{f}"', f'src="{f}?v={stamp}"')
        (out / "index.html").write_text(page, encoding="utf-8")
        (out / ".nojekyll").write_text("", encoding="utf-8")
        git("init", "-q", "-b", "gh-pages", cwd=out)
        git("config", "user.name", git("config", "user.name", cwd=ROOT, capture=True), cwd=out)
        git("config", "user.email", git("config", "user.email", cwd=ROOT, capture=True), cwd=out)
        git("add", "-A", cwd=out)
        git("commit", "-q", "-m", f"Publish site {stamp}", cwd=out)
        git("push", "-f", remote, "gh-pages", cwd=out)
    print("published to the gh-pages branch; GitHub Pages updates within a minute or two")


if __name__ == "__main__":
    main()
