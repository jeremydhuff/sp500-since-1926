# S&P 500 since 1926

The largest US companies by market value, month by month from 1926. Each band is a company's (or sector's) share of the index; the top edge is the index total, on a log scale by default. In the By company view the ten largest companies in each month sit on the baseline, drawn at 150% of their share on the log and linear views, with everyone else as the grey band above them.

Open `site/index.html` once `site/market.js` has been built (see below). Everything the page shows is in that one file.

**To refresh the data, change the page or publish, read [UPDATING.md](UPDATING.md).**

## Data

| Layer | Source | Covers |
|---|---|---|
| Index total | Actual S&P 500 membership from CRSP (via WRDS) from March 1957; the 500 largest US companies by size before that | 1926 to the last CRSP month |
| After the last CRSP month | The Ken French size-portfolio total, carried forward from the last CRSP total at its growth rate | up to today |
| Sectors | Ken French 12 industry portfolios (CRSP-derived), all listed US firms | 1926 to today |
| Companies | CRSP monthly market values through WRDS, summed by company; Yahoo Finance prices times SEC share counts for the months after CRSP ends | 1926 to today |

## Licensing

The company and index values come from CRSP through a WRDS subscription, which is licensed for academic, non-commercial use. This repository therefore holds **code only**: `site/market.js`, `data/derived/` and the WRDS pull are never committed. See "Licensing" in [UPDATING.md](UPDATING.md) before publishing anything built from them.

## Quick start

```
pip install pandas requests wrds
python pipeline/wrds_pull.py              # needs your own WRDS login
python pipeline/refresh.py --fresh --wrds # builds site/market.js
python -m http.server 8765 --directory site
```

Without a WRDS account, `python pipeline/refresh.py` builds a reduced version from public data only (sector weights from 1926, and 90 company bands from 2009).

## Layout

```
pipeline/   01 totals and sectors | 02 free companies | wrds_pull / wrds_build | 04 dataset | master_build | tests/
data/       companies.json (display list, colours, CRSP name patterns); raw/, derived/, wrds/ are local only
site/       index.html, app.js (market.js is built locally)
```
