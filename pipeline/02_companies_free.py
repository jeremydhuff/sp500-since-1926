"""Tier 1 — free company layer: month-end market cap = price x shares outstanding.

Prices : Yahoo Finance chart API, monthly, split-adjusted (not dividend-adjusted).
Shares : SEC XBRL cover-page counts (dei:EntityCommonStockSharesOutstanding)
         from data.sec.gov, which exist from mid-2009.  Counts are restated to
         the split-adjusted basis of the price series, then linearly
         interpolated between filings.

Limits (by design, all fixed by CRSP later):
  * only companies that still trade today (Yahoo has no delisted tickers),
  * only 2009 onward (before that there are no machine-readable share counts),
  * multi-class issuers use a share rule (see universe_free.csv).

Output: data/derived/companies_free.csv  date,id,cap_bn
        data/derived/free_report.csv     one QC row per company
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd

from common import DERIVED, RAW, ROOT, get, sec_headers

UNIVERSE = pd.read_csv(ROOT / "pipeline" / "universe_free.csv")
LAST_MONTH = pd.read_csv(DERIVED / "totals.csv", index_col=0, parse_dates=True).index[-1]


# ---------------------------------------------------------------- prices
def yahoo_monthly(ticker: str) -> tuple[pd.Series, pd.Series, list[tuple[pd.Timestamp, float]]]:
    """Month-end closes (split-adjusted) built from Yahoo's *daily* bars.  Both
    range=max and interval=1mo silently degrade to quarterly bars, so the window
    is requested explicitly with period1/period2."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    import time as _t
    blob = get(url, params={"period1": -1262304000, "period2": int(_t.time()) + 86400,
                            "interval": "1d", "events": "split"},
               cache=RAW / "yahoo" / f"{ticker}.json", pause=0.25)
    res = json.loads(blob)["chart"]["result"][0]
    day = pd.to_datetime(res["timestamp"], unit="s").normalize()
    q = pd.Series(res["indicators"]["quote"][0]["close"], index=day, dtype="float64").dropna()
    q = q[~q.index.duplicated(keep="last")]
    close = q.groupby(q.index.to_period("M")).last()
    close.index = close.index.to_timestamp("M")
    adj_raw = res["indicators"].get("adjclose", [{}])[0].get("adjclose")
    adj = pd.Series(adj_raw, index=day, dtype="float64").dropna() if adj_raw else pd.Series(dtype=float)
    adj = adj[~adj.index.duplicated(keep="last")]
    adj = adj.groupby(adj.index.to_period("M")).last() if len(adj) else adj
    if len(adj):
        adj.index = adj.index.to_timestamp("M")
    splits = []
    for s_ in (res.get("events", {}).get("splits", {}) or {}).values():
        splits.append((pd.to_datetime(s_["date"], unit="s"), s_["numerator"] / s_["denominator"]))
    return close, adj, sorted(splits)


# ---------------------------------------------------------------- shares
SHARE_TAGS = (
    ("dei", "EntityCommonStockSharesOutstanding", "cover"),
    ("us-gaap", "CommonStockSharesOutstanding", "instant"),
    ("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic", "avg"),
)


def sec_candidates(cik: int) -> dict[str, pd.DataFrame]:
    """Every usable share-count series for one CIK, keyed by tag.  Each frame
    has columns date, val, filed (one row per anchor date, latest filing wins)."""
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
    blob = get(url, headers=sec_headers(), cache=RAW / "sec" / f"CIK{cik:010d}.json", pause=0.15)
    facts = json.loads(blob)["facts"]
    out = {}
    for tax, tag, kind in SHARE_TAGS:
        recs = []
        for u in facts.get(tax, {}).get(tag, {}).get("units", {}).get("shares", []):
            if not u.get("form", "").startswith(("10-K", "10-Q")):
                continue
            end = pd.Timestamp(u["end"])
            if kind == "avg":
                if "start" not in u:
                    continue
                start = pd.Timestamp(u["start"])
                days = (end - start).days
                if not 80 <= days <= 100:        # quarterly averages only
                    continue
                date = start + (end - start) / 2   # centre of the period
            else:
                date = end
            recs.append((date, u["accn"], u["val"], pd.Timestamp(u["filed"])))
        if recs:
            out[tag] = pd.DataFrame(recs, columns=["date", "accn", "val", "filed"])
    return out


def to_series(df: pd.DataFrame, tag: str, rule: str) -> pd.DataFrame:
    """One anchor per date, as originally reported (later filings restate onto a
    different split basis, so the earliest filing is the consistent one).  The
    dei cover tag can list several classes per filing; the rest are totals."""
    first = df.sort_values("filed")
    if tag == "EntityCommonStockSharesOutstanding":
        first = first[first["accn"] == first.groupby("date")["accn"].transform("first")]
        first = first.drop_duplicates(["date", "val"])
        g = first.groupby("date").agg(val=("val", "sum"), filed=("filed", "first"))
    else:
        g = first.drop_duplicates("date", keep="first").set_index("date")[["val", "filed"]]
    g["val"] = g["val"].astype(float)
    return g.sort_index()


def best_series(ciks: list[int], rule: str) -> tuple[pd.DataFrame, str]:
    """Prefer the cover count; fall back to whichever tag has the densest
    coverage from 2009 on."""
    cands: dict[str, list[pd.DataFrame]] = defaultdict(list)
    for cik in ciks:
        try:
            for tag, df in sec_candidates(cik).items():
                cands[tag].append(to_series(df, tag, rule))
        except RuntimeError:
            continue
    best, best_tag, best_n = None, "", -1
    for _, tag, _ in SHARE_TAGS:
        if tag not in cands:
            continue
        s = pd.concat(cands[tag]).sort_index()
        s = s[~s.index.duplicated(keep="last")]
        s = s[s.index >= "2009-01-01"]
        # the cover tag wins unless another tag has at least 1.5x as many anchors
        n = len(s) * (1.5 if tag != "EntityCommonStockSharesOutstanding" else 1.0)
        if n > best_n and len(s):
            best, best_tag, best_n = s, tag, n
    return (best if best is not None else pd.DataFrame(columns=["val", "filed"])), best_tag


def clean_anchors(v: pd.Series) -> tuple[pd.Series, list[str]]:
    """Repair unit-scale slips (a count tagged in thousands or millions).  Real
    share counts never move 250x, so a wide window's median is a safe yardstick
    even when several neighbouring filings are wrong.  Anything subtler is left
    alone and surfaces in the QC report rather than being 'fixed' silently."""
    notes: list[str] = []
    v = v[(v > 0) & v.notna()].copy()      # zero / missing counts are not usable anchors
    for _ in range(2):
        for i in range(len(v)):
            nb = v.iloc[[j for j in range(max(0, i - 6), min(len(v), i + 7)) if j != i]]
            if nb.empty:
                continue
            ref = float(nb.median())
            lr = np.log10(v.iloc[i] / ref) if ref > 0 else 0.0
            if not np.isfinite(lr) or abs(lr) < 2.4:
                continue
            k = 10.0 ** (-3 * round(lr / 3))
            if 0.3 <= v.iloc[i] * k / ref <= 3.3:
                notes.append(f"{v.index[i].date()} x{k:g}")
                v.iloc[i] *= k
    return v, notes


_SESSION = None


def yahoo_live(tickers: list[str]) -> dict[str, tuple[float, float]]:
    """Current (market cap $, price) per ticker, via Yahoo's quote endpoint."""
    global _SESSION
    import requests
    cache = RAW / "yahoo_live.json"
    if cache.exists():
        return {k: tuple(v) for k, v in json.loads(cache.read_text()).items()}
    s = requests.Session(); s.headers["User-Agent"] = "Mozilla/5.0"
    s.get("https://fc.yahoo.com", timeout=20)
    crumb = s.get("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=20).text
    out = {}
    for i in range(0, len(tickers), 40):
        r = s.get("https://query1.finance.yahoo.com/v7/finance/quote",
                  params={"symbols": ",".join(tickers[i:i + 40]), "crumb": crumb}, timeout=30)
        for x in r.json()["quoteResponse"]["result"]:
            if x.get("marketCap") and x.get("regularMarketPrice"):
                out[x["symbol"]] = (float(x["marketCap"]), float(x["regularMarketPrice"]))
    cache.write_text(json.dumps(out))
    return out


def split_factor_after(date: pd.Timestamp, splits) -> float:
    f = 1.0
    for d, r in splits:
        if d > date:
            f *= r
    return f


def cover_anchors(ciks: list[int], splits, base: pd.Series) -> tuple[pd.Series, int, int]:
    """Share counts from pre-XBRL cover pages (02b_sec_covers.py), on today's split
    basis.  A filing lists several large numbers; the share count is the one (or
    the sum of two or three, for multi-class issuers) closest to what we already
    know from XBRL, and later the one closest to its neighbours.  Anything that
    still disagrees is dropped, never forced."""
    from itertools import combinations
    folder = RAW / "sec_covers"
    recs = []
    for f in folder.glob("*.json") if folder.exists() else []:
        r = json.loads(f.read_text(encoding="utf-8"))
        if r["cik"] in ciks and r.get("cands"):
            d = pd.Timestamp(r["report"] or r["filed"])
            filed = pd.Timestamp(r["filed"])
            fac = split_factor_after(filed, splits)
            c = [v * fac for v in r["cands"][:6]]
            opts = list(c) + [a + b for a, b in combinations(c, 2)] + [a + b + d_ for a, b, d_ in combinations(c, 3)]
            recs.append((d, opts))
    if not recs or base.empty:
        return pd.Series(dtype=float), len(recs), 0
    recs.sort(key=lambda t: t[0])
    ref0 = float(base.iloc[0])
    acc: dict[pd.Timestamp, float] = {}
    for d, opts in recs:                                     # pass 1: against the XBRL anchor
        best = min(opts, key=lambda v: abs(np.log(v / ref0)))
        if 0.2 <= best / ref0 <= 5:
            acc[d] = best
    for lo, hi in ((0.6, 1.7), (0.75, 1.35)):                # passes 2-3: against neighbours
        s_acc = pd.Series(acc).sort_index()
        nxt: dict[pd.Timestamp, float] = {}
        for d, opts in recs:
            others = s_acc.drop(d, errors="ignore")
            if len(others) < 3:
                continue
            near = others.iloc[np.argsort(np.abs((others.index - d).days.values))[:6]]
            ref = float(np.median(near.values))
            best = min(opts, key=lambda v: abs(np.log(v / ref)))
            if lo <= best / ref <= hi:
                nxt[d] = best
        acc = nxt
    out = pd.Series(acc).sort_index()
    if len(out):
        out.index = out.index.to_period("M").to_timestamp("M")
        out = out[~out.index.duplicated(keep="last")]
    return out, len(recs), len(out)


def build_company(row, live) -> tuple[pd.Series, dict]:
    close, adj, splits = yahoo_monthly(row.yahoo)
    adj = adj[~adj.index.duplicated(keep="last")]
    sh, tag = best_series([int(c) for c in str(row.ciks).split("|")], row.share_rule)
    if sh.empty:
        return pd.Series(dtype=float), {"note": "no SEC shares"}
    val = sh["val"] * (1500 if row.share_rule == "berkshire_aeq" else 1)  # SEC gives A-equivalents
    # restate each count onto today's split basis using splits *after the filing*
    # Berkshire's A-equivalent -> B-equivalent factor of 1,500 is already on today's basis
    sf = (lambda f: 1.0) if row.share_rule == "berkshire_aeq" else (lambda f: split_factor_after(f, splits))
    sh_adj = pd.Series({d: v * sf(f) for d, v, f in zip(sh.index, val, sh["filed"])}).sort_index()
    sh_adj.index = sh_adj.index.to_period("M").to_timestamp("M")
    sh_adj = sh_adj[~sh_adj.index.duplicated(keep="last")]
    n_cov, n_cov_ok = 0, 0
    # Shelved: pre-2009 cover-page share counts (02b_sec_covers.py).  CRSP supersedes them; enable
    # with AEE_USE_COVERS=1 only if the free tier is ever needed for earlier years.  Untested end to end.
    if os.environ.get("AEE_USE_COVERS") == "1" and row.share_rule == "sum":
        cov, n_cov, n_cov_ok = cover_anchors([int(c) for c in str(row.ciks).split("|")], splits, sh_adj)
        if len(cov):
            sh_adj = pd.concat([cov[cov.index < sh_adj.index[0]], sh_adj]).sort_index()
    sh_adj, fixes = clean_anchors(sh_adj)

    n_sec = len(sh_adj)
    if row.yahoo in live:                     # today's implied share count
        mc, px = live[row.yahoo]
        sh_adj = pd.concat([sh_adj, pd.Series({close.index[-1] + pd.offsets.MonthEnd(1): mc / px})]).sort_index()

    months = close.index[(close.index >= sh_adj.index[0]) & (close.index <= LAST_MONTH)]
    shares_m = np.interp(months.astype("int64"), sh_adj.index.astype("int64"), sh_adj.values)
    cap = (close.reindex(months) * pd.Series(shares_m, index=months) / 1e9).dropna()

    gap = sh_adj.index.to_series().diff().dt.days.max()
    rep = {
        "tag": tag, "first": cap.index[0].date(), "last": cap.index[-1].date(), "n_anchors": n_sec,
        "cover_read": n_cov, "cover_used": n_cov_ok,
        "max_gap_days": int(gap) if gap == gap else 0, "fixes": ";".join(fixes),
        "cap_first_bn": round(float(cap.iloc[0]), 1), "cap_last_bn": round(float(cap.iloc[-1]), 1),
        "yahoo_now_bn": round(live[row.yahoo][0] / 1e9, 1) if row.yahoo in live else None,
    }
    return cap, rep


def main() -> None:
    long, report = [], []
    live = yahoo_live(list(UNIVERSE["yahoo"]))
    for row in UNIVERSE.itertuples():
        try:
            cap, rep = build_company(row, live)
        except Exception as e:  # keep going; report it
            cap, rep = pd.Series(dtype=float), {"note": f"FAILED {type(e).__name__}: {e}"}
        rep["id"] = row.id
        report.append(rep)
        if len(cap):
            long.append(pd.DataFrame({"date": cap.index, "id": row.id, "cap_bn": cap.values.round(3)}))
        print(f"{row.id:20s}", {k: v for k, v in rep.items() if k != "id"})
    pd.concat(long).to_csv(DERIVED / "companies_free.csv", index=False)
    pd.DataFrame(report).to_csv(DERIVED / "free_report.csv", index=False)


if __name__ == "__main__":
    main()
