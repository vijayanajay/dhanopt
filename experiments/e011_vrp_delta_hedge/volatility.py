"""E011 Volatility Engine: Realized vs Implied Volatility and VRP Signal.

Calculates:
1. Realized Volatility estimators (Garman-Klass, Parkinson, Close-to-Close).
2. Implied Volatility ($IV_{ATM}$) inverted from t-1 EOD ATM straddles in FO Bhavcopy.
3. Variance Risk Premium ($VRP_t = IV_{ATM, t-1} - \\sigma_{GK, 10d}(t-1)$).
4. Rolling 60-day 80th percentile entry gate with strict shift(1) no-look-ahead discipline.
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

from core.feeds.bhavcopy import parse_date
from core.feeds.intraday import available_dates, load_intraday_candles

HISTORICAL_DIR = ROOT / "data" / "historical"
INTRADAY_DIR = ROOT / "data" / "intraday"


def bs_straddle_price(spot: float, strike: float, iv: float, dte_days: float) -> float:
    """Computes Black-Scholes ATM straddle price (Call + Put)."""
    t = max(dte_days, 0.05) / 365.0
    vol = max(iv, 0.01)
    denom = vol * math.sqrt(t)
    d1 = (math.log(spot / strike) + 0.5 * vol * vol * t) / denom
    d2 = d1 - denom
    cdf = lambda x: 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
    c = spot * cdf(d1) - strike * cdf(d2)
    p = strike * (1.0 - cdf(d2)) - spot * (1.0 - cdf(d1))
    return c + p


def invert_straddle_iv(spot: float, strike: float, straddle_price: float, dte_days: float) -> float:
    """Inverts Black-Scholes to find implied volatility for an ATM straddle.

    Uses bisection over [0.01, 3.00]. Monotone and guaranteed to converge.
    """
    if straddle_price <= 0.1 or spot <= 0 or strike <= 0:
        return np.nan

    lo, hi = 0.01, 3.0
    for _ in range(30):
        mid = 0.5 * (lo + hi)
        if bs_straddle_price(spot, strike, mid, dte_days) < straddle_price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def build_bhavcopy_calendar(historical_dir: Optional[Path] = None) -> Dict[date, Path]:
    """Maps trade_date -> FO Bhavcopy parquet file path."""
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


def extract_eod_straddle(bhavcopy_path: Path) -> Optional[Dict]:
    """Extracts nearest weekly/monthly expiry and ATM straddle price from FO bhavcopy."""
    try:
        df = pd.read_parquet(bhavcopy_path)
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

    atm_strike = round(spot_ref / 50.0) * 50.0

    opts = nifty[nifty["instrument"].isin(["OPTIDX", "IDO"])].copy()
    if opts.empty:
        return None

    opts["exp_dt"] = opts["expiry"].map(lambda e: parse_date(str(e).strip()))
    valid_exp = sorted([e for e in opts["exp_dt"].unique() if e and e >= trade_date])
    if not valid_exp:
        return None

    nearest_exp = valid_exp[0]
    dte_days = (nearest_exp - trade_date).days

    chain = opts[opts["exp_dt"] == nearest_exp]
    ce = chain[(chain["option_type"] == "CE") & (chain["strike"] == atm_strike)]
    pe = chain[(chain["option_type"] == "PE") & (chain["strike"] == atm_strike)]

    if ce.empty or pe.empty:
        return None

    ce_close = float(ce.iloc[0]["close"])
    pe_close = float(pe.iloc[0]["close"])
    straddle_price = ce_close + pe_close

    iv_atm = invert_straddle_iv(spot_ref, atm_strike, straddle_price, dte_days)

    return {
        "trade_date": trade_date,
        "spot_close": spot_ref,
        "atm_strike": atm_strike,
        "expiry": nearest_exp,
        "dte_days": dte_days,
        "ce_close": ce_close,
        "pe_close": pe_close,
        "straddle_price": straddle_price,
        "iv_atm": iv_atm,
    }


def compute_volatility_dataset(
    historical_dir: Optional[Path] = None,
    intraday_dir: Optional[Path] = None,
    window_days: int = 10,
    percentile_window: int = 60,
    percentile_hurdle: float = 0.80,
) -> pd.DataFrame:
    """Builds a daily volatility frame with strictly shifted Garman-Klass RV and VRP."""
    cal = build_bhavcopy_calendar(historical_dir)
    session_dates = available_dates(intraday_dir)

    rows: List[Dict] = []
    for d in session_dates:
        try:
            cdf = load_intraday_candles(d, intraday_dir)
        except Exception:
            continue

        if len(cdf) < 50:
            continue

        o = float(cdf.iloc[0]["open"])
        h = float(cdf["high"].max())
        l = float(cdf["low"].min())
        c = float(cdf.iloc[-1]["close"])

        # Garman-Klass single-day variance
        # 0.5 * (ln(H/L))^2 - (2*ln(2) - 1) * (ln(C/O))^2
        log_hl = math.log(max(h / l, 1.0001))
        log_co = math.log(max(c / o, 1.0001))
        gk_var = 0.5 * (log_hl**2) - (2.0 * math.log(2.0) - 1.0) * (log_co**2)

        # Parkinson single-day variance
        # (1 / (4 * ln(2))) * (ln(H/L))^2
        park_var = (1.0 / (4.0 * math.log(2.0))) * (log_hl**2)

        # Close-to-close log return will be computed on series
        rows.append({
            "date": d,
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "gk_var": gk_var,
            "park_var": park_var,
        })

    vdf = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)

    # Rolling annualized Garman-Klass & Parkinson volatility (annualized with 252) over 5, 10, 20 days
    for w in (5, 10, 20):
        vdf[f"sigma_gk_{w}d"] = np.sqrt(np.maximum(vdf["gk_var"].rolling(w, min_periods=w).mean() * 252.0, 1e-6))
        vdf[f"sigma_p_{w}d"] = np.sqrt(np.maximum(vdf["park_var"].rolling(w, min_periods=w).mean() * 252.0, 1e-6))

    # Pull EOD Straddle IV from Bhavcopy
    bhav_rows: List[Dict] = []
    for d in vdf["date"]:
        if d in cal:
            s_data = extract_eod_straddle(cal[d])
            if s_data:
                bhav_rows.append(s_data)

    bdf = pd.DataFrame(bhav_rows)
    if not bdf.empty:
        vdf = vdf.merge(bdf[["trade_date", "expiry", "dte_days", "straddle_price", "iv_atm"]],
                        left_on="date", right_on="trade_date", how="left").drop(columns=["trade_date"])

    # Strict t-1 discipline:
    # Day t trading decision must use t-1 EOD IV and t-1 Garman-Klass / Parkinson RV
    vdf["iv_atm_t1"] = vdf["iv_atm"].shift(1)
    vdf["dte_t1"] = vdf["dte_days"].shift(1)

    for w in (5, 10, 20):
        vdf[f"sigma_gk_{w}d_t1"] = vdf[f"sigma_gk_{w}d"].shift(1)
        vdf[f"sigma_p_{w}d_t1"] = vdf[f"sigma_p_{w}d"].shift(1)
        vdf[f"vrp_{w}d_t1"] = vdf["iv_atm_t1"] - vdf[f"sigma_gk_{w}d_t1"]
        vdf[f"vrp_p_{w}d_t1"] = vdf["iv_atm_t1"] - vdf[f"sigma_p_{w}d_t1"]

    # Backward-compatible column aliases for default 10d
    vdf["sigma_gk_t1"] = vdf["sigma_gk_10d_t1"]
    vdf["sigma_p_t1"] = vdf["sigma_p_10d_t1"]
    vdf["vrp_t1"] = vdf["vrp_10d_t1"]

    # Rolling 60-day 80th percentile of VRP, strictly shifted
    # Day t's hurdle is the 80th percentile of {VRP_{t-61}, ..., VRP_{t-1}}
    vdf["vrp_p80"] = vdf["vrp_t1"].rolling(percentile_window, min_periods=30).quantile(percentile_hurdle)

    # Signal on Day t: VRP(t-1) >= 80th percentile hurdle
    vdf["vrp_signal"] = (vdf["vrp_t1"] >= vdf["vrp_p80"]) & (vdf["vrp_t1"] > 0)

    # Save to artifacts cache
    cache_path = HERE / "artifacts" / "volatility_daily.parquet"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    vdf.to_parquet(cache_path, index=False)

    return vdf


def get_vrp_signal(
    vdf: pd.DataFrame,
    estimator: str = "gk",
    window: int = 10,
    percentile_window: int = 60,
    percentile_hurdle: float = 0.80,
) -> pd.Series:
    """Computes rolling 60-day 80th percentile signal for specified estimator & window.

    estimator: 'gk' (Garman-Klass) or 'p' / 'parkinson' (Parkinson)
    window: 5, 10, or 20 days
    """
    est_key = "gk" if estimator.lower() in ("gk", "garman_klass", "garman-klass") else "p"
    vrp_col = f"vrp_{window}d_t1" if est_key == "gk" else f"vrp_p_{window}d_t1"

    if vrp_col in vdf.columns:
        series = vdf[vrp_col]
    else:
        rv_col = f"sigma_{est_key}_{window}d_t1"
        series = vdf["iv_atm_t1"] - vdf[rv_col]

    p_hurdle = series.rolling(percentile_window, min_periods=30).quantile(percentile_hurdle)
    return (series >= p_hurdle) & (series > 0)


def load_or_compute_volatility(force_recompute: bool = False) -> pd.DataFrame:
    """Loads cached volatility frame or computes from scratch if absent."""
    cache_path = HERE / "artifacts" / "volatility_daily.parquet"
    if cache_path.exists() and not force_recompute:
        return pd.read_parquet(cache_path)
    return compute_volatility_dataset()

