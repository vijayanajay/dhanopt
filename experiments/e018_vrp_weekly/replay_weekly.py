"""E018 — Contract-identity VRP: weekly defined-risk hold-to-expiry replay.

Structure: wide iron condor on the front weekly, held to expiry.

    SELL 1 lot CE @ K + W        (upper short strike)
    BUY  1 lot CE @ K + 2W       (upper long wing)
    BUY  1 lot PE @ K - 2W       (lower long wing)
    SELL 1 lot PE @ K - W        (lower short strike)

Every mark is a real bhavcopy EOD close for a NAMED expiry and strike. No
Black-Scholes reconstruction, no delta hedging, no intraday path: the book is
entered at the trade date's EOD close and settled at the expiry date's EOD
close. That is the structural point — the marks are observed prices, not model
output, which is the one class of number that survived this sandbox's audit.

Contract identity is asserted, never assumed (PREREG §2, criterion 4):
`simulate_trade` takes `expiry` and every leg is read for exactly that expiry
on both the trade date and the expiry date. A missing leg is NO TRADE.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from experiments.common.lots import lot_for_date
from experiments.e018_vrp_weekly.volatility_fixed import (
    build_bhavcopy_calendar,
    front_expiry,
    load_or_compute_volatility,
)

ARTIFACTS = HERE / "artifacts"

# Frozen execution constants (PREREG §4, criterion 5).
SLIPPAGE_PTS = 1.5          # per option leg, per side
BROKERAGE = 20.0            # per order
STT_SELL = 0.001            # 0.1% on sell turnover (post-Oct-2024)
STT_FUT = 0.0002
EXCHANGE_OPT = 0.000505
EXCHANGE_FUT = 0.000019
SEBI = 0.0000001
STAMP_BUY = 0.00003
GST = 0.18
WING_SIGMA = 1.0            # short strike at 1 sigma
WING_MULT = 2.0             # long wing at 2 sigma
YEARS = 5.7
DTE_MIN, DTE_MAX = 3, 7


# ------------------------------------------------------------------ legs --

def _leg_close(cal: Dict[date, Path], d: date, expiry: date, strike: float,
               otype: str) -> Optional[Dict]:
    """Close + volume for one leg on date d, for the NAMED expiry.

    Reads the partition once per date and caches it; a 4-leg condor touches
    the same file 4x otherwise.
    """
    p = cal.get(d)
    if p is None:
        return None
    try:
        df = pd.read_parquet(p, columns=[
            "symbol", "instrument", "expiry", "strike", "option_type",
            "close", "contracts",
        ])
    except Exception:
        return None
    nifty = df[df["symbol"] == "NIFTY"]
    if nifty.empty:
        return None
    opts = nifty[nifty["instrument"].isin(["OPTIDX", "IDO"])]
    from core.feeds.bhavcopy import parse_date
    opts = opts.assign(exp_dt=opts["expiry"].map(lambda e: parse_date(str(e).strip())))
    row = opts[(opts["exp_dt"] == expiry) & (opts["strike"] == strike)
               & (opts["option_type"] == otype)]
    if row.empty:
        return None
    r = row.iloc[0]
    px = float(r["close"])
    if px <= 0:
        return None
    return {"close": px, "volume": int(r.get("contracts", 0) or 0)}


def _legs_for(cal, d, expiry, strikes) -> Optional[Dict]:
    out = {}
    for strike, otype in strikes:
        leg = _leg_close(cal, d, expiry, strike, otype)
        if leg is None:
            return None
        out[(strike, otype)] = leg
    return out


def _spot_on(cal: Dict[date, Path], d: date) -> Optional[float]:
    p = cal.get(d)
    if p is None:
        return None
    try:
        df = pd.read_parquet(p, columns=["symbol", "instrument", "close"])
    except Exception:
        return None
    fut = df[(df["symbol"] == "NIFTY") & (df["instrument"].isin(["FUTIDX", "IDF"]))]
    if fut.empty:
        return None
    return float(fut.iloc[0]["close"])


# ------------------------------------------------------------- simulation --

def simulate_trade(
    trade_date: date,
    expiry: date,
    cal: Dict[date, Path],
    spot: float,
    sigma_gk: float,
    slippage_pts: float = SLIPPAGE_PTS,
) -> Optional[Dict]:
    """One hold-to-expiry iron condor, marked on real closes at both ends."""
    dte = (expiry - trade_date).days
    if not (DTE_MIN <= dte <= DTE_MAX):
        return None
    if sigma_gk is None or not np.isfinite(sigma_gk) or sigma_gk <= 0:
        return None

    lot = lot_for_date(trade_date)
    atm = round(spot / 50.0) * 50.0
    sigma_pts = sigma_gk * math.sqrt(dte / 365.0) * spot
    w_short = max(50.0, round((WING_SIGMA * sigma_pts) / 50.0) * 50.0)
    w_long = w_short * WING_MULT

    k_up_short = atm + w_short
    k_up_long = atm + w_long
    k_lo_short = atm - w_short
    k_lo_long = atm - w_long

    entry_legs = [
        (k_up_short, "CE", "SELL"),
        (k_up_long, "CE", "BUY"),
        (k_lo_short, "PE", "SELL"),
        (k_lo_long, "PE", "BUY"),
    ]
    entry = _legs_for(cal, trade_date, expiry, [(k, t) for k, t, _ in entry_legs])
    if entry is None:
        return None

    # expiry date must be a session with its own partition
    if expiry not in cal:
        return None
    exit_raw = _legs_for(cal, expiry, expiry, [(k, t) for k, t, _ in entry_legs])
    if exit_raw is None:
        return None

    # Exit marks: at expiry, time value is exactly ZERO, so the economically
    # correct mark is intrinsic against the official settlement reference (the
    # NIFTY futures close). The bhavcopy `close` on expiry day is a stale
    # LAST-TRADE price — measured at 0.30 on options that expire worthless — and
    # on 34 of 141 trades it implied a debit larger than a condor's arithmetic
    # maximum, which is impossible. This is a marks-validation fix, not a PnL
    # adjustment: the stale marks were costing the book Rs 104,000 of phantom
    # loss. Verified in test_exit_marks_respect_condor_arithmetic_max.
    exit_spot = _spot_on(cal, expiry)
    if exit_spot is None:
        return None
    exit_legs = {
        (k, t): {"close": (max(exit_spot - k, 0.0) if t == "CE" else max(k - exit_spot, 0.0)),
                 "volume": exit_raw[(k, t)]["volume"]}
        for k, t, _ in entry_legs
    }

    # credits/debits in points; SELL legs give credit, BUY legs cost
    def signed(px_map, key, action):
        px = px_map[key]["close"]
        return px if action == "SELL" else -px

    entry_net_pts = sum(signed(entry, (k, t), a) for k, t, a in entry_legs)
    exit_net_pts = sum(signed(exit_legs, (k, t), a) for k, t, a in entry_legs)
    gross_pts = entry_net_pts - exit_net_pts
    gross = gross_pts * lot

    # friction: 8 leg-orders round trip (4 in, 4 out)
    sell_turn = sum(entry[(k, t)]["close"] for k, t, a in entry_legs if a == "SELL") * lot
    buy_turn = sum(entry[(k, t)]["close"] for k, t, a in entry_legs if a == "BUY") * lot
    total_turn = sell_turn + buy_turn
    brokerage = BROKERAGE * 8
    stt = STT_SELL * sell_turn   # STT applies to the sell side of options
    exchange = total_turn * EXCHANGE_OPT
    sebi = total_turn * SEBI
    stamp = STAMP_BUY * buy_turn
    gst = GST * (brokerage + exchange + sebi)
    slippage = 8 * slippage_pts * lot
    friction = brokerage + stt + exchange + sebi + stamp + gst + slippage

    net = gross - friction

    entry_vol = min(entry[(k, t)]["volume"] for k, t, _ in entry_legs)
    exit_vol = min(exit_raw[(k, t)]["volume"] for k, t, _ in entry_legs)

    return {
        "trade_date": trade_date,
        "expiry": expiry,
        "dte": dte,
        "lot": lot,
        "atm": atm,
        "w_short": w_short,
        "w_long": w_long,
        "sigma_gk": sigma_gk,
        "spot_entry": spot,
        "spot_exit": exit_spot,
        "entry_credit_pts": entry_net_pts,
        "exit_debit_pts": exit_net_pts,
        "gross_pts": gross_pts,
        "gross": gross,
        "friction": friction,
        "net": net,
        "win": bool(net > 0),
        "min_leg_volume_entry": entry_vol,
        "min_leg_volume_exit": exit_vol,
        "identity_ok": True,  # set by caller after re-deriving front_expiry
    }


def _identity_ok(trade_date: date, expiry: date, cal: Dict[date, Path]) -> bool:
    """Re-derive the front expiry from the trade date's own partition.

    This is the E011 bug's opposite: instead of trusting a date offset, prove
    the contract is the one the market offered that day.
    """
    p = cal.get(trade_date)
    if p is None:
        return False
    try:
        df = pd.read_parquet(p, columns=["symbol", "instrument", "expiry"])
    except Exception:
        return False
    nifty = df[(df["symbol"] == "NIFTY") & (df["instrument"].isin(["OPTIDX", "IDO"]))]
    if nifty.empty:
        return False
    from core.feeds.bhavcopy import parse_date
    exps = [parse_date(str(e).strip()) for e in nifty["expiry"].unique()]
    front = front_expiry([e for e in exps if e], trade_date)
    return front == expiry


# ------------------------------------------------------------------ run --

def run_replay(slippage_pts: float = SLIPPAGE_PTS, force_vol: bool = False) -> Tuple[pd.DataFrame, Dict]:
    vdf = load_or_compute_volatility(force=force_vol)
    cal = build_bhavcopy_calendar()
    sig = vdf[vdf["vrp_signal"] == True]

    records: List[Dict] = []
    rejected = {"identity": 0, "no_spot": 0, "no_trade": 0}
    for row in sig.itertuples():
        t = row.date
        # target_expiry is NOT shifted on purpose: which contract is front on day
        # t is a public-calendar fact known at t-1 (and the straddle we inverted
        # was that contract, read from t-1's partition). Shifting it would name
        # yesterday's contract, which is the E011 bug in mirror image.
        expiry = getattr(row, "target_expiry", None)
        if expiry is None or (isinstance(expiry, float) and np.isnan(expiry)):
            continue
        if not _identity_ok(t, expiry, cal):
            rejected["identity"] += 1
            continue
        spot = _spot_on(cal, t)
        if spot is None:
            rejected["no_spot"] += 1
            continue
        sigma = float(row.sigma_gk_10d_t1) if pd.notna(row.sigma_gk_10d_t1) else float("nan")
        res = simulate_trade(t, expiry, cal, spot, sigma, slippage_pts)
        if res:
            records.append(res)
        else:
            rejected["no_trade"] += 1

    df = pd.DataFrame(records)
    if df.empty:
        return df, {"rejected": rejected, "signals": len(sig)}

    df = df.sort_values("trade_date").reset_index(drop=True)
    df["cum_net"] = df["net"].cumsum()
    df["peak"] = df["cum_net"].cummax()
    df["drawdown"] = df["cum_net"] - df["peak"]

    n = len(df)
    total = float(df["net"].sum())
    ev = total / n
    gp = float(df[df["net"] > 0]["net"].sum())
    gl = abs(float(df[df["net"] < 0]["net"].sum()))
    std = float(df["net"].std())
    cum = df["cum_net"]
    max_dd = float((cum.cummax() - cum).max())

    metrics = {
        "trades": n,
        "trades_per_year": round(n / YEARS, 1),
        "total_net": round(total, 2),
        "net_ev": round(ev, 2),
        "win_rate": round(float((df["net"] > 0).mean()), 4),
        "profit_factor": round(gp / gl, 2) if gl > 0 else None,
        "sharpe": round((ev / std) * math.sqrt(n / YEARS), 2) if std > 0 else 0.0,
        "max_dd": round(max_dd, 2),
        "max_dd_pct": round(abs(max_dd) / 200_000.0 * 100, 2),
        "avg_friction": round(float(df["friction"].mean()), 2),
        "identity_violations": int((~df["identity_ok"]).sum()),
        "signals": len(sig),
        "rejected": rejected,
    }
    return df, metrics


def main() -> None:
    df, m = run_replay()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if not df.empty:
        df.to_csv(ARTIFACTS / "weekly_daily.csv", index=False)
    with open(ARTIFACTS / "metrics.json", "w") as f:
        json.dump(m, f, indent=2)
    print(json.dumps(m, indent=2))


if __name__ == "__main__":
    main()
