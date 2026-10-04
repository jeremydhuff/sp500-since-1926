"""Tier 2 — pull CRSP from WRDS.  Run this once your WRDS account is active.

    pip install wrds pandas
    python pipeline/wrds_pull.py --inspect     # 1. confirm table + column names
    python pipeline/wrds_pull.py               # 2. pull (about 5-15 minutes)
    python pipeline/wrds_build.py              # 3. turn the pull into the app's dataset
    python pipeline/04_build_dataset.py        # 4. rebuild site/market.js

First connection is interactive: it asks for your WRDS username/password and
offers to store them in ~/.pgpass (Windows: %APPDATA%\\postgresql\\pgpass.conf).
Set WRDS_USERNAME to skip the username prompt.  Duo two-factor, if your
institution requires it, is approved on your phone during that first connect.

CRSP changed formats in 2024.  WRDS serves two generations of tables:
  legacy (SIZ):  crsp.msf, crsp.msenames, crsp.dsp500list
  current (CIZ): crsp.msf_v2, crsp.stksecurityinfohist, crsp.dsp500list_v2
The script detects which exists and prefers CIZ.  Everything format-specific
sits in FLAVORS below so a column-name surprise is a one-line fix.

Outputs (data/wrds/):
  caps.csv.gz      permno, permco, date, cap_bn          monthly, common stock only
  names.csv.gz     permno, permco, start, end, name, ticker
  sp500.csv.gz     permno, start, end                    S&P 500 membership spells

WRDS Terms of Use (last updated 2026-08-25) — what this script does to stay inside them
  * Access is by the `wrds` Python package, a remote database connection (an allowed
    method).  It never logs in to or scrapes the website, and never automates web queries.
  * Credentials: only you type them, at the first interactive connect.  They are never
    read from, written to, or printed into this project.  Do not share them with anyone.
  * Academic, non-commercial use only; the terms are re-accepted annually, and so is the
    confirmation below (a human must answer it, so unattended runs stop).
  * It prints schema and row counts only, never rows, so nothing licensed is echoed into
    logs or into an AI assistant's context.  WRDS has a separate AI policy; read it before
    letting any tool see query output.
  * The pull is saved to WRDS_DIR.  Refuses to write inside OneDrive/Dropbox/iCloud/Google
    Drive unless AEE_WRDS_DIR points elsewhere (WRDS asks you to secure downloaded data).
  * Redistribution is governed by your institution's Subscription Agreement, not by this
    code.  site/market.js is derived output; check that agreement before publishing it.
  * Publications must carry the WRDS citation; app.js adds it to the page in the WRDS build.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import WRDS_DIR  # noqa: E402

FIRST_YEAR = 1925
LAST_YEAR = pd.Timestamp.today().year

FLAVORS = {
    "ciz": {
        "tables": ["msf_v2", "stksecurityinfohist", "dsp500list_v2"],
        # shares outstanding (shrout) is in thousands; mthcap is in $ thousands
        "caps_sql": """
            select m.permno, m.permco, m.mthcaldt as date, m.mthcap as cap_k
            from crsp.msf_v2 as m
            join crsp.stksecurityinfohist as s
              on m.permno = s.permno
             and m.mthcaldt between s.secinfostartdt and s.secinfoenddt
            where m.mthcaldt between '{a}-01-01' and '{b}-12-31'
              and s.sharetype = 'NS' and s.securitytype = 'EQTY'
              and s.securitysubtype = 'COM' and s.usincflg = 'Y'
              and s.issuertype in ('ACOR', 'CORP')
              and m.mthcap is not null and m.mthcap > 0
        """,
        "cap_divisor": 1e6,   # $ thousands -> $ billions
        "names_sql": """
            select permno, permco, secinfostartdt as start, secinfoenddt as "end",
                   issuernm as name, ticker
            from crsp.stksecurityinfohist
        """,
        "sp500_sql": "select permno, mbrstartdt as start, mbrenddt as \"end\" from crsp.dsp500list_v2",
    },
    "siz": {
        "tables": ["msf", "msenames", "dsp500list"],
        # prc may be negative (bid/ask midpoint); shrout is in thousands
        "caps_sql": """
            select a.permno, a.permco, a.date, abs(a.prc) * a.shrout as cap_k
            from crsp.msf as a
            join crsp.msenames as b
              on a.permno = b.permno and a.date between b.namedt and b.nameendt
            where a.date between '{a}-01-01' and '{b}-12-31'
              and b.shrcd in (10, 11)
              and a.prc is not null and a.shrout > 0
        """,
        "cap_divisor": 1e6,   # (price $ x shares thousands) -> $ thousands -> $ billions
        "names_sql": """
            select permno, permco, namedt as start, nameenddt as "end",
                   comnam as name, ticker
            from crsp.msenames
        """,
        "sp500_sql": "select permno, start, ending as \"end\" from crsp.dsp500list",
    },
}


CLOUD_FOLDERS = ("onedrive", "dropbox", "icloud", "google drive", "googledrive", "box sync")
ACK_FILE = WRDS_DIR / ".terms_ack"
ACK_DAYS = 365          # WRDS prompts for its terms annually; so do we


def guard_storage() -> None:
    p = str(WRDS_DIR.resolve()).lower()
    hit = next((c for c in CLOUD_FOLDERS if c in p), None)
    if hit:
        raise SystemExit(
            f"Refusing to save licensed WRDS data under a cloud-synced folder ({WRDS_DIR}).\n"
            "Set AEE_WRDS_DIR to a local folder outside it, e.g.\n"
            "  PowerShell:  $env:AEE_WRDS_DIR = 'C:\\wrds_data'\n"
            "then re-run."
        )


def confirm_terms() -> None:
    """A person must confirm academic use before data is pulled; valid for a year."""
    if ACK_FILE.exists():
        try:
            when = dt.date.fromisoformat(ACK_FILE.read_text().strip())
            if (dt.date.today() - when).days < ACK_DAYS:
                return
        except ValueError:
            pass
    if not sys.stdin.isatty():
        raise SystemExit("Run this yourself in a terminal: it asks you to confirm the WRDS terms.")
    print("Before pulling WRDS data, confirm that:\n"
          "  1. this is academic, non-commercial research through your own WRDS account;\n"
          "  2. you have read the WRDS AI policy and will not feed licensed data to an AI tool against it;\n"
          "  3. you will not publish licensed data beyond what your Subscription Agreement allows;\n"
          "  4. you will cite WRDS in anything you publish.")
    if input("Type 'yes' to continue: ").strip().lower() != "yes":
        raise SystemExit("Not confirmed; nothing pulled.")
    ACK_FILE.write_text(dt.date.today().isoformat())


def connect():
    import wrds
    user = os.environ.get("WRDS_USERNAME")
    return wrds.Connection(wrds_username=user) if user else wrds.Connection()


def detect(db) -> str:
    have = set(db.list_tables(library="crsp"))
    for name in ("ciz", "siz"):
        if all(t in have for t in FLAVORS[name]["tables"]):
            return name
    raise SystemExit(
        "Neither CRSP table family found.  Run with --inspect and check that your "
        "subscription includes CRSP Stock/Security Files (crsp.msf_v2 or crsp.msf)."
    )


def inspect(db) -> None:
    tables = sorted(db.list_tables(library="crsp"))
    print(f"{len(tables)} tables in crsp, e.g.: {tables[:15]}")
    flavor = detect(db)
    print(f"-> using flavor: {flavor}")
    for t in FLAVORS[flavor]["tables"]:
        d = db.describe_table(library="crsp", table=t)
        print(f"\ncrsp.{t}: {len(d)} columns")
        print(d[["name", "type"]].to_string(index=False))


def pull(db) -> None:
    flavor = detect(db)
    f = FLAVORS[flavor]
    print(f"flavor: {flavor}")

    parts = []
    for a in range(FIRST_YEAR, LAST_YEAR + 1, 5):          # chunk to stay inside server limits
        b = min(a + 4, LAST_YEAR)
        df = db.raw_sql(f["caps_sql"].format(a=a, b=b), date_cols=["date"])
        df["cap_bn"] = df["cap_k"] / f["cap_divisor"]
        parts.append(df[["permno", "permco", "date", "cap_bn"]])
        print(f"  caps {a}-{b}: {len(df):,} rows")
    caps = pd.concat(parts, ignore_index=True)
    caps["permno"] = caps["permno"].astype("int64")
    caps["permco"] = caps["permco"].astype("int64")
    caps.to_csv(WRDS_DIR / "caps.csv.gz", index=False)

    names = db.raw_sql(f["names_sql"], date_cols=["start", "end"])
    names.to_csv(WRDS_DIR / "names.csv.gz", index=False)
    sp = db.raw_sql(f["sp500_sql"], date_cols=["start", "end"])
    sp.to_csv(WRDS_DIR / "sp500.csv.gz", index=False)
    print(f"caps {len(caps):,} rows, {caps['date'].min().date()} -> {caps['date'].max().date()}; "
          f"names {len(names):,}; sp500 spells {len(sp):,}")
    print("next: python pipeline/wrds_build.py")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--inspect", action="store_true", help="list CRSP tables/columns and exit")
    args = ap.parse_args()
    guard_storage()
    confirm_terms()
    conn = connect()
    try:
        inspect(conn) if args.inspect else pull(conn)
    finally:
        conn.close()
