"""Assemble every available tier into site/market.js (what the page reads).

Tiers, best available wins:
  topline   data/derived/topline_wrds.csv  (CRSP, real S&P 500 membership)
            else totals.csv sp500_proxy_bn (top-500 by size, Ken French / CRSP-derived)
  companies data/derived/companies_wrds.csv   (CRSP)
            else companies_free.csv           (Yahoo price x SEC shares, 2009->)
  sectors   sectors.csv (Ken French 12 industries; share of all US market cap)

Run:  python pipeline/04_build_dataset.py
"""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd

from common import DATA, DERIVED, SITE
from master_build import SECTOR_HUE
from importlib import import_module

SECTORS = import_module("01_totals_french").SECTORS

EVENTS = [  # (YYYY-MM, label)
    ("1929-10", "1929 crash"), ("1932-06", "Depression trough"), ("1957-03", "S&P 500 launched"),
    ("1973-10", "Oil embargo"), ("1984-01", "AT&T breakup"), ("1987-10", "Black Monday"),
    ("2000-03", "Dot-com peak"), ("2008-09", "Lehman"), ("2020-03", "Covid"),
    ("2022-11", "ChatGPT"),
]


def r(a, nd):
    return [None if (x is None or (isinstance(x, float) and np.isnan(x))) else round(float(x), nd) for x in a]


def main() -> None:
    tot = pd.read_csv(DERIVED / "totals.csv", index_col=0, parse_dates=True)
    sec = pd.read_csv(DERIVED / "sectors.csv", index_col=0, parse_dates=True)
    idx = tot.index
    lab = [d.strftime("%Y-%m") for d in idx]

    # ---- topline
    top = tot["sp500_proxy_bn"].copy()
    top_kind = pd.Series("proxy", index=idx)
    wt = DERIVED / "topline_wrds.csv"
    if wt.exists():
        w = pd.read_csv(wt, parse_dates=["date"]).set_index("date")
        proxy = top.copy()
        top.loc[w.index.intersection(idx)] = w["topline_bn"]
        top_kind.loc[w.index.intersection(idx)] = w["universe"]
        crsp_last = w.index.intersection(idx).max()
        if crsp_last < idx[-1]:      # CRSP lags: carry the last member total forward at the proxy's growth
            later = idx > crsp_last
            top.loc[later] = proxy[later] * (top.loc[crsp_last] / proxy.loc[crsp_last])
    # ---- companies
    master = {m["id"]: m for m in json.loads((DATA / "companies.json").read_text(encoding="utf-8"))}
    cw, cf = DERIVED / "companies_wrds.csv", DERIVED / "companies_free.csv"
    comp_tier = "wrds" if cw.exists() else "calc"
    long = pd.read_csv(cw if cw.exists() else cf, parse_dates=["date"])
    if cw.exists() and cf.exists():  # months after the last CRSP month come from the free tier
        tail = pd.read_csv(cf, parse_dates=["date"])
        long = pd.concat([long, tail[tail["date"] > long["date"].max()]], ignore_index=True)
    piv = long.pivot_table(index="date", columns="id", values="cap_bn", aggfunc="sum").reindex(idx)

    # named slices may never exceed the topline; scale back if they do and say so
    s = piv.sum(axis=1)
    over = (s / top).where(s > top)
    if over.notna().any():
        print(f"named > topline in {int(over.notna().sum())} months (max x{over.max():.2f}); scaled back")
        piv = piv.mul(np.where(s > top, top / s, 1.0), axis=0)

    ids = [c for c in piv.columns if piv[c].notna().any()]
    comps, caps = [], {}
    for cid in ids:
        col = piv[cid]
        nz = np.flatnonzero(col.notna().values)
        a, b = int(nz[0]), int(nz[-1])
        vals = col.iloc[a:b + 1].fillna(0.0).tolist()
        m = master[cid]
        comps.append({"id": cid, "name": m["name"], "short": m["short"], "sector": m["sector"],
                      "color": m["color"], "start": a, "tier": comp_tier})
        caps[cid] = r(vals, 2)

    out = {
        "meta": {
            "built": datetime.now().strftime("%Y-%m-%d"),
            "companyTier": comp_tier,
            "toplineKinds": sorted(set(top_kind)),
            "crspLast": lab[idx.get_loc(crsp_last)] if (wt.exists() and crsp_last < idx[-1]) else None,
            "companyFrom": lab[min(c["start"] for c in comps)] if comps else None,
            "last": lab[-1],
        },
        "dates": lab,
        "topline": r(top.values, 2),
        "toplineKind": [{"proxy": 0, "top500": 1, "sp500": 2}[k] for k in top_kind],
        "totalUS": r(tot["total_us_bn"].values, 2),
        "sectors": [{"key": k, "name": SECTORS[k], "color": SECTOR_HUE[k],
                     "share": r(sec[k].reindex(idx).fillna(0).values, 4)} for k in SECTORS],
        "companies": comps,
        "caps": caps,
        "events": [{"d": d, "label": l} for d, l in EVENTS if d in lab],
    }
    js = "window.MARKET = " + json.dumps(out, separators=(",", ":")) + ";\n"
    (SITE / "market.js").write_text(js, encoding="utf-8")
    print(f"site/market.js  {len(js)/1e3:.0f} kB  months={len(lab)}  companies={len(comps)}  tier={comp_tier}")
    if comp_tier == "wrds":
        print("NOTE: market.js now holds CRSP-derived company values. Before publishing it, confirm your\n"
              "      institution's WRDS Subscription Agreement allows it (academic, non-commercial use only).")


if __name__ == "__main__":
    main()
