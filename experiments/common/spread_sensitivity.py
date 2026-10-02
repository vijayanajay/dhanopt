"""Spread-width sensitivity sweep on the two frozen TAKER books (E011, E013).

Question: the published net-PnL figures assume a 1.5 pts/leg taker slippage (half-spread
proxy). How sensitive is each book's net EV to that single point estimate?

Method — exact reconstruction, no re-simulation. Both frozen engines charge the option
slippage as a linear friction line, `n_leg_orders x p x lot`, and keep gross PnL free of
that line, so for any per-leg slippage `p`:

    net_i(p) = gross_i - [friction_i + (p - 1.5) * n_leg_orders * lot_i]

Leg-order semantics: E011 charges 4 leg-orders/session (2 entry + 2 exit); E013 charges 4
(entry side only — its frozen exit convention prices at intrinsic with no spread term).

Outputs: `spread_sensitivity.json` written into each strategy's own artifacts directory
with the full net-EV-vs-spread curve and the exact breakeven spread:
    p* = 1.5 + total_net_published / (n_leg_orders * sum(lot))
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Sequence

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
YEARS = 5.7

SPREADS_PTS: Sequence[float] = (1.0, 1.5, 2.0, 2.5, 3.0)
BASELINE_PTS = 1.5

E011_CSV = ROOT / "experiments" / "e011_vrp_delta_hedge" / "artifacts" / "vrp_daily.csv"
E013_CSV = ROOT / "experiments" / "e013_0dte_pin" / "artifacts" / "pin_daily.csv"


def reconstruct_net(df: pd.DataFrame, p: float, n_leg_orders: int) -> pd.Series:
    """Exact per-session net PnL at per-leg slippage p from the frozen artifact columns."""
    return df["gross"] - (df["friction"] + (p - BASELINE_PTS) * n_leg_orders * df["lot"])


def _curve_point(net: pd.Series, p: float) -> Dict:
    n = len(net)
    total = float(net.sum())
    ev = total / n
    gp = float(net[net > 0].sum())
    gl = abs(float(net[net < 0].sum()))
    std = float(net.std())
    sharpe = (ev / std) * math.sqrt(n / YEARS) if std > 0 else 0.0
    cum = net.cumsum()
    return {
        "half_spread_pts": p,
        "total_net_pnl": round(total, 2),
        "net_ev_per_trade": round(ev, 2),
        "win_rate": round(float((net > 0).mean()), 4),
        "profit_factor": round(gp / gl, 2) if gl > 0 else None,
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_inr": round(float((cum - cum.cummax()).min()), 2),
    }


def sweep_book(df: pd.DataFrame, gross_col: str, n_leg_orders: int) -> Dict:
    """Full sweep + exact breakeven for one frozen book (dates must be pre-sorted)."""
    frame = pd.DataFrame(
        {"gross": df[gross_col].astype(float), "friction": df["friction"].astype(float), "lot": df["lot_size"].astype(int)}
    )
    curve = [_curve_point(reconstruct_net(frame, p, n_leg_orders), p) for p in SPREADS_PTS]
    baseline_net = reconstruct_net(frame, BASELINE_PTS, n_leg_orders)
    denom = n_leg_orders * int(frame["lot"].sum())
    breakeven = BASELINE_PTS + float(baseline_net.sum()) / denom if denom else None
    return {
        "baseline_half_spread_pts": BASELINE_PTS,
        "leg_orders_per_session": n_leg_orders,
        "sessions": len(frame),
        "breakeven_half_spread_pts": round(breakeven, 3) if breakeven is not None else None,
        "sweep": curve,
        "method": "net(p) = gross - [friction_published + (p - 1.5) * n_leg_orders * lot]; exact linear reconstruction, no re-simulation",
    }


def run_sweep() -> Dict[str, Dict]:
    vrp = pd.read_csv(E011_CSV).sort_values("date").reset_index(drop=True)
    pin = pd.read_csv(E013_CSV)
    pin = pin[pin["trade_type"] == "PIN_IRON_FLY"].sort_values("date").reset_index(drop=True)

    out = {
        "e011_vrp_straddle": sweep_book(vrp, gross_col="total_gross_pnl", n_leg_orders=4),
        "e013_pin_iron_fly": sweep_book(pin, gross_col="gross_pnl", n_leg_orders=4),
    }

    for key, rel in (
        ("e011_vrp_straddle", "experiments/e011_vrp_delta_hedge/artifacts"),
        ("e013_pin_iron_fly", "experiments/e013_0dte_pin/artifacts"),
    ):
        path = ROOT / rel / "spread_sensitivity.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out[key], f, indent=2)

    return out


if __name__ == "__main__":
    res = run_sweep()
    import pprint

    print("Spread-width sensitivity (per-leg taker slippage, pts)")
    pprint.pprint(res)
