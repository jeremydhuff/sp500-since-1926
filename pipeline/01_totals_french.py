"""Tier 0 — primary, free, complete: total US market cap, an S&P 500 proxy
topline, and sector shares, monthly from 1926.

Source: Kenneth French's Data Library (CRSP-derived).  The size-portfolio and
industry-portfolio files publish, for every month since 1926, the number of
firms and the average firm size (market equity) of each portfolio, so

    total cap = sum over portfolios of (number of firms x average firm size)

The S&P 500 proxy is the cap of the 500 largest firms, read off the size
deciles from the top down (the crossing decile is pro-rated at its average).
Checked against remembered S&P 500 aggregate caps (2000, 2008, 2021, 2024) it
lands within a few percent.  Replaced by actual S&P membership once CRSP
(crsp.dsp500list) is available.

Outputs
  data/derived/totals.csv   date, total_us_bn, sp500_proxy_bn, n_firms
  data/derived/sectors.csv  date, <12 sector columns>  (share of total US cap)
"""
from __future__ import annotations

import io

import pandas as pd

from common import DERIVED, RAW, get, unzip_first

BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
SIZE_DECILES_TOP_DOWN = ["Hi 10", "9-Dec", "8-Dec", "7-Dec", "6-Dec", "5-Dec", "4-Dec", "3-Dec", "2-Dec", "Lo 10"]
TOP_N = 500

SECTORS = {
    "NoDur": "Nondurables",
    "Durbl": "Durables",
    "Manuf": "Manufacturing",
    "Enrgy": "Energy",
    "Chems": "Chemicals",
    "BusEq": "Technology",
    "Telcm": "Telecom",
    "Utils": "Utilities",
    "Shops": "Retail",
    "Hlth": "Health care",
    "Money": "Finance",
    "Other": "Other",
}


def block(lines: list[str], title: str) -> pd.DataFrame:
    s = [i for i, l in enumerate(lines) if l.strip() == title][0]
    header = [c.strip() for c in lines[s + 1].split(",")]
    rows = []
    for l in lines[s + 2:]:
        if not l.split(",")[0].strip().isdigit():
            break
        rows.append(l)
    df = pd.read_csv(io.StringIO("\n".join(rows)), header=None, names=["ym"] + header[1:])
    return df.set_index("ym")


def load(name: str) -> list[str]:
    blob = get(BASE + name, cache=RAW / name)
    return unzip_first(blob).split("\n")


def top_n_cap(counts: pd.Series, sizes: pd.Series, n: int) -> float:
    taken, cap = 0.0, 0.0
    for col in SIZE_DECILES_TOP_DOWN:
        c, s = counts[col], sizes[col]
        if c <= 0 or s < 0:
            continue
        take = min(c, n - taken)
        cap += take * s
        taken += take
        if taken >= n:
            break
    return cap


def main() -> None:
    me = load("Portfolios_Formed_on_ME_CSV.zip")
    n, a = block(me, "Number of Firms in Portfolios"), block(me, "Average Firm Size")
    dec = SIZE_DECILES_TOP_DOWN
    total_mm = (n[dec] * a[dec]).sum(axis=1)  # $ millions
    top_mm = pd.Series({i: top_n_cap(n.loc[i], a.loc[i], TOP_N) for i in n.index})

    # French's size files report size at the *start* of each month (end of the
    # prior month): the row labelled 198711 is the market just after October
    # 1987.  Shift by one so each date means "month-end".
    idx = pd.to_datetime(n.index.astype(str), format="%Y%m") + pd.offsets.MonthEnd(0)
    tot = pd.DataFrame({
        "total_us_bn": total_mm.values / 1e3,
        "sp500_proxy_bn": top_mm.values / 1e3,
        "n_firms": n[dec].sum(axis=1).values,
    }, index=idx)
    tot.index = tot.index - pd.offsets.MonthEnd(1)  # row t describes end of t-1
    tot.index.name = "date"
    tot = tot.iloc[1:]  # first row described Dec-1925, which CRSP does not hold fully

    ind = load("12_Industry_Portfolios_CSV.zip")
    ni, ai = block(ind, "Number of Firms in Portfolios"), block(ind, "Average Firm Size")
    cap_i = (ni * ai.where(ai > 0, 0)).clip(lower=0)
    share = cap_i.div(cap_i.sum(axis=1), axis=0)
    share.index = pd.to_datetime(share.index.astype(str), format="%Y%m") + pd.offsets.MonthEnd(0) - pd.offsets.MonthEnd(1)
    share.index.name = "date"
    share = share.iloc[1:]

    tot.round(3).to_csv(DERIVED / "totals.csv")
    share.round(5).to_csv(DERIVED / "sectors.csv")
    last = tot.index[-1].date()
    print(f"totals.csv: {len(tot)} months, {tot.index[0].date()} -> {last}")
    for d in ["1957-03-31", "1973-11-30", "1987-09-30", "1987-10-31", "2000-03-31", "2008-12-31", "2021-12-31", "2024-12-31"]:
        r = tot.loc[d]
        print(f"  {d}: total ${r.total_us_bn/1e3:6.2f}T  S&P proxy ${r.sp500_proxy_bn/1e3:6.2f}T  ({r.sp500_proxy_bn/r.total_us_bn:.0%})")


if __name__ == "__main__":
    main()
