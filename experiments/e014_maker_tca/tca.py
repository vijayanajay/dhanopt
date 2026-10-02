"""E014: Execution Microstructure & Limit Order TCA — Maker vs Taker.

Re-runs the two validated strategies under identical timing and three execution arms:
- TAKER:     every leg crosses the spread (reproduces E011/E013 accounting exactly).
- MAKER:     all-or-none passive basket — every entry leg must fill passively inside the
             entry window or the session is NO TRADE (missed alpha counted).
- HYBRID:    passive entry where possible, unfilled legs cross at the first bar after the
             window (E013 only; E011's hedge schedule depends on entry timing).

Passive fills are simulated with core/execution/maker.py against Black-Scholes mid paths
built from the 5-minute spot store. All parameters are frozen in PREREG.md; nothing here
is tuned after observing results.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from core.execution.maker import (
    Bar,
    Fill,
    PassiveOrder,
    QueueFillSimulator,
    apply_adverse_selection,
    fill_in_window,
    passive_limit_price,
    reference_moves,
)
from core.feeds.intraday import load_intraday_candles
from core.pricing import bs_call, bs_put
from experiments.common.lots import lot_for_date
from experiments.e011_vrp_delta_hedge.replay_vrp import simulate_session
from experiments.e011_vrp_delta_hedge.volatility import load_or_compute_volatility

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARTIFACTS = HERE / "artifacts"
E011_ARTIFACTS = ROOT / "experiments" / "e011_vrp_delta_hedge" / "artifacts"
E013_ARTIFACTS = ROOT / "experiments" / "e013_0dte_pin" / "artifacts"

# ---------------------------------------------------------------------------
# Frozen parameters (PREREG.md)
# ---------------------------------------------------------------------------
FROZEN = {
    "option_half_spread_pts": 1.5,
    "tick_size": 0.05,
    "volume_multiple": 3.0,
    "adverse_threshold_pct": 0.002,
    "entry_window_bars": 6,
    "exit_post_bar": 68,
    "exit_window_bars": [69, 70, 71],
    "forced_exit_bar": 71,
    "e013_entry_bar": 40,
    "e011_entry_bar": 1,
    "pin_wing_offset_pts": 150.0,
    "vrp_threshold": 0.15,
    "taker_slippage_opt_pts": 1.5,
    "taker_slippage_fut_pts": 0.5,
    "maker_gate_fill_rate": 0.50,
    "maker_gate_aggregate_ratio": 0.60,
    "years": 5.7,
}
HALF = FROZEN["option_half_spread_pts"]
TICK = FROZEN["tick_size"]
EXIT_WINDOW = tuple(FROZEN["exit_window_bars"])

ARMS_E013 = ("TAKER", "MAKER", "HYBRID")
ARMS_E011 = ("TAKER", "MAKER")


# ---------------------------------------------------------------------------
# Black-Scholes mid helpers (shared with E011)
# ---------------------------------------------------------------------------
def _opt_mid(spot: float, strike: float, opt_type: str, iv: float, t: float) -> float:
    v = bs_call(spot, strike, iv, t) if opt_type == "CE" else bs_put(spot, strike, iv, t)
    return max(v, 0.05)


def _option_mid_bars(
    candles: pd.DataFrame,
    strike: float,
    opt_type: str,
    iv: float,
    t_at,
    bar_indices: Sequence[int],
) -> Dict[int, Bar]:
    """Modeled option mid path per bar: BS on the underlying OHLC; volume=None (fail-closed)."""
    out: Dict[int, Bar] = {}
    for i in bar_indices:
        row = candles.iloc[i]
        t = t_at(i)
        v_open = _opt_mid(float(row["open"]), strike, opt_type, iv, t)
        v_high = _opt_mid(float(row["high"]), strike, opt_type, iv, t)
        v_low = _opt_mid(float(row["low"]), strike, opt_type, iv, t)
        v_close = _opt_mid(float(row["close"]), strike, opt_type, iv, t)
        out[i] = Bar(
            open=v_open,
            high=max(v_high, v_low),
            low=min(v_high, v_low),
            close=v_close,
            volume=None,
        )
    return out


def _try_fill_leg(
    side: str,
    mid_at_post: float,
    bars: Dict[int, Bar],
    window: Sequence[int],
    qty: int,
    tag: str,
    sim: QueueFillSimulator,
) -> Optional[Fill]:
    """Posts one passive limit at bid+1tick / ask-1tick and rests it over the window."""
    bid = max(mid_at_post - HALF, TICK)
    ask = mid_at_post + HALF
    limit = passive_limit_price(bid, ask, side, TICK)
    order = PassiveOrder(side=side, limit_price=limit, quantity=qty, posted_bar=window[0] - 1, tag=tag)
    # Adverse-selection reprice reference = the taker alternative at posting: exactly the
    # captured spread improvement (spread - tick) is stripped, nothing else (PREREG 2.5).
    taker_at_post = _taker_cross_price(mid_at_post, side)
    return fill_in_window(order, bars, window, sim, {b: taker_at_post for b in window})


def _taker_cross_price(mid: float, side: str) -> float:
    """Crossing price for a leg order (buy pays ask, sell receives bid); floor at one tick."""
    if side == "BUY":
        return mid + HALF
    return max(mid - HALF, TICK)


def _adjust_fills(
    passive_fills: Dict[str, Fill],
    bars_by_leg: Dict[str, Dict[int, Bar]],
) -> Dict[str, Tuple[Fill, float, bool, float]]:
    """Per-leg adverse-selection strip against the leg's OWN modeled mid path (PREREG 2.5).

    Returns leg -> (raw fill, adjusted price, flagged, penalty_rupees).
    """
    out: Dict[str, Tuple[Fill, float, bool, float]] = {}
    for n, f in passive_fills.items():
        leg_bars = bars_by_leg[n]
        leg_moves = reference_moves(
            {i: (leg_bars[i].open, leg_bars[i].close) for i in leg_bars}
        )
        (adj,), events = apply_adverse_selection([f], leg_moves, FROZEN["adverse_threshold_pct"])
        penalty = events[0].penalty_rupees if events else 0.0
        out[n] = (f, adj.fill_price, bool(events), penalty)
    return out


# ---------------------------------------------------------------------------
# E013 Pin Harvest Iron Fly
# ---------------------------------------------------------------------------
def _e013_exit_mids(candles: pd.DataFrame, atm: float, iv: float, dte: float) -> Dict[str, float]:
    """E013's frozen exit valuation at bar 71 close."""
    s_exit = float(candles.iloc[71]["close"])
    if dte <= 0.01:
        return {
            "sell_atm_ce": max(s_exit - atm, 0.0),
            "sell_atm_pe": max(atm - s_exit, 0.0),
            "buy_wing_ce": max(s_exit - (atm + 150.0), 0.0),
            "buy_wing_pe": max((atm - 150.0) - s_exit, 0.0),
        }
    t_exit = 0.0001
    return {
        "sell_atm_ce": bs_call(s_exit, atm, iv, t_exit),
        "sell_atm_pe": bs_put(s_exit, atm, iv, t_exit),
        "buy_wing_ce": bs_call(s_exit, atm + 150.0, iv, t_exit),
        "buy_wing_pe": bs_put(s_exit, atm - 150.0, iv, t_exit),
    }


def _e013_session(
    d: date,
    candles: pd.DataFrame,
    iv: float,
    dte: float,
    lot: int,
    arm: str,
    sim: QueueFillSimulator,
) -> Optional[Tuple[Dict, List[Dict]]]:
    if len(candles) < 72:
        return None

    s_entry = float(candles.iloc[40]["open"])
    atm = round(s_entry / 50.0) * 50.0
    t_entry = (0.426 / 365.0) if dte <= 0.01 else (dte - 0.5) / 365.0
    # Linear-in-bar-time interpolation between the two frozen E013 endpoints (PREREG 2.7).
    t_at = lambda i: t_entry + (0.0001 - t_entry) * (i - 40) / 31.0

    legs = [
        ("sell_atm_ce", "SELL", "CE", atm),
        ("sell_atm_pe", "SELL", "PE", atm),
        ("buy_wing_ce", "BUY", "CE", atm + 150.0),
        ("buy_wing_pe", "BUY", "PE", atm - 150.0),
    ]
    entry_mids = {n: _opt_mid(s_entry, k, ot, iv, t_entry) for n, _, ot, k in legs}
    fill_rows: List[Dict] = []

    def _row(leg: str, phase: str, side: str, passive: bool, crossed: bool,
             limit: float, raw: float, final: float, taker: float, bar: int,
             adverse: bool, penalty: float) -> Dict:
        return {
            "date": d, "strategy": "E013_PIN_FLY", "arm": arm, "leg": leg, "phase": phase,
            "side": side, "passive": passive, "crossed": crossed, "limit_price": round(limit, 4),
            "raw_fill_price": round(raw, 4), "fill_price": round(final, 4),
            "taker_price": round(taker, 4), "fill_bar": bar, "adverse": adverse,
            "penalty": round(penalty, 4),
        }

    # ---------------- Entry ----------------
    entry_fill: Dict[str, float] = {}
    entry_bars: Dict[str, int] = {}
    n_crossed_entry = 0
    bars: Dict[str, Dict[int, Bar]] = {}

    if arm == "TAKER":
        entry_fill = dict(entry_mids)
        entry_bars = {n: 40 for n, _, _, _ in legs}
        n_crossed_entry = 4
    else:
        bars = {n: _option_mid_bars(candles, k, ot, iv, t_at, range(40, 72)) for n, _, ot, k in legs}
        window = list(range(40, 40 + FROZEN["entry_window_bars"]))
        passive_fills: Dict[str, Fill] = {}
        for n, side, ot, k in legs:
            f = _try_fill_leg(side, entry_mids[n], bars[n], window, lot, n, sim)
            if f is not None:
                passive_fills[n] = f

        if arm == "MAKER" and len(passive_fills) < len(legs):
            # AON basket failed — NO TRADE. Record what did fill for per-leg statistics.
            for n, f in passive_fills.items():
                fill_rows.append(_row(n, "entry", f.side, True, False, f.limit_price,
                                      f.fill_price, f.fill_price, f.taker_price, f.fill_bar,
                                      False, 0.0))
            rec = {
                "date": d, "strategy": "E013_PIN_FLY", "arm": arm, "filled": False,
                "legs_filled": len(passive_fills), "entry_bar": None,
                "gross_pnl": 0.0, "friction": 0.0, "net_pnl": 0.0,
                "adverse_events": 0, "adverse_penalty": 0.0, "win": False,
            }
            return rec, fill_rows

        # Adverse-selection strip on passive entry fills (per-leg own mid path).
        for n, (f, adj_px, flagged, penalty) in _adjust_fills(passive_fills, bars).items():
            fill_rows.append(_row(n, "entry", f.side, True, False, f.limit_price, f.fill_price,
                                  adj_px, f.taker_price, f.fill_bar, flagged, penalty))
            entry_fill[n] = adj_px
            entry_bars[n] = f.fill_bar

        if arm == "HYBRID":
            for n, side, ot, k in legs:
                if n in entry_fill:
                    continue
                m46 = bars[n][40 + FROZEN["entry_window_bars"]].open
                px = _taker_cross_price(m46, side)
                entry_fill[n] = px
                entry_bars[n] = 40 + FROZEN["entry_window_bars"]
                n_crossed_entry += 1
                fill_rows.append(_row(n, "entry", side, False, True, px, px, px, px,
                                      40 + FROZEN["entry_window_bars"], False, 0.0))

    # ---------------- Exit ----------------
    exit_mids = _e013_exit_mids(candles, atm, iv, dte)
    exit_fill: Dict[str, float] = {}
    if arm == "TAKER":
        exit_fill = dict(exit_mids)
    else:
        exit_fills: Dict[str, Fill] = {}
        for n, side, ot, k in legs:
            close_side = "BUY" if side == "SELL" else "SELL"
            m68 = bars[n][FROZEN["exit_post_bar"]].close
            f = _try_fill_leg(close_side, m68, bars[n], EXIT_WINDOW, lot, n, sim)
            if f is None:
                px = _taker_cross_price(exit_mids[n], close_side)
                exit_fill[n] = px
                fill_rows.append(_row(n, "exit", close_side, False, True, px, px, px, px,
                                      FROZEN["forced_exit_bar"], False, 0.0))
            else:
                exit_fills[n] = f
        for n, (f, adj_px, flagged, penalty) in _adjust_fills(exit_fills, bars).items():
            fill_rows.append(_row(n, "exit", f.side, True, False, f.limit_price, f.fill_price,
                                  adj_px, f.taker_price, f.fill_bar, flagged, penalty))
            exit_fill[n] = adj_px

    # ---------------- PnL & friction ----------------
    gross = 0.0
    for n, side, ot, k in legs:
        e, x = entry_fill[n], exit_fill[n]
        gross += ((e - x) if side == "SELL" else (x - e)) * lot

    sell_turnover = (entry_fill["sell_atm_ce"] + entry_fill["sell_atm_pe"]) * lot
    slip_pts = 6.0 if arm == "TAKER" else 1.5 * n_crossed_entry
    friction = 160.0 + 0.001 * sell_turnover + slip_pts * lot + 160.0 * 0.18
    net = gross - friction

    adverse_events = sum(1 for r in fill_rows if r["adverse"])
    adverse_penalty = sum(r["penalty"] for r in fill_rows)
    rec = {
        "date": d, "strategy": "E013_PIN_FLY", "arm": arm, "filled": True,
        "legs_filled": len(legs), "entry_bar": max(entry_bars.values()),
        "gross_pnl": gross, "friction": friction, "net_pnl": net,
        "adverse_events": adverse_events, "adverse_penalty": adverse_penalty, "win": net > 0,
    }
    return rec, fill_rows


# ---------------------------------------------------------------------------
# E011 VRP delta-hedged straddle
# ---------------------------------------------------------------------------
def _e011_session(
    d: date,
    candles: pd.DataFrame,
    iv: float,
    dte: float,
    lot: int,
    arm: str,
    sim: QueueFillSimulator,
) -> Optional[Tuple[Dict, List[Dict]]]:
    if len(candles) < 50:
        return None
    total_bars = min(72, len(candles))
    if FROZEN["e011_entry_bar"] >= total_bars:
        return None

    if arm == "TAKER":
        rec = simulate_session(
            trade_date=d, candles=candles, iv_t1=iv, dte_days=dte,
            threshold=FROZEN["vrp_threshold"],
            slippage_opt=FROZEN["taker_slippage_opt_pts"],
            slippage_fut=FROZEN["taker_slippage_fut_pts"],
        )
        if rec is None:
            return None
        return (
            {
                "date": d, "strategy": "E011_VRP_STRADDLE", "arm": arm, "filled": True,
                "legs_filled": 2, "entry_bar": rec["entry_bar"],
                "gross_pnl": rec["total_gross_pnl"], "friction": rec["friction"],
                "net_pnl": rec["net_pnl"], "adverse_events": 0, "adverse_penalty": 0.0,
                "win": bool(rec["net_pnl"] > 0),
            },
            [],
        )

    # ---------------- MAKER arm: passive straddle entry + passive exit ----------------
    iv0 = max(iv, 0.05)
    t0 = max(dte, 0.05) / 365.0
    s0 = float(candles.iloc[1]["open"])
    strike = round(s0 / 50.0) * 50.0
    t_at = lambda i: max(t0 - i * 5.0 / (375.0 * 365.0), 0.0001)

    mid1 = {
        "CE": max(bs_call(s0, strike, iv0, t0), 0.05),
        "PE": max(bs_put(s0, strike, iv0, t0), 0.05),
    }
    bars = {ot: _option_mid_bars(candles, strike, ot, iv0, t_at, range(1, total_bars)) for ot in ("CE", "PE")}
    window = list(range(1, 1 + FROZEN["entry_window_bars"]))
    fills = {ot: _try_fill_leg("SELL", mid1[ot], bars[ot], window, lot, ot, sim) for ot in ("CE", "PE")}

    fill_rows: List[Dict] = []

    def _row(leg: str, phase: str, side: str, passive: bool, crossed: bool, limit: float,
             raw: float, final: float, taker: float, bar: int, adverse: bool, penalty: float) -> Dict:
        return {
            "date": d, "strategy": "E011_VRP_STRADDLE", "arm": arm, "leg": leg, "phase": phase,
            "side": side, "passive": passive, "crossed": crossed, "limit_price": round(limit, 4),
            "raw_fill_price": round(raw, 4), "fill_price": round(final, 4),
            "taker_price": round(taker, 4), "fill_bar": bar, "adverse": adverse,
            "penalty": round(penalty, 4),
        }

    if fills["CE"] is None or fills["PE"] is None:
        for ot, f in fills.items():
            if f is not None:
                fill_rows.append(_row(ot, "entry", "SELL", True, False, f.limit_price, f.fill_price,
                                      f.fill_price, f.taker_price, f.fill_bar, False, 0.0))
        rec = {
            "date": d, "strategy": "E011_VRP_STRADDLE", "arm": arm, "filled": False,
            "legs_filled": sum(1 for f in fills.values() if f is not None), "entry_bar": None,
            "gross_pnl": 0.0, "friction": 0.0, "net_pnl": 0.0,
            "adverse_events": 0, "adverse_penalty": 0.0, "win": False,
        }
        return rec, fill_rows

    entry_bar = max(fills["CE"].fill_bar, fills["PE"].fill_bar)
    order = ["CE", "PE"]
    entry_fill: Dict[str, float] = {}
    for ot, (f, adj_px, flagged, penalty) in _adjust_fills({ot: fills[ot] for ot in order}, bars).items():
        fill_rows.append(_row(ot, "entry", "SELL", True, False, f.limit_price, f.fill_price,
                              adj_px, f.taker_price, f.fill_bar, flagged, penalty))
        entry_fill[ot] = adj_px

    # Exit reference = the engine's own frozen exit valuation at bar 71 close.
    spot_exit = float(candles.iloc[total_bars - 1]["close"])
    t_final = max(t0 - total_bars * 5.0 / (375.0 * 365.0), 0.0001)
    if dte <= 0.01:
        base_exit = {"CE": max(spot_exit - strike, 0.05), "PE": max(strike - spot_exit, 0.05)}
    else:
        base_exit = {
            "CE": max(bs_call(spot_exit, strike, iv0, t_final), 0.05),
            "PE": max(bs_put(spot_exit, strike, iv0, t_final), 0.05),
        }

    exit_fill: Dict[str, float] = {}
    exit_passive: Dict[str, Fill] = {}
    for ot in order:
        m68 = bars[ot][FROZEN["exit_post_bar"]].close
        f = _try_fill_leg("BUY", m68, bars[ot], EXIT_WINDOW, lot, ot, sim)
        if f is None:
            px = _taker_cross_price(base_exit[ot], "BUY")
            exit_fill[ot] = px
            fill_rows.append(_row(ot, "exit", "BUY", False, True, px, px, px, px,
                                  FROZEN["forced_exit_bar"], False, 0.0))
        else:
            exit_passive[ot] = f
    for ot, (f, adj_px, flagged, penalty) in _adjust_fills(exit_passive, bars).items():
        fill_rows.append(_row(ot, "exit", "BUY", True, False, f.limit_price, f.fill_price,
                              adj_px, f.taker_price, f.fill_bar, flagged, penalty))
        exit_fill[ot] = adj_px

    rec = simulate_session(
        trade_date=d, candles=candles, iv_t1=iv, dte_days=dte,
        threshold=FROZEN["vrp_threshold"],
        slippage_opt=FROZEN["taker_slippage_opt_pts"],
        slippage_fut=FROZEN["taker_slippage_fut_pts"],
        entry_bar=entry_bar,
        strike_override=strike,
        entry_fill_ce=entry_fill["CE"],
        entry_fill_pe=entry_fill["PE"],
        exit_fill_ce=exit_fill["CE"],
        exit_fill_pe=exit_fill["PE"],
    )
    if rec is None:
        return None

    adverse_events = sum(1 for r in fill_rows if r["adverse"])
    adverse_penalty = sum(r["penalty"] for r in fill_rows)
    return (
        {
            "date": d, "strategy": "E011_VRP_STRADDLE", "arm": arm, "filled": True,
            "legs_filled": 2, "entry_bar": rec["entry_bar"],
            "gross_pnl": rec["total_gross_pnl"], "friction": rec["friction"],
            "net_pnl": rec["net_pnl"], "adverse_events": adverse_events,
            "adverse_penalty": adverse_penalty, "win": bool(rec["net_pnl"] > 0),
        },
        fill_rows,
    )


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def _summarize(trades: pd.DataFrame, strategy: str, arm: str, n_signaled: int) -> Dict:
    sub = trades[(trades["strategy"] == strategy) & (trades["arm"] == arm)].sort_values("date")
    filled = sub[sub["filled"]]
    n = len(filled)
    if n == 0:
        return {"sessions_filled": 0, "fill_rate": 0.0}
    total = float(filled["net_pnl"].sum())
    ev = total / n
    wr = float(filled["win"].mean())
    gp = float(filled[filled["net_pnl"] > 0]["net_pnl"].sum())
    gl = abs(float(filled[filled["net_pnl"] < 0]["net_pnl"].sum()))
    pf = (gp / gl) if gl > 0 else float("nan")
    std = float(filled["net_pnl"].std())
    sharpe = (ev / std) * np.sqrt(n / FROZEN["years"]) if std > 0 else 0.0
    cum = filled["net_pnl"].cumsum()
    max_dd = float((cum - cum.cummax()).min())
    return {
        "sessions_signaled": n_signaled,
        "sessions_filled": n,
        "fill_rate": round(n / n_signaled, 4),
        "total_net_pnl": round(total, 2),
        "net_ev_per_trade": round(ev, 2),
        "annual_net_pnl": round(total / FROZEN["years"], 2),
        "win_rate": round(wr, 4),
        "profit_factor": round(pf, 2) if not np.isnan(pf) else None,
        "max_drawdown_inr": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 2),
        "avg_friction_per_trade": round(float(filled["friction"].mean()), 2),
        "adverse_events": int(sub["adverse_events"].sum()),
        "adverse_penalty_rupees": round(float(sub["adverse_penalty"].sum()), 2),
        "legs_filled_total": int(sub["legs_filled"].sum()),
    }


def _leg_fill_rates(fills: pd.DataFrame, strategy: str, arm: str, sessions_signaled: int,
                    legs_per_session: int, phase: str) -> Dict[str, float]:
    sub = fills[(fills["strategy"] == strategy) & (fills["arm"] == arm) & (fills["phase"] == phase)]
    n = len(sub)
    if n == 0:
        return {}
    passive = float(sub["passive"].mean())
    return {"attempts": n, "passive_fills": int(sub["passive"].sum()), "passive_rate": round(passive, 4)}


def run_tca() -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    vdf = load_or_compute_volatility().set_index("date")

    pin = pd.read_csv(E013_ARTIFACTS / "pin_daily.csv")
    pin = pin[pin["trade_type"] == "PIN_IRON_FLY"].copy()
    pin["date"] = pd.to_datetime(pin["date"]).dt.date

    vrp = pd.read_csv(E011_ARTIFACTS / "vrp_daily.csv")
    vrp["date"] = pd.to_datetime(vrp["date"]).dt.date

    sim = QueueFillSimulator(FROZEN["volume_multiple"])
    candle_cache: Dict[date, Optional[pd.DataFrame]] = {}

    def _candles(d: date) -> Optional[pd.DataFrame]:
        if d not in candle_cache:
            try:
                candle_cache[d] = load_intraday_candles(d)
            except Exception:
                candle_cache[d] = None
        return candle_cache[d]

    trade_rows: List[Dict] = []
    fill_rows: List[Dict] = []

    # ---- E013 Pin Fly: TAKER / MAKER / HYBRID ----
    n_pin_skipped = 0
    for arm in ARMS_E013:
        for _, srow in pin.iterrows():
            d = srow["date"]
            candles = _candles(d)
            if candles is None:
                n_pin_skipped += 1
                continue
            iv = float(vdf.loc[d, "iv_atm_t1"]) if pd.notna(vdf.loc[d, "iv_atm_t1"]) else 0.15
            dte = float(vdf.loc[d, "dte_t1"]) if pd.notna(vdf.loc[d, "dte_t1"]) else 1.0
            lot = lot_for_date(d)
            out = _e013_session(d, candles, iv, dte, lot, arm, sim)
            if out is None:
                n_pin_skipped += 1
                continue
            rec, frows = out
            trade_rows.append(rec)
            fill_rows.extend(frows)

    # ---- E011 VRP straddle: TAKER / MAKER ----
    n_vrp_skipped = 0
    for arm in ARMS_E011:
        for _, srow in vrp.iterrows():
            d = srow["date"]
            candles = _candles(d)
            if candles is None:
                n_vrp_skipped += 1
                continue
            iv = float(srow["iv_t1"]) if pd.notna(srow["iv_t1"]) else 0.15
            dte = float(srow["dte_days"]) if pd.notna(srow["dte_days"]) else 4.0
            lot = lot_for_date(d)
            out = _e011_session(d, candles, iv, dte, lot, arm, sim)
            if out is None:
                n_vrp_skipped += 1
                continue
            rec, frows = out
            trade_rows.append(rec)
            fill_rows.extend(frows)

    trades = pd.DataFrame(trade_rows)
    fills = pd.DataFrame(fill_rows)

    # ---- Metrics & gates ----
    n_pin = len(pin)
    n_vrp = len(vrp)
    metrics: Dict = {
        "frozen_params": FROZEN,
        "sessions": {
            "e013_pin_signaled": n_pin,
            "e011_vrp_signaled": n_vrp,
            "e013_skipped_for_missing_candles": n_pin_skipped,
            "e011_skipped_for_missing_candles": n_vrp_skipped,
        },
        "e013_pin_iron_fly": {},
        "e011_vrp_straddle": {},
    }

    for strategy, n_signaled, arms, legs_per in (
        ("E013_PIN_FLY", n_pin, ARMS_E013, 4),
        ("E011_VRP_STRADDLE", n_vrp, ARMS_E011, 2),
    ):
        block: Dict = {}
        for arm in arms:
            block[arm] = _summarize(trades, strategy, arm, n_signaled)
            if arm != "TAKER":
                block[arm]["entry_leg_fill_stats"] = _leg_fill_rates(fills, strategy, arm, n_signaled, legs_per, "entry")
                block[arm]["exit_leg_fill_stats"] = _leg_fill_rates(fills, strategy, arm, n_signaled, legs_per, "exit")
        # Fill-selection diagnostic: taker EV on the maker-filled subset vs overall.
        taker = trades[(trades["strategy"] == strategy) & (trades["arm"] == "TAKER") & trades["filled"]]
        maker_dates = set(
            trades[(trades["strategy"] == strategy) & (trades["arm"] == "MAKER") & trades["filled"]]["date"]
        )
        subset = taker[taker["date"].isin(maker_dates)]
        if len(subset) > 0 and len(taker) > 0:
            block["fill_selection_effect"] = {
                "taker_ev_on_maker_filled_subset": round(float(subset["net_pnl"].mean()), 2),
                "taker_ev_on_all_sessions": round(float(taker["net_pnl"].mean()), 2),
                "delta": round(float(subset["net_pnl"].mean() - taker["net_pnl"].mean()), 2),
                "subset_sessions": len(subset),
            }
        # Gates on the MAKER arm.
        taker_m = block.get("TAKER", {})
        maker_m = block.get("MAKER", {})
        if maker_m.get("sessions_filled", 0) > 0:
            block["gates"] = {
                "gate1_fill_rate": {
                    "bar": FROZEN["maker_gate_fill_rate"],
                    "observed": maker_m["fill_rate"],
                    "pass": bool(maker_m["fill_rate"] >= FROZEN["maker_gate_fill_rate"]),
                },
                "gate2_per_trade_quality": {
                    "maker_ev": maker_m["net_ev_per_trade"],
                    "taker_ev": taker_m.get("net_ev_per_trade"),
                    "pass": bool(maker_m["net_ev_per_trade"] > taker_m.get("net_ev_per_trade", 0.0)),
                },
                "gate3_aggregate_survival": {
                    "bar_ratio": FROZEN["maker_gate_aggregate_ratio"],
                    "maker_total": maker_m["total_net_pnl"],
                    "taker_total": taker_m.get("total_net_pnl"),
                    "ratio": round(maker_m["total_net_pnl"] / taker_m["total_net_pnl"], 4)
                    if taker_m.get("total_net_pnl", 0.0) > 0
                    else None,
                    "pass": bool(
                        maker_m["total_net_pnl"] >= FROZEN["maker_gate_aggregate_ratio"] * taker_m.get("total_net_pnl", 0.0)
                    ),
                },
            }
        metrics[
            "e013_pin_iron_fly" if strategy == "E013_PIN_FLY" else "e011_vrp_straddle"
        ] = block

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    trades.to_csv(ARTIFACTS / "trades.csv", index=False)
    if not fills.empty:
        fills.to_csv(ARTIFACTS / "maker_fills.csv", index=False)
    with open(ARTIFACTS / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    return trades, fills, metrics


if __name__ == "__main__":
    trades_df, fills_df, m = run_tca()
    import pprint

    print("E014 Maker TCA — metrics")
    pprint.pprint(m)
