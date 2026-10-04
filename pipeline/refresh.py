"""Rebuild everything.

    python pipeline/refresh.py            # free tier: French totals/sectors, Yahoo x SEC companies
    python pipeline/refresh.py --wrds     # also (re)build from an existing data/wrds pull
    python pipeline/refresh.py --fresh    # drop cached downloads first (needed to pick up new months)

The WRDS pull itself is separate (it needs your login):  python pipeline/wrds_pull.py
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def run(script: str) -> None:
    print(f"\n==> {script}")
    subprocess.run([sys.executable, str(HERE / script)], check=True, cwd=HERE)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--wrds", action="store_true", help="build the company layer from data/wrds")
    ap.add_argument("--fresh", action="store_true", help="delete cached downloads first")
    a = ap.parse_args()
    if a.fresh:
        for p in (ROOT / "data" / "raw").glob("*"):          # keep the shelved SEC cover-page cache; everything else is re-downloaded
            if p.name != "sec_covers":
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink()
    run("master_build.py")
    run("01_totals_french.py")
    run("02_companies_free.py")                       # also fills the months after CRSP's last month when --wrds is used
    if a.wrds:
        wrds_dir = Path(os.environ.get("AEE_WRDS_DIR", ROOT / "data" / "wrds"))
        if not (wrds_dir / "caps.csv.gz").exists():
            sys.exit(f"no {wrds_dir / 'caps.csv.gz'} — run pipeline/wrds_pull.py first")
        run("wrds_build.py")
    run("04_build_dataset.py")
    print("\nOpen site/index.html (or serve the site/ folder).")
