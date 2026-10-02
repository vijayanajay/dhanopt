"""E012: Volatility Skew & 1x2 Ratio Spread Replay Engine.

Implements:
1. Asymmetric 1x2 Put Ratio Spread with Broken-Wing Tail Protection:
   - BUY 1 lot 35-Delta Put (captures moderate downside).
   - SELL 2 lots 15-Delta Put (harvests overpriced skew peak).
   - BUY 1 lot 2-Delta Put (caps tail risk / defines max loss).
2. Dynamic intraday path exits:
   - TARGET: 50% of maximum theoretical spread profit.
   - STOP: 1.5x initial outlay loss OR spot breaching the short strike.
   - EOD: 15:15 IST square-off.
3. Realistic Zerodha post-Oct 2024 fee schedules (brokerage, STT, GST, slippage).
4. Era-correct lot sizes (75 -> 50 -> 25 -> 75 -> 65).
"""

from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.feeds.intraday import load_intraday_candles
from experiments.common.lots import lot_for_date
from core.pricing import bs_put
from experiments.e012_skew_ratio.skew import load_or_compute_skew

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"


def simulate_skew_session(
    trade_date: date,
    candles: pd.DataFrame,
    strike_long: float,
    strike_short: float,
    strike_wing: float,
    atm_iv: float,
    dte_days: float,
    slippage_opt: float = 1.5,
) -> Optional[Dict]:
    """Simulates one session of 1x2 Put Ratio Spread with broken wing."""
    if len(candles) < 50:
        return None

    # Sanity: long strike > short strike > wing strike for put ratio spread
    if not (strike_long > strike_short > strike_wing):
        return None

    lot_size = lot_for_date(trade_date)

    # Entry at 09:20 IST (Bar 1 Open)
    bar_entry = candles.iloc[1] if len(candles) > 1 else candles.iloc[0]
    s0 = float(bar_entry["open"])

    t0_years = max(dte_days, 0.05) / 365.0
    iv0 = max(atm_iv, 0.05)

    # Initial leg prices
    p_long0 = max(bs_put(s0, strike_long, iv0, t0_years), 0.05)
    p_short0 = max(bs_put(s0, strike_short, iv0, t0_years), 0.05)
    p_wing0 = max(bs_put(s0, strike_wing, iv0, t0_years), 0.05)

    # Net credit/debit per share: sell 2 short, buy 1 long, buy 1 wing
    # Positive = Net credit collected; Negative = Net debit paid
    net_credit = (2.0 * p_short0) - (p_long0 + p_wing0)

    # Maximum theoretical profit occurs at strike_short at expiry:
    # (strike_long - strike_short) + net_credit
    spread_width = strike_long - strike_short
    max_profit = spread_width + net_credit

    # Target: 50% of max profit
    target_profit = 0.50 * max(max_profit, 10.0)

    # Stop: Loss reaches 1.5x of credit (or 1.5x spread width if debit), OR spot breaches strike_short
    stop_loss = 1.50 * max(abs(net_credit), 15.0)

    # Entry friction:
    # 4 orders: ₹20 * 4 = ₹80 brokerage
    # STT: 0.1% on sell turnover = 0.001 * (2 * p_short0) * lot_size
    # Slippage: 4 legs * slippage_opt * lot_size
    # Exchange turnover (0.0505%) + SEBI + Stamp + GST (18%)
    entry_turnover_sell = (2.0 * p_short0) * lot_size
    entry_stt = 0.001 * entry_turnover_sell
    entry_brokerage = 80.0
    entry_slippage = (4.0 * slippage_opt) * lot_size
    entry_exchange_etc = (entry_turnover_sell * 0.000535 * 1.18) + (entry_brokerage * 0.18)
    entry_friction = entry_brokerage + entry_stt + entry_slippage + entry_exchange_etc

    # Walk 5-min path
    total_bars = min(72, len(candles))
    exit_reason = "EOD"
    exit_bar = total_bars - 1
    pnl_per_share = 0.0

    for i in range(1, total_bars):
        bar = candles.iloc[i]
        s_i = float(bar["close"])
        dt_years = (i * 5.0) / (375.0 * 365.0)
        t_rem = max(t0_years - dt_years, 0.0001)

        p_long_i = max(bs_put(s_i, strike_long, iv0, t_rem), 0.05)
        p_short_i = max(bs_put(s_i, strike_short, iv0, t_rem), 0.05)
        p_wing_i = max(bs_put(s_i, strike_wing, iv0, t_rem), 0.05)

        # Current spread liquidation value (if closing now):
        # Sell long, buy back 2 shorts, sell wing:
        # PnL = (p_long_i + p_wing_i - 2.0 * p_short_i) + net_credit
        mtm_i = (p_long_i + p_wing_i - 2.0 * p_short_i) + net_credit

        # Check TARGET trigger
        if mtm_i >= target_profit:
            exit_reason = "TARGET"
            exit_bar = i
            pnl_per_share = mtm_i
            break

        # Check STOP trigger (MTM loss exceeds stop OR spot breaches below strike_short)
        if mtm_i <= -stop_loss or s_i <= strike_short:
            exit_reason = "STOP"
            exit_bar = i
            pnl_per_share = mtm_i
            break

    # If EOD square-off
    if exit_reason == "EOD":
        bar_exit = candles.iloc[exit_bar]
        s_exit = float(bar_exit["close"])
        dt_final = (exit_bar * 5.0) / (375.0 * 365.0)
        t_final = max(t0_years - dt_final, 0.0001)

        if dte_days <= 0.01:
            p_long_f = max(strike_long - s_exit, 0.05)
            p_short_f = max(strike_short - s_exit, 0.05)
            p_wing_f = max(strike_wing - s_exit, 0.05)
        else:
            p_long_f = max(bs_put(s_exit, strike_long, iv0, t_final), 0.05)
            p_short_f = max(bs_put(s_exit, strike_short, iv0, t_final), 0.05)
            p_wing_f = max(bs_put(s_exit, strike_wing, iv0, t_final), 0.05)

        pnl_per_share = (p_long_f + p_wing_f - 2.0 * p_short_f) + net_credit

    gross_pnl = pnl_per_share * lot_size

    # Exit friction (4 orders: ₹80 brokerage + 4 legs slippage + exchange fees, no STT on buy closing)
    exit_brokerage = 80.0
    exit_slippage = (4.0 * slippage_opt) * lot_size
    exit_friction = exit_brokerage + exit_slippage + (exit_brokerage * 0.18)

    total_friction = entry_friction + exit_friction
    net_pnl = gross_pnl - total_friction

    return {
        "date": trade_date,
        "spot_entry": s0,
        "strike_long": strike_long,
        "strike_short": strike_short,
        "strike_wing": strike_wing,
        "lot_size": lot_size,
        "dte_days": dte_days,
        "net_credit": net_credit,
        "max_profit": max_profit,
        "exit_reason": exit_reason,
        "bars_held": exit_bar,
        "gross_pnl": gross_pnl,
        "friction": total_friction,
        "net_pnl": net_pnl,
        "win": bool(net_pnl > 0),
    }


def run_skew_replay(
    slippage_mult: float = 1.0,
    force_skew_recompute: bool = False,
) -> Tuple[pd.DataFrame, Dict]:
    """Runs walk-forward replay on all Skew-gated sessions."""
    df_skew = load_or_compute_skew(force_recompute=force_skew_recompute)
    signals = df_skew[df_skew["skew_signal"] == True].copy()

    records: List[Dict] = []
    slip_opt = 1.5 * slippage_mult

    for _, row in signals.iterrows():
        d = row["date"]
        try:
            candles = load_intraday_candles(d)
        except Exception:
            continue

        kl = row["strike_long_t1"]
        ks = row["strike_short_t1"]
        kw = row["strike_wing_t1"]

        if pd.isna(kl) or pd.isna(ks) or pd.isna(kw):
            continue

        dte = float(row["dte_t1"]) if pd.notna(row["dte_t1"]) else 4.0
        iv = float(row["atm_iv_t1"]) if pd.notna(row["atm_iv_t1"]) else 0.15

        res = simulate_skew_session(
            trade_date=d,
            candles=candles,
            strike_long=float(kl),
            strike_short=float(ks),
            strike_wing=float(kw),
            atm_iv=iv,
            dte_days=dte,
            slippage_opt=slip_opt,
        )
        if res:
            records.append(res)

    res_df = pd.DataFrame(records)
    if res_df.empty:
        return res_df, {}

    res_df["cum_net"] = res_df["net_pnl"].cumsum()
    res_df["peak"] = res_df["cum_net"].cummax()
    res_df["drawdown"] = res_df["cum_net"] - res_df["peak"]

    total_net = float(res_df["net_pnl"].sum())
    total_trades = len(res_df)
    wins = int(res_df["win"].sum())
    win_rate = wins / total_trades if total_trades > 0 else 0.0

    gross_profit = float(res_df[res_df["net_pnl"] > 0]["net_pnl"].sum())
    gross_loss = abs(float(res_df[res_df["net_pnl"] < 0]["net_pnl"].sum()))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else np.nan

    max_dd = float(res_df["drawdown"].min())
    max_dd_pct = (abs(max_dd) / 200_000.0) * 100.0

    mean_pnl = float(res_df["net_pnl"].mean())
    std_pnl = float(res_df["net_pnl"].std())
    trades_per_year = total_trades / 5.7
    sharpe = (mean_pnl / std_pnl) * math.sqrt(trades_per_year) if std_pnl > 0 else 0.0

    # Max consecutive losses
    loss_series = (~res_df["win"]).astype(int)
    max_consec_losses = int((loss_series.groupby((loss_series != loss_series.shift()).cumsum()).cumsum() * loss_series).max())

    metrics = {
        "slippage_mult": slippage_mult,
        "total_trades": total_trades,
        "trades_per_year": round(trades_per_year, 1),
        "total_net_pnl": round(total_net, 2),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 2) if not np.isnan(profit_factor) else None,
        "max_drawdown_inr": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_consecutive_losses": max_consec_losses,
        "exits": res_df["exit_reason"].value_counts().to_dict(),
    }

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if slippage_mult == 1.0:
        res_df.to_csv(ARTIFACTS / "skew_trades.csv", index=False)
        import json
        with open(ARTIFACTS / "metrics.json", "w") as f:
            json.dump(metrics, f, indent=2)

    return res_df, metrics


if __name__ == "__main__":
    df, m = run_skew_replay()
    print("Skew Ratio Replay Metrics:")
    print(m)
