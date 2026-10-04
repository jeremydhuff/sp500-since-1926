"""Pre-XBRL share counts: read the cover page of every 10-K / 10-Q filed 1993 -> mid-2009.

For each company in universe_free.csv this lists its filings (data.sec.gov submissions),
fetches the first ~80 kB of each filing, and records every large number that sits next to
the word "outstanding".  Which number is the share count is decided later (02_companies_free)
against the share count we already know from XBRL, so a stray figure cannot slip in.

Needs a contact in the User-Agent (SEC policy):
    set SEC_USER_AGENT=Your Name you@example.com

Output: data/raw/sec_covers/<accession>.json   {cik, form, filed, report, cands:[ints]}
Resumable: finished accessions are skipped.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

from common import RAW, ROOT, get, sec_headers

OUT = RAW / "sec_covers"
OUT.mkdir(parents=True, exist_ok=True)
FIRST, LAST = "1993-01-01", "2009-08-31"
FORMS = {"10-K", "10-K405", "10-Q", "10-KSB"}
NUM = re.compile(r"\b\d{1,3}(?:,\d{3}){2,}\b")
GAP = 0.13   # seconds between request starts, shared by all threads: inside SEC's 10 requests/second
WORKERS = 6
_lock, _next = threading.Lock(), [0.0]


def throttle() -> None:
    with _lock:
        now = time.monotonic()
        wait = max(0.0, _next[0] - now)
        _next[0] = max(now, _next[0]) + GAP
    if wait:
        time.sleep(wait)


def filings(cik: int) -> list[dict]:
    base = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
    j = json.loads(get(base, headers=sec_headers(), cache=RAW / "sec_sub" / f"{cik}.json", pause=GAP))
    blocks = [j["filings"]["recent"]]
    for f in j["filings"].get("files", []):
        if f["filingTo"] >= FIRST:
            u = "https://data.sec.gov/submissions/" + f["name"]
            blocks.append(json.loads(get(u, headers=sec_headers(), cache=RAW / "sec_sub" / f["name"], pause=GAP)))
    out = []
    for b in blocks:
        for i, form in enumerate(b["form"]):
            fd = b["filingDate"][i]
            if form in FORMS and FIRST <= fd <= LAST:
                out.append({"cik": cik, "form": form, "filed": fd, "report": b["reportDate"][i],
                            "accn": b["accessionNumber"][i], "doc": b["primaryDocument"][i]})
    return out


def head(url: str, n: int = 80_000) -> str | None:
    for attempt in range(3):
        try:
            throttle()
            r = requests.get(url, headers=sec_headers(), timeout=60, stream=True)
            if r.status_code == 200:
                buf = b""
                for chunk in r.iter_content(16_384):
                    buf += chunk
                    if len(buf) >= n:
                        break
                r.close()
                return buf.decode("latin1", "ignore")
            if r.status_code in (403, 429):
                time.sleep(5 * (attempt + 1))
                continue
            return None
        except requests.RequestException:
            time.sleep(2)
    return None


def candidates(text: str) -> list[int]:
    t = re.sub(r"<[^>]+>", " ", text)
    t = re.sub(r"&nbsp;|&#160;", " ", t)
    t = re.sub(r"\s+", " ", t)[:60_000]
    low = t.lower()
    vals: list[int] = []
    for m in NUM.finditer(t):
        lo, hi = max(0, m.start() - 350), m.end() + 350
        if "outstanding" in low[lo:hi]:
            v = int(m.group().replace(",", ""))
            if 1_000_000 <= v <= 60_000_000_000 and v not in vals:
                vals.append(v)
    return vals


def fetch(f: dict) -> None:
    dest = OUT / f"{f['accn']}.json"
    if dest.exists():
        return
    nd = f["accn"].replace("-", "")
    urls = []
    if f["doc"]:
        urls.append(f"https://www.sec.gov/Archives/edgar/data/{f['cik']}/{nd}/{f['doc']}")
    urls.append(f"https://www.sec.gov/Archives/edgar/data/{f['cik']}/{f['accn']}.txt")
    text = None
    for u in urls:
        text = head(u)
        if text:
            break
    rec = dict(f, cands=candidates(text) if text else None)
    dest.write_text(json.dumps(rec), encoding="utf-8")


def main() -> None:
    if "@" not in os.environ.get("SEC_USER_AGENT", ""):
        sys.exit("Set SEC_USER_AGENT to 'Your Name your@email' first (SEC fair-access policy).")
    uni = pd.read_csv(ROOT / "pipeline" / "universe_free.csv")
    ciks = sorted({int(c) for cs in uni["ciks"].astype(str) for c in cs.split("|")})
    todo = []
    for cik in ciks:
        try:
            todo += filings(cik)
        except Exception as e:  # noqa: BLE001
            print(f"  CIK {cik}: no filing list ({e})")
    todo = [f for f in todo if not (OUT / f"{f['accn']}.json").exists()]
    print(f"{len(ciks)} CIKs, {len(todo)} filings to read", flush=True)
    with ThreadPoolExecutor(WORKERS) as ex:
        for k, _ in enumerate(ex.map(fetch, todo), 1):
            if k % 200 == 0:
                print(f"  {k}/{len(todo)}", flush=True)
    print("done")


if __name__ == "__main__":
    main()
