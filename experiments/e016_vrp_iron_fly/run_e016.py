"""E016: VRP-Gated Iron Fly — defined-risk wings on the E011 delta-hedged straddle.

Runs the frozen adaptive-width rule (PREREG.md) across all 293 E011 signaled sessions
via the extended `simulate_session`, plus a fixed-width diagnostic table (not used for
selection). Compares against the frozen naked-straddle artifacts.
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.feeds.intraday import load_intraday_candles
from experiments.common.lots import lot_for_date
from experiments.e011_vrp_delta_hedge.replay_vrp import simulate_session
from experiments.e011_vrp_delta_hedge.volatility import load_or_compute_volatility

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARTIFACTS = HERE / "artifacts"
E011_CSV = ROOT / "experiments" / "e011_vrp_delta_hedge" / "artifacts" / "vrp_daily.csv"
YEARS = 5.7

FROZEN = {
    "width_sigma": 1.0,
    "width_floor_pts": 150.0,
    "strike_grid": 50.0,
    "delta_threshold": 0.15,
    "slippage_opt_pts": 1.5,
    "slippage_fut_pts": 0.5,
    "diagnostic_widths_pts": [100.0, 150.0, 200.0, 250.0, 300.0],
    "kill_max_dd_inr": 16000.0,
    "kill_min_ev_inr": 500.0,
    "kill_min_total_vs_e011": 0.40,
}


def adaptive_width(sigma_gk_10d_t1: float, dte_days: float, spot: float) -> float:
    """Frozen width rule: max(150, 1.0 * sigma_gk * sqrt(DTE/365) * S), 50-pt grid."""
    sigma = max(float(sigma_gk_10d_t1), 0.05)
    w = FROZEN["width_sigma"] * sigma * math.sqrt(max(dte_days, 0.5) / 365.0) * float(spot)
    w = max(w, FROZEN["width_floor_pts"])
    return round(w / FROZEN["strike_grid"]) * FROZEN["strike_grid"]


def _summarize(df: pd.DataFrame, label: str) -> Dict:
    n = len(df)
    total = float(df["net_pnl"].sum())
    ev = total / n if n else 0.0
    gp = float(df[df["net_pnl"] > 0]["net_pnl"].sum())
    gl = abs(float(df[df["net_pnl"] < 0]["net_pnl"].sum()))
    std = float(df["net_pnl"].std())
    sharpe = (ev / std) * math.sqrt(n / YEARS) if n and std > 0 else 0.0
    cum = df.sort_values("date")["net_pnl"].cumsum()
    max_dd = float((cum - cum.cummax()).min()) if n else 0.0
    return {
        "label": label,
        "sessions": n,
        "total_net_pnl": round(total, 2),
        "net_ev_per_trade": round(ev, 2),
        "win_rate": round(float((df["net_pnl"] > 0).mean()), 4) if n else 0.0,
        "profit_factor": round(gp / gl, 2) if gl > 0 else None,
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_inr": round(max_dd, 2),
        "max_drawdown_pct_of_2l": round(abs(max_dd) / 2000.0, 2),
        "avg_hedges_per_day": round(float(df["hedge_trades"].mean()), 2) if n else 0.0,
        "avg_friction_per_trade": round(float(df["friction"].mean()), 2) if n else 0.0,
    }


def _run(sessions: pd.DataFrame, wing_fn, label: str, candle_cache: Dict) -> Tuple[pd.DataFrame, Dict]:
    records: List[Dict] = []
    for _, row in sessions.iterrows():
        d = row["date"]
        if d not in candle_cache:
            try:
                candle_cache[d] = load_intraday_candles(d)
            except Exception:
                candle_cache[d] = None
        candles = candle_cache[d]
        if candles is None:
            continue
        iv = float(row["iv_t1"]) if pd.notna(row["iv_t1"]) else 0.15
        dte = float(row["dte_days"]) if pd.notna(row["dte_days"]) else 4.0
        lot = lot_for_date(d)
        spot1 = float(candles.iloc[1]["open"])
        w_ce, w_pe = wing_fn(row, dte, spot1, lot)
        rec = simulate_session(
            trade_date=d,
            candles=candles,
            iv_t1=iv,
            dte_days=dte,
            threshold=FROZEN["delta_threshold"],
            slippage_opt=FROZEN["slippage_opt_pts"],
            slippage_fut=FROZEN["slippage_fut_pts"],
            wing_offset_ce=w_ce,
            wing_offset_pe=w_pe,
        )
        if rec is None:
            continue
        rec["wing_ce_pts"] = w_ce
        rec["wing_pe_pts"] = w_pe
        records.append(rec)
    df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
    return df, _summarize(df, label)


def run_e016() -> Tuple[pd.DataFrame, pd.DataFrame, Dict]:
    vrp = pd.read_csv(E011_CSV)
    vrp["date"] = pd.to_datetime(vrp["date"]).dt.date
    vdf = load_or_compute_volatility().set_index("date")

    def frozen_rule(row, dte, spot1, lot):
        sigma = float(row["iv_t1"])  # placeholder; replaced below with sigma lookup
        # Strict t-1 discipline: sigma_gk_10d_t1 comes from the frozen volatility frame.
        sigma = float(vdf.loc[row["date"], "sigma_gk_10d_t1"])
        w = adaptive_width(sigma, dte, spot1)
        return w, w

    candle_cache: Dict[date, Optional[pd.DataFrame]] = {}
    df_fly, sum_fly = _run(vrp, frozen_rule, "E016_ADAPTIVE_FLY", candle_cache)

    diagnostics = {}
    for w in FROZEN["diagnostic_widths_pts"]:
        _, sum_w = _run(vrp, lambda row, dte, spot1, lot, W=w: (W, W), f"FLY_W{int(w)}", candle_cache)
        diagnostics[f"w{int(w)}_pts"] = sum_w

    e011_published = pd.read_csv(E011_CSV)
    sum_naked = _summarize(e011_published.assign(**{"hedge_trades": e011_published["hedge_trades"]}), "E011_NAKED_PUBLISHED")

    # Kill gates (PREREG section 3)
    e011_total = float(e011_published["net_pnl"].sum())
    gates = {
        "gate1_max_dd_le_16k": {
            "bar": FROZEN["kill_max_dd_inr"],
            "observed": sum_fly["max_drawdown_inr"],
            "pass": bool(abs(sum_fly["max_drawdown_inr"]) <= FROZEN["kill_max_dd_inr"]),
        },
        "gate2_ev_ge_500": {
            "bar": FROZEN["kill_min_ev_inr"],
            "observed": sum_fly["net_ev_per_trade"],
            "pass": bool(sum_fly["net_ev_per_trade"] >= FROZEN["kill_min_ev_inr"]),
        },
        "gate3_total_ge_40pct_e011": {
            "bar": round(FROZEN["kill_min_total_vs_e011"] * e011_total, 2),
            "observed": sum_fly["total_net_pnl"],
            "ratio_vs_e011": round(sum_fly["total_net_pnl"] / e011_total, 4),
            "pass": bool(sum_fly["total_net_pnl"] >= FROZEN["kill_min_total_vs_e011"] * e011_total),
        },
    }

    metrics = {
        "frozen_params": FROZEN,
        "e011_naked_published": sum_naked,
        "e016_adaptive_fly": sum_fly,
        "width_diagnostics": diagnostics,
        "gates": gates,
        "all_gates_pass": bool(all(g["pass"] for g in gates.values())),
    }

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    df_fly.to_csv(ARTIFACTS / "fly_daily.csv", index=False)
    with open(ARTIFACTS / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    return df_fly, e011_published, metrics


if __name__ == "__main__":
    fly, naked, m = run_e016()
    import pprint

    print("E016 VRP Iron Fly — metrics")
    pprint.pprint(m)
