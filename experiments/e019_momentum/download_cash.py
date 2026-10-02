"""E019 — Free NSE cash-market EOD downloader.

Fetches the official daily cash bhavcopy from NSE's public archive (the same
publisher and the same 15:30 EOD convention as the FO partitions already in
data/historical/) and normalizes it into the repo's partitioned parquet layout.

    python -m experiments.e019_momentum.download_cash --start-year 2021 --end-year 2026

No new dependency: `requests` is already used by core/feeds/bhavcopy.py.
Idempotent — a session already on disk is skipped, so a killed run resumes.
"""
from __future__ import annotations

import argparse
import io
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

import config

CASH_DIR = config.DATA_DIR / "cash"

# NSE has published cash bhavcopy under two different names. Both are probed per
# date and the first that returns data wins, so the downloader is agnostic to
# where exactly the archive cut over (~Aug 2024, verified by probe).
NEW_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
OLD_URL = ("https://nsearchives.nseindia.com/content/historical/EQUITIES/"
           "{y}/{mon}/cm{dd}{mon}{y}bhav.csv.zip")
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")

# NSE serves these as .zip regardless of extension; a missing session (holiday)
# returns a 200 with a non-zip body or a 404, both of which mean "no session".
KEEP_TYPES = {"STK", "ETF", "REIT", "SGB"}

# Legacy-format series that are not plain common equity. ETFs and REITs are
# tradable cash instruments and are kept (that is where the ETF leg lives); the
# rest are debt/warrant paper and are dropped.
SERIES_KEEP = {"EQ", "ETF", "REIT"}
SERIES_TYPE = {"EQ": "STK", "ETF": "ETF", "REIT": "REIT"}
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Referer": "https://www.nseindia.com/",
}


def partition_path(d: date, out_dir: Path = CASH_DIR) -> Path:
    return out_dir / f"year={d.year}" / f"month={d.month:02d}" / f"cm_{d:%Y%m%d}.parquet"


def weekday_dates(start: date, end: date) -> List[date]:
    out, cur = [], start
    while cur <= end:
        if cur.weekday() < 5:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def fetch_one(d: date, out_dir: Path = CASH_DIR, timeout: int = 60,
              session=None, retries: int = 5, pace: float = 0.35) -> Optional[date]:
    """One session. Returns the date on success, None if it is not a session.

    ponytail: NSE's archive WAF bans bursts — a 6-worker flood returns 403 for
    every subsequent request until the ban expires. So this is deliberately slow
    (one shared session, `pace` seconds between requests, linear backoff on 403)
    and idempotent (a cached partition is never re-fetched, so a killed run
    resumes). Upgrade path: mirror the archive, or a bulk vendor feed, if the
    sample ever needs more than ~1.5k politely-paced requests.
    """
    p = partition_path(d, out_dir)
    if p.exists():
        return d
    ymd = d.strftime("%Y%m%d")
    urls = [
        NEW_URL.format(ymd=ymd),
        OLD_URL.format(y=d.year, mon=MONTHS[d.month - 1], dd=d.strftime("%d")),
    ]
    import requests
    sess = session or requests
    raw = None
    time.sleep(pace)
    for url in urls:
        for attempt in range(retries):
            try:
                r = sess.get(url, timeout=timeout, headers=HEADERS)
            except Exception:
                time.sleep(2.0 * (attempt + 1))
                continue
            if r.status_code == 200 and len(r.content) > 5000:
                try:
                    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
                        raw = pd.read_csv(zf.open(zf.namelist()[0]), dtype=str, low_memory=False)
                    break
                except Exception:
                    break
            if r.status_code in (403, 429, 503):
                time.sleep(20.0 * (attempt + 1))   # banned: wait it out, don't hammer
            elif r.status_code == 404:
                break                              # this name doesn't exist; try the other
            else:
                time.sleep(2.0 * (attempt + 1))
        if raw is not None:
            break
    if raw is None:
        return None

    out = _normalize(raw, d)
    if out is None or out.empty:
        return None
    p.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(p, index=False)
    return d


def _normalize(raw: pd.DataFrame, d: date) -> Optional[pd.DataFrame]:
    """Map either archive format onto one schema."""
    if "TckrSymb" in raw.columns:                      # new format
        num = ["OpnPric", "HghPric", "LwPric", "ClsPric", "PrvsClsgPric"]
        for c in num:
            raw[c] = pd.to_numeric(raw[c], errors="coerce")
        keep = raw[raw["FinInstrmTp"].isin(KEEP_TYPES)].copy()
        if keep.empty:
            return None
        out = keep[[
            "TckrSymb", "FinInstrmTp", "SctySrs", "ISIN", "OpnPric", "HghPric",
            "LwPric", "ClsPric", "PrvsClsgPric", "TtlTradgVol", "TtlTrfVal",
        ]].rename(columns={
            "TckrSymb": "symbol", "FinInstrmTp": "type", "SctySrs": "series",
            "OpnPric": "open", "HghPric": "high", "LwPric": "low", "ClsPric": "close",
            "PrvsClsgPric": "prev_close", "TtlTradgVol": "volume", "TtlTrfVal": "turnover",
        })
    elif "SYMBOL" in raw.columns:                      # legacy format
        for c in ["OPEN", "HIGH", "LOW", "CLOSE", "PREVCLOSE"]:
            raw[c] = pd.to_numeric(raw[c], errors="coerce")
        keep = raw[raw["SERIES"].isin(SERIES_KEEP)].copy()
        if keep.empty:
            return None
        out = keep[[
            "SYMBOL", "SERIES", "ISIN", "OPEN", "HIGH", "LOW",
            "CLOSE", "PREVCLOSE", "TOTTRDQTY", "TOTTRDVAL",
        ]].rename(columns={
            "SYMBOL": "symbol", "SERIES": "series", "ISIN": "ISIN", "OPEN": "open",
            "HIGH": "high", "LOW": "low", "CLOSE": "close", "PREVCLOSE": "prev_close",
            "TOTTRDQTY": "volume", "TOTTRDVAL": "turnover",
        })
        out["type"] = out["series"].map(SERIES_TYPE)
    else:
        return None

    for c in ("volume", "turnover"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out[out["close"].notna() & (out["close"] > 0)]
    out["trade_date"] = d
    return out.reset_index(drop=True)


def download(start_year: int = 2021, end_year: int = 2026, workers: int = 1,
             pace: float = 0.35) -> None:
    dates = weekday_dates(date(start_year, 1, 1), min(date(end_year, 12, 31), date.today()))
    pending = [d for d in dates if not partition_path(d).exists()]
    print(f"weekdays {start_year}-{end_year}: {len(dates)} | "
          f"cached {len(dates)-len(pending)} | pending {len(pending)}", flush=True)
    if not pending:
        print("nothing to do")
        return

    import requests
    session = requests.Session()
    session.headers.update(HEADERS)

    # Serial by default and on purpose: the archive WAF bans bursts outright.
    # Order is chronological so an interrupted run resumes from where it stopped.
    ok, miss, t0, stalls = 0, 0, time.time(), 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(fetch_one, d, CASH_DIR, 60, session, 5, pace) for d in pending]
        for i, fut in enumerate(futs, 1):
            try:
                r = fut.result()
            except Exception:
                r = None
            if r is None:
                miss += 1
            else:
                ok += 1
            if ok and ok % 25 == 0 and ok != getattr(download, "_last", 0):
                download._last = ok
                el = time.time() - t0
                eta = (len(pending) - i) / (i / el) if el and i else 0
                print(f"  {i}/{len(pending)} ok={ok} miss={miss} "
                      f"{i/el:.2f}/s eta={eta/60:.1f}m", flush=True)
    print(f"done: {ok} cached, {miss} non-sessions/failures in {(time.time()-t0)/60:.1f}m")


def available_dates(out_dir: Path = CASH_DIR) -> List[date]:
    out = []
    for f in out_dir.glob("**/cm_*.parquet"):
        try:
            out.append(datetime.strptime(f.stem[3:], "%Y%m%d").date())
        except ValueError:
            continue
    return sorted(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2021)
    ap.add_argument("--end-year", type=int, default=2026)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--pace", type=float, default=0.35,
                    help="seconds between requests (WAF budget)")
    a = ap.parse_args()
    download(a.start_year, a.end_year, a.workers, a.pace)
