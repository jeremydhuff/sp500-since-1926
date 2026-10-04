"""Turn the raw CRSP pull (data/wrds/*.csv.gz) into the app's company layer.

Method
  * cap is summed to the PERMCO (company) level, so multi-class issuers such as
    Alphabet or Berkshire are one slice, and name changes (Standard Oil NJ ->
    Exxon -> ExxonMobil) stay one continuous company.
  * a PERMCO is mapped to a display company by testing the regexes in
    data/companies.json against every name it has ever had (first match wins).
  * the index universe is the actual S&P 500 membership (crsp dsp500list) from
    SP500_START onward.  Before that date the index did not exist; the universe
    is the 500 largest companies by cap, the same proxy the topline uses today.
  * a company's band counts only while it is an index member, so the named
    slices always sum to at most the topline.

Outputs
  data/derived/companies_wrds.csv   date, id, cap_bn
  data/derived/topline_wrds.csv     date, topline_bn, n_members, universe
  data/derived/wrds_unmapped.csv    large companies with no master entry yet —
                                    add them to pipeline/master_build.py and rerun
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd

from common import DATA, DERIVED, WRDS_DIR

SP500_START = pd.Timestamp("1957-03-31")   # S&P 500 launched 4 March 1957
TOP_PRE_INDEX = 500
UNMAPPED_TOP_RANK = 30                      # report unmapped firms that ever rank this high


def month_end(s: pd.Series) -> pd.Series:
    return s.dt.to_period("M").dt.to_timestamp("M")


def main() -> None:
    caps = pd.read_csv(WRDS_DIR / "caps.csv.gz", parse_dates=["date"])
    names = pd.read_csv(WRDS_DIR / "names.csv.gz", parse_dates=["start", "end"])
    sp = pd.read_csv(WRDS_DIR / "sp500.csv.gz", parse_dates=["start", "end"])
    master = json.loads((DATA / "companies.json").read_text(encoding="utf-8"))

    caps["date"] = month_end(caps["date"])
    caps = caps.sort_values(["permno", "date"]).drop_duplicates(["permno", "date"], keep="last")

    # ---- S&P membership by permno-month
    sp["end"] = sp["end"].fillna(pd.Timestamp("2262-01-01"))
    months = pd.DatetimeIndex(sorted(caps["date"].unique()))
    member = []
    for r in sp.itertuples():
        d = months[(months >= r.start) & (months <= r.end)]
        if len(d):
            member.append(pd.DataFrame({"permno": r.permno, "date": d}))
    member = pd.concat(member).drop_duplicates()
    member["in_sp"] = True
    caps = caps.merge(member, on=["permno", "date"], how="left")
    caps["in_sp"] = caps["in_sp"].fillna(False)

    # ---- permco -> display id
    hist = names.groupby("permco")["name"].agg(lambda s: " | ".join(sorted(set(map(str, s)))).upper())
    pats = [(m["id"], re.compile(m["match"])) for m in master if m.get("match")]
    mapping = {}
    for permco, allnames in hist.items():
        for cid, rx in pats:
            if any(rx.search(n.strip()) for n in allnames.split(" | ")):
                mapping[permco] = cid
                break
    caps["id"] = caps["permco"].map(mapping)

    # ---- universe: actual S&P members from 1957, top-500 by company cap before
    co = caps.groupby(["permco", "date"], as_index=False).agg(cap_bn=("cap_bn", "sum"), any_sp=("in_sp", "max"))
    co["rank"] = co.groupby("date")["cap_bn"].rank(ascending=False, method="first")
    pre = co["date"] < SP500_START
    co["in_universe"] = np.where(pre, co["rank"] <= TOP_PRE_INDEX, co["any_sp"])
    caps = caps.merge(co[["permco", "date", "in_universe", "rank"]], on=["permco", "date"], how="left")
    # a class not itself in the index does not count after 1957
    caps["counted"] = np.where(caps["date"] < SP500_START, caps["in_universe"], caps["in_sp"])

    top = (caps[caps["counted"]].groupby("date")
           .agg(topline_bn=("cap_bn", "sum"), n_members=("permno", "nunique")).reset_index())
    top["universe"] = np.where(top["date"] < SP500_START, "top500", "sp500")
    top.to_csv(DERIVED / "topline_wrds.csv", index=False)

    named = (caps[caps["counted"] & caps["id"].notna()]
             .groupby(["date", "id"], as_index=False)["cap_bn"].sum())
    named["cap_bn"] = named["cap_bn"].round(3)
    named.to_csv(DERIVED / "companies_wrds.csv", index=False)

    # ---- who is big but unmapped?
    un = co[(co["rank"] <= UNMAPPED_TOP_RANK) & (~co["permco"].isin(mapping))]
    rep = (un.groupby("permco").agg(first=("date", "min"), last=("date", "max"),
                                    months_in_top=("date", "count"), peak_bn=("cap_bn", "max"))
           .join(hist.rename("names")).sort_values("peak_bn", ascending=False).reset_index())
    rep["names"] = rep["names"].str.slice(0, 120)
    rep.to_csv(DERIVED / "wrds_unmapped.csv", index=False)

    print(f"topline: {len(top)} months  {top.date.min().date()} -> {top.date.max().date()}")
    print(f"named companies: {named['id'].nunique()}  mapped permcos: {len(mapping)}")
    print(f"unmapped big companies: {len(rep)} -> data/derived/wrds_unmapped.csv")
    cover = (named.groupby("date")["cap_bn"].sum() / top.set_index("date")["topline_bn"]).dropna()
    print("named share of topline, median by decade:")
    print(cover.groupby(cover.index.year // 10 * 10).median().round(2).to_string())


if __name__ == "__main__":
    main()
