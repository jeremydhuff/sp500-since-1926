# Updating S&P 500 since 1926

How to refresh the data, change the page, and publish. Commands are PowerShell, run from the project folder.

```powershell
cd "C:\Users\galax\OneDrive\Desktop\Claude Code Projects\American Equity Explorer"
```

## What lives where

| Path | What it is |
|---|---|
| `site/index.html`, `site/app.js` | The page and all its behaviour. In git. |
| `site/market.js` | The data the page reads. **Built, not committed** (see "Licensing"). |
| `pipeline/` | Python that builds `market.js`. In git. |
| `data/companies.json` | Display list of companies (names, colours, CRSP name patterns). Written by `pipeline/master_build.py`. |
| `data/raw/`, `data/derived/` | Download cache and intermediate files. Not in git. |
| `C:\wrds_data\` | The raw WRDS/CRSP pull. Kept outside OneDrive and outside git on purpose. |

## Licensing: read before publishing anything

WRDS and CRSP data are licensed for **academic, non-commercial use** through your institution's WRDS account.

- `site/market.js` and `data/derived/*wrds*` contain CRSP-derived values and are in `.gitignore`. Do not commit them, and do not host `market.js` publicly, unless your institution's WRDS Subscription Agreement allows it.
- Never share or store your WRDS password in the project. The `wrds` package keeps it in `%APPDATA%\postgresql\pgpass.conf`.
- Do not let AI tools read WRDS query output until you have read the WRDS AI policy.
- Anything you publish that used WRDS must carry the citation, which the page adds to its sources panel automatically: "Wharton Research Data Services (WRDS) was used in preparing this chart. This service and the data available thereon constitute valuable intellectual property and trade secrets of WRDS and/or its third-party suppliers."
- `wrds_pull.py` asks you to confirm these terms once a year. It refuses to save under OneDrive, Dropbox, iCloud or Google Drive.

## First-time setup on a new machine

1. Install Python 3.11 or newer, then `pip install pandas requests wrds`.
2. Set a contact for SEC requests (they ask API clients to identify themselves): `$env:SEC_USER_AGENT = "Your Name you@example.com"`.
3. Pull CRSP once (below) so there is data to build from.

## Refreshing the data (monthly or quarterly)

CRSP on WRDS lags by several months, so the page carries the last CRSP month forward with the Ken French size data and fills company values from Yahoo Finance and SEC filings. A new pull moves that handover later.

**Step 1: pull CRSP from WRDS (you, in a terminal, because it needs your login).**

```powershell
$env:AEE_WRDS_DIR = 'C:\wrds_data'
python pipeline/wrds_pull.py --inspect    # optional: confirms table and column names
python pipeline/wrds_pull.py              # about 5-15 minutes
```

The first run asks you to type `yes` to the terms, then for your WRDS username and password (say yes to saving them in pgpass if the computer is yours alone) and to approve Duo on your phone.

**Step 2: rebuild everything.**

```powershell
$env:AEE_WRDS_DIR = 'C:\wrds_data'
python pipeline/refresh.py --fresh --wrds
```

`--fresh` throws away cached downloads so new months are fetched. Without it the build reuses old copies and nothing moves. It takes a few minutes because it re-downloads the Ken French files and the Yahoo and SEC data for about 90 companies. The last line says how many months and companies went into `site/market.js`.

**Step 3: look at it.**

```powershell
python -m http.server 8765 --directory site
```

Open <http://localhost:8765>. Check that the last month is what you expect, the index total at the right edge looks continuous across the "CRSP data ends" month, and the company legend has no oddities. Hard-reload (Ctrl+F5) because browsers cache `market.js`.

## New big companies appear as grey "everyone else"

The build matches CRSP company names to display companies by pattern. A large company with no pattern falls into the grey band. After a build:

1. Open `data/derived/wrds_unmapped.csv`. It lists large companies with no display entry, with their CRSP names.
2. Add a row for each to `ROWS` in `pipeline/master_build.py`: `(id, "Display name", "SHORT LABEL", sector, None, r"^CRSP NAME PATTERN")`. Sector is one of `NoDur Durbl Manuf Enrgy Chems BusEq Telcm Utils Shops Hlth Money Other`. CRSP writes initials with spaces (`"G T E"`, `"I T T"`), and the first matching row wins, so put specific patterns before general ones.
3. Optional: give it a colour in `BRAND` in the same file. Otherwise it gets a tint of its sector colour.
4. Rebuild: `python pipeline/refresh.py --wrds` (no `--fresh` needed).

## Changing the page

All settings sit near the top of `site/app.js`:

| Want to change | Edit |
|---|---|
| How many companies get a band each month | `TOP_N` (default 10) |
| How much thicker they are drawn than their true share (log and linear views only; the 100% view is always true size) | `TOP_SCALE` (default 1.5; 1 = true size) |
| Months a band takes to fade in or out | `TOP_FADE` (default 13) |
| Minimum grey left above the top companies | `TOP_MAX` (default 0.92, so 8% grey) |
| Start-year buttons (1926, 1957, 1990, 2010) | the `From` buttons in `site/index.html`, and `startOf` in `app.js` |
| Which companies appear as legend buttons | `renderKeys` in `app.js` (Tesla is pinned in, Nabisco is left out) |
| Company or sector colours | `BRAND` and `SECTOR_HUE` in `pipeline/master_build.py`, then rebuild |
| Titles and copy | `site/index.html`, and `renderCopy` / `renderPanels` in `app.js` |

Deep links for checking a view: `http://localhost:8765/#group=companies&from=1990&axis=log` (also `iso=<company id>` to preselect a company, and `sel=2000-03` to set the date).

## Checks

```powershell
python pipeline/tests/check_wrds_fixture.py   # the WRDS build logic on synthetic data; must print "all checks passed"
```

## Publishing

Two things are published from the same repository:

- **Code** (branch `main`): `git add -A`, `git commit -m "Describe the change"`, `git push`. `git status` should never list `site/market.js` or anything under `data/`. If it does, stop and check `.gitignore`.
- **The live site** (branch `gh-pages`, served by GitHub Pages at <https://jeremydhuff.github.io/sp500-since-1926/>): after rebuilding the data or changing the page, run

  ```powershell
  python pipeline/publish_site.py
  ```

  It copies `index.html`, `app.js` and `market.js` into a single fresh commit on `gh-pages` and force-pushes it. The site updates in a minute or two. Each publish gives the scripts a new `?v=` stamp, so visitors never see a stale copy.

`market.js` contains CRSP-derived values from WRDS, so the live site publishes them. That is only appropriate if your institution's WRDS Subscription Agreement allows it. To take the data down, run `gh api -X DELETE repos/jeremydhuff/sp500-since-1926/pages` (the site goes offline) and `git push origin --delete gh-pages` (removes the published copy of `market.js`).

## When something breaks

- **`wrds_pull.py` says it cannot find tables or columns.** CRSP changes formats occasionally. Run `--inspect`, then fix the names in the `FLAVORS` dictionary at the top of `pipeline/wrds_pull.py` (one line per column).
- **Page says `market.js not found`.** Run Step 2 above. The file is not in git.
- **A company is missing or merged into another.** Check its pattern in `ROWS`. Two CRSP company records can share one display id on purpose (Nabisco does).
- **Page looks stale after a rebuild.** Hard-reload; the browser cached the old `market.js`.
- **Yahoo or SEC downloads fail.** Rerun; both throttle. SEC needs `SEC_USER_AGENT` set.
