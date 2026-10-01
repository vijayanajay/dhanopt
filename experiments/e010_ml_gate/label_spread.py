"""e010 Phase 1: per-day net PnL of the FROZEN credit spread (PREREG §2 +
amendment 2). Structure-agnostic reuse of e004's loaders and path sim:
SELL ATM put + BUY ATM-150 put at the 09:15 open (ATM from the day's open —
observable at entry; no wall input anywhere in the structure), fixed IV from
the t-1 straddle (e004's `_iv_from_straddle`, computed from the prior-day
partition exactly as e004 does), exits SL 0.35x credit / target 0.70x credit
/ EOD (e004's BEAR fractions applied to the credit — the e005 condor
convention), friction from the certified model.

Output: artifacts/credit_labels.csv (date, exit_reason, bars_held,
gross_pnl, friction, net_pnl, win) — the gate's label. A day with candles
but missing prior-partition context is dropped (same as e004), which the
gate treats as a non-tradable day.

Run: python -m experiments.e010_ml_gate.label_spread
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from core.feeds.intraday import available_dates, load_intraday_candles
from core.friction.zerodha import OptionLeg, calculate_friction
from experiments.common.lots import lot_for_date
import experiments.e004_intraday_replay.replay_intraday as e4
from experiments.e004_intraday_replay.replay_intraday import (
    SPREAD_OFFSET, _iv_from_straddle, _load_prior_partition, _price_leg)

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
OUT = ARTIFACTS / "credit_labels.csv"

BEAR_EXIT = (0.35, 0.70)  # frozen (PREREG §2): (stop_frac, target_frac) of credit


def _credit_legs(day_open: float) -> list[dict]:
    atm = round(day_open / 50.0) * 50.0
    return [{"strike": atm, "is_call": False, "action": "SELL"},
            {"strike": atm - SPREAD_OFFSET, "is_call": False, "action": "BUY"}]


def _simulate_credit_day(candles: pd.DataFrame, lot: int, iv: float, dte: float) -> dict:
    """e004's simulate_day mtm walk with e010's credit legs and the exit
    fractions applied to the credit (e005 condor convention)."""
    legs = _credit_legs(float(candles.iloc[0]["open"]))
    qty = lot
    prices_open = [_price_leg(candles.iloc[0]["open"], l["strike"], l["is_call"], iv, dte) for l in legs]
    short_outlay = sum(p * qty for p, l in zip(prices_open, legs) if l["action"] == "SELL")
    long_outlay = sum(p * qty for p, l in zip(prices_open, legs) if l["action"] == "BUY")
    credit = short_outlay - long_outlay
    stop_level = -BEAR_EXIT[0] * credit
    target_level = BEAR_EXIT[1] * credit

    exit_reason, exit_bar, gross_pnl = "EOD", None, 0.0
    for i, (_, bar) in enumerate(candles.iterrows()):
        prices = [_price_leg(bar["close"], l["strike"], l["is_call"], iv, dte) for l in legs]
        mtm = sum((p - p0) * qty for p, p0, l in zip(prices, prices_open, legs) if l["action"] == "BUY") \
            + sum((p0 - p) * qty for p, p0, l in zip(prices, prices_open, legs) if l["action"] == "SELL")
        if mtm <= stop_level:
            exit_reason, exit_bar, gross_pnl = "STOP", i + 1, mtm
            break
        if mtm >= target_level:
            exit_reason, exit_bar, gross_pnl = "TARGET", i+1, mtm
            break
    else:
        gross_pnl = mtm  # EOD exit at the last bar's close
    olegs = [OptionLeg(strike=float(l["strike"]), option_type="CE" if l["is_call"] else "PE",
                       action=l["action"], entry_price=float(p), lot_size=qty)
             for l, p in zip(legs, prices_open)]
    fric = calculate_friction(olegs)
    return {"exit_reason": exit_reason, "bars_held": exit_bar or 0,
            "gross_pnl": round(gross_pnl, 2), "friction": fric.total_rupees,
            "net_pnl": round(gross_pnl - fric.total_rupees, 2),
            "win": bool(gross_pnl - fric.total_rupees > 0)}


def run(historical_dir, intraday_dir=None, limit=None) -> pd.DataFrame:
    """e004.run_days' per-day context verbatim; only the legs differ."""
    import argparse
    dates = available_dates(intraday_dir)
    if limit:
        dates = dates[-limit:]
    rows: list[dict] = []
    for d in dates:
        try:
            candles = load_intraday_candles(d, data_dir=intraday_dir)
        except FileNotFoundError:
            continue
        lot = lot_for_date(d)
        prior_df = _load_prior_partition(historical_dir, d)
        if prior_df is None:
            continue
        nifty = prior_df[prior_df["symbol"] == "NIFTY"]
        fut = nifty[nifty["instrument"].isin(["FUTIDX", "IDF"])]
        opts = nifty[nifty["instrument"].isin(["OPTIDX", "IDO"])]
        if fut.empty or opts.empty:
            continue
        expiries = sorted([(e4.parse_date(str(e).strip()), str(e).strip())
                           for e in opts["expiry"].unique() if e4._safe_parse(e) is not None])
        if not expiries:
            continue
        chain = opts[opts["expiry"] == expiries[0][1]]
        pe, ce = chain[chain["option_type"] == "PE"], chain[chain["option_type"] == "CE"]
        if pe.empty or ce.empty:
            continue
        prev_close = float(fut.iloc[0]["close"])
        atm_t1 = round(prev_close / 50.0) * 50.0
        atm_ce, atm_pe = ce[ce["strike"] == atm_t1], pe[pe["strike"] == atm_t1]
        if atm_ce.empty or atm_pe.empty:
            continue
        straddle = float(atm_ce.iloc[0]["close"]) + float(atm_pe.iloc[0]["close"])
        dte = max((expiries[0][0] - d).days, 0.5)
        iv = _iv_from_straddle(prev_close, atm_t1, dte, straddle)
        rows.append({"date": d.isoformat(),
                     **_simulate_credit_day(candles, lot, iv, dte)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import argparse

    import config

    ap = argparse.ArgumentParser(description="e010 frozen credit-spread labels")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    df = run(config.HISTORICAL_DATA_DIR, limit=args.limit)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(json.dumps({"days": len(df), "net": round(df.net_pnl.sum(), 0),
                      "wr": round(float(df.win.mean()), 3) if len(df) else 0}, indent=1))
