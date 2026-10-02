"""E012 Volatility Skew Engine: 25-Delta Skew Measurement & Signal Generation.

Implements:
1. Implied Volatility curve parameterization from EOD FO Bhavcopy (2021–2026).
2. Calculation of 25-Delta Skew: (IV_PE_25 - IV_CE_25) / IV_ATM.
3. Strike selection for 1x2 Ratio Spreads: 35-Delta Long Put, 15-Delta Short Puts, 2-Delta Wing Put.
4. Rolling 60-day 90th percentile entry gate with strict shift(1) no-look-ahead discipline.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.feeds.bhavcopy import parse_date
from core.pricing import bs_call, bs_put, delta_ce, delta_pe
from experiments.e011_vrp_delta_hedge.volatility import load_or_compute_volatility

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HISTORICAL_DIR = ROOT / "data" / "historical"
ARTIFACTS = HERE / "artifacts"


def invert_option_iv(spot: float, strike: float, price: float, dte_days: float, is_call: bool = True) -> float:
    """Inverts Black-Scholes using bisection for a single option contract."""
    t = max(dte_days, 0.05) / 365.0
    intrinsic = max(spot - strike, 0.0) if is_call else max(strike - spot, 0.0)
    if price <= intrinsic or price <= 0.05:
        return 0.05

    lo, hi = 0.01, 3.0
    fn = bs_call if is_call else bs_put
    for _ in range(25):
        mid = 0.5 * (lo + hi)
        if fn(spot, strike, mid, t) < price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def extract_skew_and_strikes(bhavcopy_path: Path) -> Optional[Dict]:
    """Parses one Bhavcopy parquet file, computes 25-delta skew and ratio spread strikes."""
    try:
        df = pd.read_parquet(
            bhavcopy_path,
            columns=["symbol", "instrument", "expiry", "strike", "option_type", "close", "trade_date"],
        )
    except Exception:
        return None

    nifty = df[df["symbol"] == "NIFTY"]
    if nifty.empty:
        return None

    fut = nifty[nifty["instrument"].isin(["FUTIDX", "IDF"])]
    if fut.empty:
        return None

    f0 = fut.iloc[0]
    td_raw = str(f0["trade_date"]).strip()
    try:
        trade_date = parse_date(td_raw)
    except Exception:
        return None

    spot_ref = float(f0["close"])
    if spot_ref <= 0:
        return None

    opts = nifty[nifty["instrument"].isin(["OPTIDX", "IDO"])].copy()
    if opts.empty:
        return None

    opts["exp_dt"] = opts["expiry"].map(lambda e: parse_date(str(e).strip()))
    valid_exp = sorted([e for e in opts["exp_dt"].unique() if e and e >= trade_date])
    if not valid_exp:
        return None

    nearest_exp = valid_exp[0]
    dte_days = (nearest_exp - trade_date).days
    t_years = max(dte_days, 0.05) / 365.0

    chain = opts[opts["exp_dt"] == nearest_exp]
    ce = chain[chain["option_type"] == "CE"].copy()
    pe = chain[chain["option_type"] == "PE"].copy()
    if ce.empty or pe.empty:
        return None

    atm_strike = round(spot_ref / 50.0) * 50.0
    atm_ce = ce[ce["strike"] == atm_strike]
    atm_pe = pe[pe["strike"] == atm_strike]
    if atm_ce.empty or atm_pe.empty:
        return None

    atm_ce_px = float(atm_ce.iloc[0]["close"])
    atm_pe_px = float(atm_pe.iloc[0]["close"])
    atm_iv = invert_option_iv(spot_ref, atm_strike, atm_pe_px, dte_days, is_call=False)

    # Calculate approximate deltas using ATM IV as reference anchor
    pe["delta"] = pe["strike"].map(lambda k: abs(delta_pe(spot_ref, k, atm_iv, t_years)))
    ce["delta"] = ce["strike"].map(lambda k: abs(delta_ce(spot_ref, k, atm_iv, t_years)))

    # Find 25-Delta strikes for Skew
    pe25_row = pe.iloc[(pe["delta"] - 0.25).abs().argsort()[:1]].iloc[0]
    ce25_row = ce.iloc[(ce["delta"] - 0.25).abs().argsort()[:1]].iloc[0]

    pe25_iv = invert_option_iv(spot_ref, pe25_row["strike"], float(pe25_row["close"]), dte_days, is_call=False)
    ce25_iv = invert_option_iv(spot_ref, ce25_row["strike"], float(ce25_row["close"]), dte_days, is_call=True)

    skew_25d = (pe25_iv - ce25_iv) / max(atm_iv, 0.01)

    # Find strikes for 1x2 Ratio Spread with Broken Wing:
    # Long Leg: 35-Delta Put
    pe35_row = pe.iloc[(pe["delta"] - 0.35).abs().argsort()[:1]].iloc[0]
    # Short Legs: 15-Delta Put
    pe15_row = pe.iloc[(pe["delta"] - 0.15).abs().argsort()[:1]].iloc[0]
    # Wing Leg: 2-Delta Put (tail protection)
    pe02_row = pe.iloc[(pe["delta"] - 0.02).abs().argsort()[:1]].iloc[0]

    return {
        "date": trade_date,
        "spot_close": spot_ref,
        "expiry": nearest_exp,
        "dte_days": dte_days,
        "atm_strike": atm_strike,
        "atm_iv": atm_iv,
        "pe25_iv": pe25_iv,
        "ce25_iv": ce25_iv,
        "skew_25d": skew_25d,
        "strike_long_35": float(pe35_row["strike"]),
        "px_long_35": float(pe35_row["close"]),
        "strike_short_15": float(pe15_row["strike"]),
        "px_short_15": float(pe15_row["close"]),
        "strike_wing_02": float(pe02_row["strike"]),
        "px_wing_02": float(pe02_row["close"]),
    }


def compute_skew_dataset(
    historical_dir: Optional[Path] = None,
    percentile_window: int = 60,
    percentile_hurdle: float = 0.90,
) -> pd.DataFrame:
    """Computes daily skew and ratio strikes across all historical Bhavcopy files."""
    hdir = historical_dir or HISTORICAL_DIR
    files = sorted(hdir.glob("**/*.parquet"))

    rows: List[Dict] = []
    for f in files:
        res = extract_skew_and_strikes(f)
        if res:
            rows.append(res)

    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

    # Strict t-1 discipline:
    # Day t trading decision must use t-1 EOD Skew and t-1 strikes
    df["skew_25d_t1"] = df["skew_25d"].shift(1)
    df["atm_iv_t1"] = df["atm_iv"].shift(1)
    df["dte_t1"] = df["dte_days"].shift(1)
    df["expiry_t1"] = df["expiry"].shift(1)

    df["strike_long_t1"] = df["strike_long_35"].shift(1)
    df["strike_short_t1"] = df["strike_short_15"].shift(1)
    df["strike_wing_t1"] = df["strike_wing_02"].shift(1)

    # Rolling 60-day 90th percentile of Skew, strictly shifted
    df["skew_p90"] = df["skew_25d_t1"].rolling(percentile_window, min_periods=30).quantile(percentile_hurdle)

    # Signal on Day t: Skew(t-1) >= 90th percentile hurdle and Skew > 0
    df["skew_signal"] = (df["skew_25d_t1"] >= df["skew_p90"]) & (df["skew_25d_t1"] > 0)

    # Cache artifact
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    cache_path = ARTIFACTS / "skew_daily.parquet"
    df.to_parquet(cache_path, index=False)

    return df


def load_or_compute_skew(force_recompute: bool = False) -> pd.DataFrame:
    """Loads cached skew frame or computes from scratch if absent."""
    cache_path = ARTIFACTS / "skew_daily.parquet"
    if cache_path.exists() and not force_recompute:
        return pd.read_parquet(cache_path)
    return compute_skew_dataset()
