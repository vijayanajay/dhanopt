"""E018 Volatility Engine — contract-identity-correct VRP signal.

The one thing this module exists to do differently from e011/volatility.py:

    e011 picked, on each date d, the expiry NEAREST TO d, inverted its ATM
    straddle, and then shifted the result by one day. The trade happens on
    d+1, where the tradable contract is the expiry nearest to d+1. When d was
    itself an expiry day those are different contracts, and the inverted "IV"
    was a bisection artifact (tenor ~0 against a pinned straddle -> IV up to
    1.929).

    e018 picks, for a trade date t, the expiry nearest to t — read out of t's
    OWN partition, so contract identity is a fact about the data, not an
    inference — and takes that expiry's ATM straddle as observed in the
    PREVIOUS session's partition. Same contract, t-1 observable, correct tenor.

Everything else (Garman-Klass realized vol, the rolling percentile hurdle,
era-correct lots, the EOD mark path) follows e011 so the two engines differ in
exactly one dimension and the comparison is legible.
"""

from __future__ import annotations

import math
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.feeds.bhavcopy import parse_date
from core.feeds.intraday import available_dates, load_intraday_candles

HISTORICAL_DIR = ROOT / "data" / "historical"
INTRADAY_DIR = ROOT / "data" / "intraday"


# ---------------------------------------------------------------- calendar --

def build_bhavcopy_calendar(historical_dir: Optional[Path] = None) -> Dict[date, Path]:
    """Maps trade_date -> FO bhavcopy parquet path."""
    hdir = historical_dir or HISTORICAL_DIR
    cal: Dict[date, Path] = {}
    for f in hdir.glob("**/*.parquet"):
        stem = f.stem
        if stem.startswith("fo_") and len(stem) == 11 and stem[3:].isdigit():
            try:
                cal[datetime.strptime(stem[3:], "%Y%m%d").date()] = f
            except ValueError:
                continue
    return cal


# ------------------------------------------------------------- IV helpers --

def _n(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_straddle_price(spot: float, strike: float, iv: float, dte_days: float) -> float:
    t = max(dte_days, 0.05) / 365.0
    vol = max(iv, 0.01)
    den = vol * math.sqrt(t)
    d1 = (math.log(spot / strike) + 0.5 * vol * vol * t) / den
    d2 = d1 - den
    return spot * _n(d1) - strike * _n(d2) + strike * _n(-d2) - spot * _n(-d1)


def invert_straddle_iv(spot: float, strike: float, straddle_price: float, dte_days: float) -> float:
    """Bisection inversion of the ATM straddle. Monotone, always converges.

    Same floor convention as e011 (tenor floored at 0.05 days) so the only
    difference between the engines is WHICH contract and WHICH tenor is passed
    in, never the maths.
    """
    if straddle_price <= 0.1 or spot <= 0 or strike <= 0:
        return float("nan")
    lo, hi = 0.01, 3.0
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        if bs_straddle_price(spot, strike, mid, dte_days) < straddle_price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ------------------------------------------------------ contract identity --

def front_expiry(expiries: List[date], trade_date: date) -> Optional[date]:
    """The expiry nearest to (and not before) trade_date. THE contract identity."""
    valid = sorted({e for e in expiries if e and e >= trade_date})
    return valid[0] if valid else None


def extract_straddles_all_expiries(bhav_path: Path) -> List[Dict]:
    """ATM straddle of EVERY listed expiry, in one pass over a partition.

    Naming the expiry explicitly is the fix: nothing here infers "the front
    contract" from a date comparison that can be off by a roll. One read per
    session (not two) is what makes the 1,415-session build tractable.
    """
    try:
        df = pd.read_parquet(bhav_path, columns=[
            "symbol", "instrument", "expiry", "strike",
            "option_type", "close", "contracts",
        ])
    except Exception:
        return []

    nifty = df[df["symbol"] == "NIFTY"]
    if nifty.empty:
        return []

    fut = nifty[nifty["instrument"].isin(["FUTIDX", "IDF"])]
    if fut.empty:
        return []
    spot = float(fut.iloc[0]["close"])
    if spot <= 0:
        return []
    strike = round(spot / 50.0) * 50.0

    opts = nifty[nifty["instrument"].isin(["OPTIDX", "IDO"])]
    if opts.empty:
        return []
    opts = opts.assign(exp_dt=opts["expiry"].map(lambda e: parse_date(str(e).strip())))

    out: List[Dict] = []
    for expiry in sorted({e for e in opts["exp_dt"] if e}):
        chain = opts[opts["exp_dt"] == expiry]
        if chain.empty:
            continue
        ce = chain[(chain["option_type"] == "CE") & (chain["strike"] == strike)]
        pe = chain[(chain["option_type"] == "PE") & (chain["strike"] == strike)]
        if ce.empty or pe.empty:
            continue
        ce_row, pe_row = ce.iloc[0], pe.iloc[0]
        out.append({
            "spot": spot,
            "strike": strike,
            "expiry": expiry,
            "ce_close": float(ce_row["close"]),
            "pe_close": float(pe_row["close"]),
            "straddle_price": float(ce_row["close"]) + float(pe_row["close"]),
            "ce_volume": int(ce_row.get("contracts", 0) or 0),
            "pe_volume": int(pe_row.get("contracts", 0) or 0),
            "strikes_available": int(chain["strike"].nunique()),
        })
    return out


def extract_straddle_for_expiry(bhav_path: Path, expiry: date) -> Optional[Dict]:
    for row in extract_straddles_all_expiries(bhav_path):
        if row["expiry"] == expiry:
            return row
    return None


def extract_leg(bhav_path: Path, expiry: date, strike: float, option_type: str) -> Optional[Dict]:
    """One option leg's EOD close + volume for a named expiry and strike."""
    try:
        df = pd.read_parquet(bhav_path)
    except Exception:
        return None
    nifty = df[df["symbol"] == "NIFTY"]
    if nifty.empty:
        return None
    fut = nifty[nifty["instrument"].isin(["FUTIDX", "IDF"])]
    if fut.empty:
        return None
    spot = float(fut.iloc[0]["close"])
    opts = nifty[nifty["instrument"].isin(["OPTIDX", "IDO"])].copy()
    if opts.empty:
        return None
    opts["exp_dt"] = opts["expiry"].map(lambda e: parse_date(str(e).strip()))
    row = opts[
        (opts["exp_dt"] == expiry)
        & (opts["strike"] == strike)
        & (opts["option_type"] == option_type)
    ]
    if row.empty:
        return None
    r = row.iloc[0]
    return {"close": float(r["close"]), "volume": int(r.get("contracts", 0) or 0), "spot": spot}


# -------------------------------------------------------- signal assembly --

def compute_volatility_dataset(
    historical_dir: Optional[Path] = None,
    intraday_dir: Optional[Path] = None,
    window_days: int = 10,
    percentile_window: int = 60,
    percentile_hurdle: float = 0.80,
) -> pd.DataFrame:
    """Daily frame with contract-identity-correct, strictly t-1 VRP.

    For each trade date t:
      * target expiry  = front_expiry(t) read from t's own partition
      * signal IV      = ATM straddle of THAT expiry from t-1's partition,
                        inverted with the tenor as observed on t-1
      * RV             = Garman-Klass over the trailing window ending t-1
      * VRP_t1         = IV_signal - sigma_GK(t-1)
    """
    cal = build_bhavcopy_calendar(historical_dir)
    sessions = available_dates(intraday_dir)
    sessions_sorted = sorted(sessions)

    # trailing realized vol from the 5-min store (t-1 and earlier only)
    rows: List[Dict] = []
    for d in sessions_sorted:
        try:
            cdf = load_intraday_candles(d, intraday_dir)
        except Exception:
            continue
        if len(cdf) < 50:
            continue
        o = float(cdf.iloc[0]["open"])
        h = float(cdf["high"].max())
        lo = float(cdf["low"].min())
        c = float(cdf.iloc[-1]["close"])
        log_hl = math.log(max(h / lo, 1.0001))
        log_co = math.log(max(c / o, 1.0001))
        rows.append({
            "date": d, "open": o, "high": h, "low": lo, "close": c,
            "gk_var": 0.5 * (log_hl ** 2) - (2.0 * math.log(2.0) - 1.0) * (log_co ** 2),
        })
    vdf = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    for w in (5, 10, 20):
        vdf[f"sigma_gk_{w}d"] = np.sqrt(
            np.maximum(vdf["gk_var"].rolling(w, min_periods=w).mean() * 252.0, 1e-6)
        )
        vdf[f"sigma_gk_{w}d_t1"] = vdf[f"sigma_gk_{w}d"].shift(1)

    # One read per session: the ATM straddle of every listed expiry, in parallel.
    prior_cal = sorted(cal)
    chain_rows: List[Dict] = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(extract_straddles_all_expiries, cal[d]): d for d in prior_cal}
        for fut in as_completed(futures):
            d = futures[fut]
            for r in fut.result():
                r["date"] = d
                chain_rows.append(r)
    chain = pd.DataFrame(chain_rows)
    if chain.empty:
        raise RuntimeError("no NIFTY chain rows extracted; aborting rather than reporting zeros")
    print(f"  chain rows: {len(chain)} across {chain['date'].nunique()} sessions", flush=True)

    # contract identity: for trade date t the tradable contract is the expiry
    # nearest to t, read out of t's OWN partition (a fact, not an inference).
    idx = chain.set_index(["date", "expiry"])
    prev_of = {}
    for i in range(1, len(prior_cal)):
        prev_of[prior_cal[i]] = prior_cal[i - 1]

    iv_rows: List[Dict] = []
    for t in sorted(d for d in vdf["date"] if d in cal):
        try:
            df_t = pd.read_parquet(cal[t], columns=["symbol", "instrument", "expiry"])
        except Exception:
            continue
        nifty = df_t[(df_t["symbol"] == "NIFTY") & (df_t["instrument"].isin(["OPTIDX", "IDO"]))]
        if nifty.empty:
            continue
        exps = {parse_date(str(e).strip()) for e in nifty["expiry"].unique()}
        target = front_expiry([e for e in exps if e], t)
        if target is None:
            continue
        prev = prev_of.get(t)
        if prev is None:
            continue
        try:
            obs = idx.loc[(prev, target)]
        except KeyError:
            continue
        if isinstance(obs, pd.DataFrame):
            obs = obs.iloc[0]
        dte_obs = (target - prev).days
        iv = invert_straddle_iv(obs["spot"], obs["strike"], obs["straddle_price"], dte_obs)
        iv_rows.append({
            "date": t, "target_expiry": target, "obs_date": prev,
            "iv_signal": iv, "dte_observed": dte_obs,
            "dte_at_trade": (target - t).days,
            "atm_strike": float(obs["strike"]), "signal_spot": float(obs["spot"]),
            "straddle_px": float(obs["straddle_price"]),
            "atm_volume": int(obs["ce_volume"]) + int(obs["pe_volume"]),
        })

    idf = pd.DataFrame(iv_rows)
    if not idf.empty:
        vdf = vdf.merge(idf, on="date", how="left")

    # strictly t-1: shift the signal row itself
    for col in ("iv_signal", "dte_observed", "dte_at_trade", "atm_strike", "signal_spot"):
        if col in vdf.columns:
            vdf[f"{col}_t1"] = vdf[col].shift(1)
    vdf["vrp_t1"] = vdf["iv_signal_t1"] - vdf["sigma_gk_10d_t1"]

    # rolling hurdle: day t's bar is the p80 of {VRP_{t-60}..VRP_{t-1}}
    vdf["vrp_p80"] = vdf["vrp_t1"].rolling(percentile_window, min_periods=30).quantile(percentile_hurdle)
    vdf["vrp_signal"] = (vdf["vrp_t1"] >= vdf["vrp_p80"]) & (vdf["vrp_t1"] > 0)

    ARTIFACTS = HERE / "artifacts"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    vdf.to_parquet(ARTIFACTS / "volatility_daily.parquet", index=False)
    return vdf


def load_or_compute_volatility(force: bool = False) -> pd.DataFrame:
    p = HERE / "artifacts" / "volatility_daily.parquet"
    if p.exists() and not force:
        return pd.read_parquet(p)
    return compute_volatility_dataset()
