"""Shared paths and helpers for the data pipeline."""
from __future__ import annotations

import io
import os
import time
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("AEE_DATA_DIR", ROOT / "data"))   # override only for tests
RAW = DATA / "raw"
DERIVED = DATA / "derived"
WRDS_DIR = Path(os.environ.get("AEE_WRDS_DIR", DATA / "wrds"))   # licensed data: keep off cloud-synced folders
SITE = ROOT / "site"
for _d in (RAW, DERIVED, WRDS_DIR, SITE):
    _d.mkdir(parents=True, exist_ok=True)

BROWSER_UA = {"User-Agent": "Mozilla/5.0"}


def sec_headers() -> dict:
    """SEC asks API clients to identify themselves.  Set SEC_USER_AGENT to
    'Your Name your@email' before running anything that touches sec.gov."""
    ua = os.environ.get("SEC_USER_AGENT", "AmericanEquityExplorer personal-research")
    return {"User-Agent": ua}


def get(url: str, *, headers=None, cache: Path | None = None, params=None, retries=3, pause=0.0):
    """GET with a simple on-disk cache and retry.  Returns bytes."""
    if cache is not None and cache.exists():
        return cache.read_bytes()
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=headers or BROWSER_UA, params=params, timeout=60)
            if r.status_code == 200:
                if cache is not None:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_bytes(r.content)
                if pause:
                    time.sleep(pause)
                return r.content
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:  # pragma: no cover
            last = str(e)
        time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"GET failed for {url}: {last}")


def unzip_first(blob: bytes) -> str:
    z = zipfile.ZipFile(io.BytesIO(blob))
    return z.read(z.namelist()[0]).decode("latin1").replace("\r", "")
