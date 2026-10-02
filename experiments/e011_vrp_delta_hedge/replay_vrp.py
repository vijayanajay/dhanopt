"""E011: Variance Risk Premium (VRP) & Dynamic Delta-Neutral Replay.

Implements:
1. Dynamic Delta-Hedging of short ATM straddles along the 5-min path.
2. Threshold-based rebalancing (|net_delta| >= 0.15) executed strictly at bar t+1 Open.
3. Realistic Zerodha post-Oct 2024 fee schedules (brokerage, STT, GST, slippage).
4. Era-correct historical lot sizes (75 -> 50 -> 25 -> 75 -> 65).
"""

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

from core.collateral import CollateralManager
from core.feeds.intraday import load_intraday_candles
from core.pricing import bs_call, bs_put, delta_ce, delta_pe
from experiments.common.lots import lot_for_date
from experiments.e011_vrp_delta_hedge.volatility import get_vrp_signal, load_or_compute_volatility

ARTIFACTS = HERE / "artifacts"


def simulate_session(
    trade_date: date,
    candles: pd.DataFrame,
    iv_t1: float,
    dte_days: float,
    threshold: float = 0.15,
    slippage_opt: float = 1.5,
    slippage_fut: float = 0.5,
    wing_offset: Optional[float] = None,
    wing_offset_ce: Optional[float] = None,
    wing_offset_pe: Optional[float] = None,
    entry_bar: int = 1,
    strike_override: Optional[float] = None,
    entry_fill_ce: Optional[float] = None,
    entry_fill_pe: Optional[float] = None,
    exit_fill_ce: Optional[float] = None,
    exit_fill_pe: Optional[float] = None,
) -> Optional[Dict]:
    """Simulates one trading session of dynamic delta-hedged ATM straddle.

    Passive-execution seam (E014 TCA): when entry_fill_* / exit_fill_* are provided,
    those actual fill prices replace the Black-Scholes mids and the corresponding
    point-slippage line is dropped (the spread lives in the fill price instead).
    Defaults reproduce the published E011 behavior exactly.

    Wing support (E016): wing_offset (or per-side wing_offset_ce / wing_offset_pe)
    converts the naked short straddle into an Iron Fly — 1 lot of CE wing bought at
    strike + offset and PE wing at strike - offset. Defaults keep the naked straddle.
    """
    if len(candles) < 50:
        return None
    if entry_bar >= min(72, len(candles)):
        return None

    lot_size = lot_for_date(trade_date)

    # Entry at 09:20 IST (Bar 1 Open) by default; E014 maker entries may fill later.
    bar_entry = candles.iloc[entry_bar] if len(candles) > entry_bar else candles.iloc[0]
    s0 = float(bar_entry["open"])
    strike = round(s0 / 50.0) * 50.0 if strike_override is None else float(strike_override)
    maker_entry = entry_fill_ce is not None and entry_fill_pe is not None
    maker_exit = exit_fill_ce is not None and exit_fill_pe is not None

    # Iron-fly wings (E016). The straddle-margin gate below is an upper bound for the
    # fly (long wings only reduce required margin), so it stays fail-closed as-is.
    w_off_ce = wing_offset_ce if wing_offset_ce is not None else wing_offset
    w_off_pe = wing_offset_pe if wing_offset_pe is not None else wing_offset
    is_fly = w_off_ce is not None and w_off_pe is not None and w_off_ce > 0 and w_off_pe > 0
    if is_fly:
        k_ce_wing = strike + float(w_off_ce)
        k_pe_wing = strike - float(w_off_pe)

    # Phase 1 Collateral & Capital Gate: Ensure 1-lot straddle margin is approved under ₹2L bankroll
    straddle_margin_req = CollateralManager.estimate_straddle_margin(spot=s0, lot_size=lot_size)
    approved, _, _ = CollateralManager().check_margin_requirement(straddle_margin_req)
    if not approved:
        return None

    t0_years = max(dte_days, 0.05) / 365.0
    iv0 = max(iv_t1, 0.05)

    if is_fly:
        w_ce0 = max(bs_call(s0, k_ce_wing, iv0, t0_years), 0.05)
        w_pe0 = max(bs_put(s0, k_pe_wing, iv0, t0_years), 0.05)
    if maker_entry:
        c0 = max(float(entry_fill_ce), 0.05)
        p0 = max(float(entry_fill_pe), 0.05)
    else:
        c0 = max(bs_call(s0, strike, iv0, t0_years), 0.05)
        p0 = max(bs_put(s0, strike, iv0, t0_years), 0.05)
    initial_credit = (c0 + p0) - (w_ce0 + w_pe0) if is_fly else (c0 + p0)

    # Initial options friction (net-credit turnover basis, as published):
    # STT: 0.1% on sell turnover; brokerage ₹20/leg; slippage 1.5 pts/leg.
    # Exchange turnover (0.0505%) + SEBI (₹10/Cr) + GST (18%) on charges.
    n_entry_legs = 4 if is_fly else 2
    opt_sell_turnover = initial_credit * lot_size
    opt_stt = 0.001 * opt_sell_turnover
    opt_brokerage = 20.0 * n_entry_legs
    opt_slippage_cost = 0.0 if maker_entry else (n_entry_legs * slippage_opt) * lot_size
    opt_exchange_etc = opt_sell_turnover * (0.000505 + 0.00003) * 1.18 + opt_brokerage * 0.18
    entry_friction = opt_brokerage + opt_stt + opt_slippage_cost + opt_exchange_etc

    # Path simulation along 5-min bars (entry bar to Bar 71, ~09:20 to 15:15 IST)
    total_bars = min(72, len(candles))
    current_hedge = 0.0  # Fraction of lot size in futures
    hedge_cash_flows: List[float] = []
    hedge_friction_total = 0.0
    hedge_trades = 0

    pending_hedge_order: Optional[float] = None  # Delta adjustment to fill at t+1 Open

    for i in range(entry_bar, total_bars):
        bar = candles.iloc[i]

        # Execute any pending hedge order at Bar i Open (t+1 Fill Rule)
        if pending_hedge_order is not None and abs(pending_hedge_order) > 1e-4:
            dh = pending_hedge_order
            open_px = float(bar["open"])

            # Buying futures pays ask (open + slippage), selling receives bid (open - slippage)
            fill_px = (open_px + slippage_fut) if dh > 0 else (open_px - slippage_fut)
            cash_flow = -dh * fill_px * lot_size
            hedge_cash_flows.append(cash_flow)

            # Futures friction: ₹20 brokerage + GST + STT (0.02% on sell)
            fut_turnover = abs(dh) * fill_px * lot_size
            fut_stt = (0.0002 * fut_turnover) if dh < 0 else 0.0
            fut_exchange = fut_turnover * 0.000019 * 1.18
            fut_cost = 20.0 * 1.18 + fut_stt + fut_exchange
            hedge_friction_total += fut_cost
            hedge_trades += 1

            current_hedge += dh
            pending_hedge_order = None

        # Calculate Greeks at Bar i Close
        spot_close = float(bar["close"])
        dt_years = (i * 5.0) / (375.0 * 365.0)
        t_rem = max(t0_years - dt_years, 0.0001)

        d_ce = delta_ce(spot_close, strike, iv0, t_rem)
        d_pe = delta_pe(spot_close, strike, iv0, t_rem)

        # Portfolio delta from short options: -(d_ce + d_pe)
        delta_opt = -(d_ce + d_pe)
        if is_fly:
            # Long wings add back their own delta, offsetting short gamma away from ATM.
            delta_opt += delta_ce(spot_close, k_ce_wing, iv0, t_rem) + delta_pe(
                spot_close, k_pe_wing, iv0, t_rem
            )
        net_delta = delta_opt + current_hedge

        # Check threshold rebalancing trigger for NEXT bar (i < total_bars - 1)
        if i < total_bars - 1:
            if abs(net_delta) >= threshold:
                # Trigger order to reset net delta to 0: target dh = -net_delta
                pending_hedge_order = -net_delta

    # Exit at 15:15 IST (last bar)
    last_bar = candles.iloc[total_bars - 1]
    spot_exit = float(last_bar["close"])
    dt_final = (total_bars * 5.0) / (375.0 * 365.0)
    t_final = max(t0_years - dt_final, 0.0001)

    if maker_exit:
        c_exit = max(float(exit_fill_ce), 0.05)
        p_exit = max(float(exit_fill_pe), 0.05)
    elif dte_days <= 0.01:
        # Expiry day settlement at intrinsic value
        c_exit = max(spot_exit - strike, 0.05)
        p_exit = max(strike - spot_exit, 0.05)
    else:
        c_exit = max(bs_call(spot_exit, strike, iv0, t_final), 0.05)
        p_exit = max(bs_put(spot_exit, strike, iv0, t_final), 0.05)

    if is_fly:
        if dte_days <= 0.01:
            w_ce1 = max(spot_exit - k_ce_wing, 0.05)
            w_pe1 = max(k_pe_wing - spot_exit, 0.05)
        else:
            w_ce1 = max(bs_call(spot_exit, k_ce_wing, iv0, t_final), 0.05)
            w_pe1 = max(bs_put(spot_exit, k_pe_wing, iv0, t_final), 0.05)
    else:
        w_ce1 = w_pe1 = 0.0
    final_debit = (c_exit + p_exit) - (w_ce1 + w_pe1)
    opt_gross_pnl = (initial_credit - final_debit) * lot_size

    # Option exit friction (buy to close: ₹20/leg brokerage + 1.5 pts/leg slippage, no STT on buy)
    n_exit_legs = 4 if is_fly else 2
    opt_exit_turnover = final_debit * lot_size
    opt_exit_brokerage = 20.0 * n_exit_legs
    opt_exit_slippage = 0.0 if maker_exit else (n_exit_legs * slippage_opt) * lot_size
    opt_exit_exchange = opt_exit_turnover * 0.000505 * 1.18 + opt_exit_brokerage * 0.18
    exit_friction = opt_exit_brokerage + opt_exit_slippage + opt_exit_exchange

    # Square off any outstanding futures hedge at 15:15 Close
    if abs(current_hedge) > 1e-4:
        fut_exit_px = (spot_exit - slippage_fut) if current_hedge > 0 else (spot_exit + slippage_fut)
        close_flow = current_hedge * fut_exit_px * lot_size
        hedge_cash_flows.append(close_flow)

        fut_turnover = abs(current_hedge) * fut_exit_px * lot_size
        fut_stt = (0.0002 * fut_turnover) if current_hedge > 0 else 0.0
        fut_cost = 20.0 * 1.18 + fut_stt + fut_turnover * 0.000019 * 1.18
        hedge_friction_total += fut_cost
        hedge_trades += 1

    hedge_gross_pnl = sum(hedge_cash_flows)
    total_gross_pnl = opt_gross_pnl + hedge_gross_pnl
    total_friction = entry_friction + exit_friction + hedge_friction_total
    net_pnl = total_gross_pnl - total_friction

    return {
        "date": trade_date,
        "entry_bar": entry_bar,
        "spot_entry": s0,
        "spot_exit": spot_exit,
        "strike": strike,
        "lot_size": lot_size,
        "dte_days": dte_days,
        "iv_t1": iv_t1,
        "initial_credit": initial_credit,
        "wing_offset_ce": float(w_off_ce) if is_fly else None,
        "wing_offset_pe": float(w_off_pe) if is_fly else None,
        "final_debit": final_debit,
        "opt_gross_pnl": opt_gross_pnl,
        "hedge_gross_pnl": hedge_gross_pnl,
        "hedge_trades": hedge_trades,
        "total_gross_pnl": total_gross_pnl,
        "friction": total_friction,
        "net_pnl": net_pnl,
        "win": bool(net_pnl > 0),
    }


def run_vrp_replay(
    slippage_mult: float = 1.0,
    force_vol_recompute: bool = False,
    threshold: float = 0.15,
    estimator: str = "gk",
    window: int = 10,
    signal_series: Optional[pd.Series] = None,
    candle_cache: Optional[Dict[date, pd.DataFrame]] = None,
) -> Tuple[pd.DataFrame, Dict]:
    """Runs full walk-forward replay on all VRP-gated sessions."""
    vdf = load_or_compute_volatility(force_recompute=force_vol_recompute)
    if signal_series is not None:
        signals = vdf[signal_series == True].copy()
    elif estimator.lower() == "gk" and window == 10:
        signals = vdf[vdf["vrp_signal"] == True].copy()
    else:
        sig = get_vrp_signal(vdf, estimator=estimator, window=window)
        signals = vdf[sig == True].copy()

    records: List[Dict] = []
    slip_opt = 1.5 * slippage_mult
    slip_fut = 0.5 * slippage_mult

    for _, row in signals.iterrows():
        d = row["date"]
        if candle_cache is not None and d in candle_cache:
            candles = candle_cache[d]
        else:
            try:
                candles = load_intraday_candles(d)
                if candle_cache is not None:
                    candle_cache[d] = candles
            except Exception:
                continue

        dte = float(row["dte_t1"]) if pd.notna(row["dte_t1"]) else 4.0
        iv = float(row["iv_atm_t1"]) if pd.notna(row["iv_atm_t1"]) else 0.15

        res = simulate_session(
            trade_date=d,
            candles=candles,
            iv_t1=iv,
            dte_days=dte,
            threshold=threshold,
            slippage_opt=slip_opt,
            slippage_fut=slip_fut,
        )
        if res:
            records.append(res)

    res_df = pd.DataFrame(records)
    if res_df.empty:
        return res_df, {}

    # Performance metrics
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

    # Annualized Sharpe (assuming 252 days/yr)
    mean_pnl = float(res_df["net_pnl"].mean())
    std_pnl = float(res_df["net_pnl"].std())
    trades_per_year = total_trades / 5.7  # 5.7 years
    sharpe = (mean_pnl / std_pnl) * math.sqrt(trades_per_year) if std_pnl > 0 else 0.0

    avg_hedges = float(res_df["hedge_trades"].mean()) if total_trades > 0 else 0.0
    avg_friction = float(res_df["friction"].mean()) if total_trades > 0 else 0.0

    metrics = {
        "estimator": estimator,
        "window": window,
        "threshold": threshold,
        "slippage_mult": slippage_mult,
        "total_trades": total_trades,
        "trades_per_year": round(trades_per_year, 1),
        "total_net_pnl": round(total_net, 2),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 2) if not np.isnan(profit_factor) else None,
        "max_drawdown_inr": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "sharpe_ratio": round(sharpe, 2),
        "avg_hedges_per_day": round(avg_hedges, 1),
        "avg_friction_per_trade": round(avg_friction, 2),
    }

    # Save artifacts only for baseline frozen run
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if (
        slippage_mult == 1.0
        and threshold == 0.15
        and estimator.lower() == "gk"
        and window == 10
        and signal_series is None
    ):
        res_df.to_csv(ARTIFACTS / "vrp_daily.csv", index=False)
        import json
        with open(ARTIFACTS / "metrics.json", "w") as f:
            json.dump(metrics, f, indent=2)

    return res_df, metrics


if __name__ == "__main__":
    df, m = run_vrp_replay()
    print("VRP Replay Metrics:")
    print(m)
