"""Builds a tiny synthetic CRSP-shaped dataset so wrds_build.py can be tested without WRDS access.

    python pipeline/tests/make_wrds_fixture.py            # writes to <repo>/data/_fixture
    set AEE_DATA_DIR=<repo>\\data\\_fixture
    python pipeline/wrds_build.py                          # reads/writes under the fixture folder only
    python pipeline/tests/check_wrds_fixture.py            # asserts the behaviour below

What the fixture encodes (so a regression is obvious):
  * permco 1 (Standard Oil NJ) has two share classes; only permno 10 is an S&P member
  * permco 2 (Mobil) leaves the index in June 1959
  * permco 4 (ACME) never joins the index and matches no display company
  * before March 1957 the universe is the top 500 by size; afterwards, actual members only
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FIX = Path(os.environ.get("AEE_FIXTURE_DIR", ROOT / "data" / "_fixture"))


def main() -> None:
    (FIX / "wrds").mkdir(parents=True, exist_ok=True)
    (FIX / "derived").mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "data" / "companies.json", FIX / "companies.json")
    months = pd.date_range("1956-01-31", "1960-12-31", freq="ME")
    spec = {1: 100, 2: 60, 3: 150, 4: 5}              # permco -> base cap, $bn
    rows = []
    for permco, base in spec.items():
        for i, m in enumerate(months):
            rows.append((permco * 10, permco, m + pd.Timedelta(days=-1 if i % 2 else 0), base * (1 + 0.01 * i)))
    rows += [(11, 1, m, 10.0) for m in months]        # second share class of permco 1
    pd.DataFrame(rows, columns=["permno", "permco", "date", "cap_bn"]).to_csv(FIX / "wrds" / "caps.csv.gz", index=False)
    pd.DataFrame([
        (10, 1, "1950-01-01", "1990-01-01", "STANDARD OIL CO N J", "ESO"),
        (11, 1, "1950-01-01", "1990-01-01", "STANDARD OIL CO N J", "ESO.B"),
        (20, 2, "1950-01-01", "1990-01-01", "SOCONY MOBIL OIL INC", "MOB"),
        (30, 3, "1950-01-01", "1990-01-01", "GENERAL MOTORS CORP", "GM"),
        (40, 4, "1950-01-01", "1990-01-01", "ACME CORP", "ACM"),
    ], columns=["permno", "permco", "start", "end", "name", "ticker"]).to_csv(FIX / "wrds" / "names.csv.gz", index=False)
    pd.DataFrame([(10, "1957-03-04", None), (20, "1957-03-04", "1959-06-30"), (30, "1957-03-04", None)],
                 columns=["permno", "start", "end"]).to_csv(FIX / "wrds" / "sp500.csv.gz", index=False)
    print("fixture written to", FIX)


if __name__ == "__main__":
    main()
