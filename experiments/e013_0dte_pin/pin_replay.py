"""E013: 0DTE Expiry Microstructure & Pin Dynamics Replay Engine.

Implements:
1. 12:30 IST Session Classification via Expansion Ratio:
   Expansion Ratio = (High_{09:15-12:30} - Low_{09:15-12:30}) / (09:20 ATM Straddle)
2. Strategy A (Pin Harvest - Iron Butterfly):
   - Triggered when Expansion Ratio <= 0.65.
   - Entry strictly at 12:35 IST Open (Bar 40).
   - Sells ATM straddle + buys +/-150 wings. Held to 15:15 IST.
3. Strategy B (Gamma Breakout Follower):
   - Triggered when Expansion Ratio >= 1.20.
   - Entry strictly at 12:35 IST Open (Bar 40).
   - Directional debit spread in direction of morning trend. Held to 15:15 IST.
4. Observability Audit:
   - Measures leg availability within 5-min window from e008 rolling-API snapshot files.
"""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.feeds.bhavcopy import parse_date
from core.feeds.intraday import load_intraday_candles
from core.pricing import bs_call, bs_put
from experiments.common.lots import lot_for_date
from experiments.e011_vrp_delta_hedge.volatility import load_or_compute_volatility

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARTIFACTS = HERE / "artifacts"
WALLS_DIR = ROOT / "experiments" / "e008_wall_flip" / "artifacts" / "walls"


def audit_leg_observability(session_json_path: Path, atm_strike: float) -> bool:
    """Checks if ATM and +/-150 wing quotes are present within 5 mins of 12:35 IST."""
    if not session_json_path.exists():
        return False
    try:
        with open(session_json_path, "r", encoding="utf-8") as fp:
            d = json.load(fp)
    except Exception:
        return False

    bars = d.get("bars", [])
    if len(bars) < 41:
        return False

    # Check Bar 40 (12:35 IST)
    b40 = bars[40]
    chain = b40.get("chain", [])
    target_strikes = {atm_strike, atm_strike + 150.0, atm_strike - 150.0}

    ce_found = {k: False for k in target_strikes}
    pe_found = {k: False for k in target_strikes}

    for item in chain:
        st = item.get("strike")
        side = item.get("side")
        if st in target_strikes:
            if side == "CE":
                ce_found[st] = True
            elif side == "PE":
                pe_found[st] = True

    return all(ce_found.values()) and all(pe_found.values())


def run_pin_replay() -> Tuple[pd.DataFrame, Dict]:
    """Runs full replay of 0DTE Pin Harvest and Gamma Breakout across 576 sessions."""
    vdf = load_or_compute_volatility().set_index("date")

    json_files = sorted(WALLS_DIR.glob("*.json"))
    records: List[Dict] = []
    observable_checks: List[bool] = []

    for f in json_files:
        d_str = f.stem
        d = parse_date(d_str)
        if d not in vdf.index:
            continue
        row = vdf.loc[d]

        try:
            candles = load_intraday_candles(d)
        except Exception:
            continue

        if len(candles) < 72:
            continue

        # Morning range from 09:15 to 12:30 (Bars 0 to 39)
        morning = candles.iloc[:40]
        high_1230 = float(morning["high"].max())
        low_1230 = float(morning["low"].min())
        range_1230 = high_1230 - low_1230

        s_0920 = float(candles.iloc[1]["open"])
        iv = float(row["iv_atm_t1"]) if pd.notna(row["iv_atm_t1"]) else 0.15
        dte = float(row["dte_t1"]) if pd.notna(row["dte_t1"]) else 1.0
        t0 = max(dte, 0.05) / 365.0

        atm_0920 = round(s_0920 / 50.0) * 50.0
        c0 = bs_call(s_0920, atm_0920, iv, t0)
        p0 = bs_put(s_0920, atm_0920, iv, t0)
        straddle_0920 = c0 + p0
        if straddle_0920 <= 5.0:
            continue

        expansion_ratio = range_1230 / straddle_0920

        # Bar 40 (12:35 Open) is Entry
        s_entry = float(candles.iloc[40]["open"])
        atm_entry = round(s_entry / 50.0) * 50.0
        lot_size = lot_for_date(d)

        # Check observability in e008 JSON
        is_obs = audit_leg_observability(f, atm_entry)
        observable_checks.append(is_obs)

        # Remaining time to expiry at 12:35: ~32 bars (160 mins = 0.426 trading days)
        t_entry = (0.426 / 365.0) if dte <= 0.01 else (dte - 0.5) / 365.0

        # Exit at 15:15 Close (Bar 71)
        s_exit = float(candles.iloc[71]["close"])

        trade_type = None
        gross_pnl = 0.0
        friction = 0.0

        if expansion_ratio <= 0.65:
            # Pin Harvest — Iron Butterfly
            trade_type = "PIN_IRON_FLY"
            k_atm = atm_entry
            k_ce_wing = atm_entry + 150.0
            k_pe_wing = atm_entry - 150.0

            # Entry prices
            ce_s0 = bs_call(s_entry, k_atm, iv, t_entry)
            pe_s0 = bs_put(s_entry, k_atm, iv, t_entry)
            ce_w0 = bs_call(s_entry, k_ce_wing, iv, t_entry)
            pe_w0 = bs_put(s_entry, k_pe_wing, iv, t_entry)
            credit = (ce_s0 + pe_s0) - (ce_w0 + pe_w0)

            # Exit prices at 15:15
            if dte <= 0.01:
                ce_s1 = max(s_exit - k_atm, 0.0)
                pe_s1 = max(k_atm - s_exit, 0.0)
                ce_w1 = max(s_exit - k_ce_wing, 0.0)
                pe_w1 = max(k_pe_wing - s_exit, 0.0)
            else:
                t_exit = 0.0001
                ce_s1 = bs_call(s_exit, k_atm, iv, t_exit)
                pe_s1 = bs_put(s_exit, k_atm, iv, t_exit)
                ce_w1 = bs_call(s_exit, k_ce_wing, iv, t_exit)
                pe_w1 = bs_put(s_exit, k_pe_wing, iv, t_exit)

            debit = (ce_s1 + pe_s1) - (ce_w1 + pe_w1)
            gross_pnl = (credit - debit) * lot_size

            # 4 legs friction: ₹80 entry + ₹80 exit + 0.1% STT on sell turnover + 6.0 pts slippage
            sell_turnover = (ce_s0 + pe_s0) * lot_size
            friction = 160.0 + (0.001 * sell_turnover) + (6.0 * lot_size) + (160.0 * 0.18)

        elif expansion_ratio >= 1.20:
            # Gamma Breakout Follower
            trade_type = "BREAKOUT"
            is_bull = (s_entry >= s_0920)
            if is_bull:
                k_long = atm_entry
                k_short = atm_entry + 150.0
                debit0 = bs_call(s_entry, k_long, iv, t_entry) - bs_call(s_entry, k_short, iv, t_entry)
                if dte <= 0.01:
                    payoff1 = max(s_exit - k_long, 0.0) - max(s_exit - k_short, 0.0)
                else:
                    payoff1 = bs_call(s_exit, k_long, iv, 0.0001) - bs_call(s_exit, k_short, iv, 0.0001)
            else:
                k_long = atm_entry
                k_short = atm_entry - 150.0
                debit0 = bs_put(s_entry, k_long, iv, t_entry) - bs_put(s_entry, k_short, iv, t_entry)
                if dte <= 0.01:
                    payoff1 = max(k_long - s_exit, 0.0) - max(k_short - s_exit, 0.0)
                else:
                    payoff1 = bs_put(s_exit, k_long, iv, 0.0001) - bs_put(s_exit, k_short, iv, 0.0001)

            gross_pnl = (payoff1 - debit0) * lot_size
            friction = 80.0 + (3.0 * lot_size) + (80.0 * 0.18)

        if trade_type:
            net_pnl = gross_pnl - friction
            records.append({
                "date": d,
                "trade_type": trade_type,
                "expansion_ratio": round(expansion_ratio, 3),
                "spot_0920": s_0920,
                "spot_entry": s_entry,
                "spot_exit": s_exit,
                "atm_entry": atm_entry,
                "lot_size": lot_size,
                "gross_pnl": round(gross_pnl, 2),
                "friction": round(friction, 2),
                "net_pnl": round(net_pnl, 2),
                "win": bool(net_pnl > 0),
            })

    res_df = pd.DataFrame(records)
    obs_rate = (sum(observable_checks) / len(observable_checks)) if observable_checks else 0.0

    # Separate metrics for PIN_IRON_FLY and BREAKOUT
    pin_df = res_df[res_df["trade_type"] == "PIN_IRON_FLY"]
    brk_df = res_df[res_df["trade_type"] == "BREAKOUT"]

    def calc_group_stats(df_sub: pd.DataFrame) -> Dict:
        if df_sub.empty:
            return {}
        n = len(df_sub)
        net_tot = float(df_sub["net_pnl"].sum())
        ev = net_tot / n
        wr = float(df_sub["win"].mean())
        gp = float(df_sub[df_sub["net_pnl"] > 0]["net_pnl"].sum())
        gl = abs(float(df_sub[df_sub["net_pnl"] < 0]["net_pnl"].sum()))
        pf = (gp / gl) if gl > 0 else np.nan
        std_pnl = float(df_sub["net_pnl"].std())
        sharpe = (ev / std_pnl) * math.sqrt(n / 5.7) if std_pnl > 0 else 0.0

        cum = df_sub["net_pnl"].cumsum()
        max_dd = float((cum - cum.cummax()).min())

        return {
            "trades": n,
            "trades_per_year": round(n / 5.7, 1),
            "total_net_pnl": round(net_tot, 2),
            "net_ev_per_trade": round(ev, 2),
            "win_rate": round(wr, 4),
            "profit_factor": round(pf, 2) if not np.isnan(pf) else None,
            "max_drawdown_inr": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
        }

    metrics = {
        "total_evaluated_sessions": len(json_files),
        "total_traded_sessions": len(res_df),
        "fill_feasibility_in_e008_data": round(obs_rate, 4),
        "pin_iron_fly": calc_group_stats(pin_df),
        "gamma_breakout": calc_group_stats(brk_df),
    }

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    res_df.to_csv(ARTIFACTS / "pin_daily.csv", index=False)
    with open(ARTIFACTS / "metrics.json", "w") as fp:
        json.dump(metrics, fp, indent=2)

    return res_df, metrics


if __name__ == "__main__":
    df, m = run_pin_replay()
    print("0DTE Pin Replay Metrics:")
    import pprint
    pprint.pprint(m)
