"""Runs wrds_build.py against the synthetic fixture and asserts the expected behaviour.

    python pipeline/tests/check_wrds_fixture.py
Exit code 0 = pass.  Safe to run any time; it only touches data/_fixture.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "data" / "_fixture"
env = dict(os.environ, AEE_DATA_DIR=str(FIX))
subprocess.run([sys.executable, str(ROOT / "pipeline" / "tests" / "make_wrds_fixture.py")], check=True)
subprocess.run([sys.executable, str(ROOT / "pipeline" / "wrds_build.py")], check=True, env=env, cwd=ROOT / "pipeline")

top = pd.read_csv(FIX / "derived" / "topline_wrds.csv", parse_dates=["date"]).set_index("date")
co = pd.read_csv(FIX / "derived" / "companies_wrds.csv", parse_dates=["date"])
un = pd.read_csv(FIX / "derived" / "wrds_unmapped.csv")

assert (top.loc[:"1957-02-28", "universe"] == "top500").all(), "pre-index universe should be top500"
assert (top.loc["1957-03-31":, "universe"] == "sp500").all(), "post-launch universe should be sp500"
m = co[co.date == "1957-03-31"].set_index("id")["cap_bn"]
assert abs(m["exxon"] - 114.0) < 0.01, "only the member share class (permno 10) should count for Exxon"
assert abs(top.loc["1957-03-31", "topline_bn"] - (m["exxon"] + m["gm"] + m["mobil"])) < 0.01, "topline = sum of members"
assert "mobil" not in set(co[co.date >= "1959-07-31"]["id"]), "Mobil leaves the index in mid-1959"
assert list(un["permco"]) == [4], "ACME is large, unmapped, and should be reported"
print("wrds_build fixture: all checks passed")
