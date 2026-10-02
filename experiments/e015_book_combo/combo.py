"""E015: Book Composition Analysis — E011 VRP Straddle × E013 Pin Fly on one ₹2L account.

Pure arithmetic over the two frozen published artifacts (no re-simulation, no new
parameters):

1. **Overlap:** how often both books trade the same session, vs the independent-session
   expectation, and the same-day PnL correlation between the books.
2. **Combined book:** date-merged PnL series (sum where both trade) with joint profit
   factor, Sharpe (repo convention) and joint max drawdown.
3. **Capital utilization:** per-session SPAN+Exposure margin via the Phase 1 engine
   (`CollateralManager.estimate_straddle_margin`). For the Pin Fly this is an explicit
   UPPER BOUND — its long wings only reduce required margin — so capacity breaches are
   computed against the conservative case. Usable margin: ₹1,82,000 (Phase 1).

Descriptive analysis of frozen results; no kill gates, nothing tuned.
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from core.collateral import CollateralManager
from experiments.e011_vrp_delta_hedge.volatility import load_or_compute_volatility

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARTIFACTS = HERE / "artifacts"
E011_CSV = ROOT / "experiments" / "e011_vrp_delta_hedge" / "artifacts" / "vrp_daily.csv"
E013_CSV = ROOT / "experiments" / "e013_0dte_pin" / "artifacts" / "pin_daily.csv"
YEARS = 5.7
USABLE_MARGIN = CollateralManager().total_usable_margin  # ₹1,82,000 (Phase 1)


def _book_metrics(df: pd.DataFrame, pnl_col: str = "net_pnl") -> Dict:
    n = len(df)
    if n == 0:
        return {}
    total = float(df[pnl_col].sum())
    ev = total / n
    gp = float(df[df[pnl_col] > 0][pnl_col].sum())
    gl = abs(float(df[df[pnl_col] < 0][pnl_col].sum()))
    std = float(df[pnl_col].std())
    sharpe = (ev / std) * math.sqrt(n / YEARS) if std > 0 else 0.0
    cum = df[pnl_col].cumsum()
    dd = float((cum - cum.cummax()).min())
    return {
        "sessions": n,
        "total_net_pnl": round(total, 2),
        "net_ev_per_trade": round(ev, 2),
        "win_rate": round(float((df[pnl_col] > 0).mean()), 4),
        "profit_factor": round(gp / gl, 2) if gl > 0 else None,
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_inr": round(dd, 2),
        "max_drawdown_pct_of_2l": round(abs(dd) / 2000.0, 2),
    }


def _margin_upper_bound(row: pd.Series) -> float:
    """SPAN+Exposure upper-bound margin for one session of the book (Phase 1 engine)."""
    return CollateralManager.estimate_straddle_margin(spot=float(row["spot_entry"]), lot_size=int(row["lot_size"]))


def run_combo() -> Tuple[pd.DataFrame, Dict]:
    vrp = pd.read_csv(E011_CSV)
    pin = pd.read_csv(E013_CSV)
    pin = pin[pin["trade_type"] == "PIN_IRON_FLY"].copy()

    for df in (vrp, pin):
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df.sort_values("date", inplace=True)
        df["margin_ub"] = df.apply(_margin_upper_bound, axis=1)

    n_sessions = len(load_or_compute_volatility())  # session calendar 2021-2026
    d11 = set(vrp["date"])
    d13 = set(pin["date"])
    overlap = sorted(d11 & d13)
    expected_overlap = len(d11) * len(d13) / n_sessions

    # Same-day PnL correlation on overlap sessions.
    both = (
        vrp[vrp["date"].isin(overlap)][["date", "net_pnl", "margin_ub"]]
        .merge(
            pin[pin["date"].isin(overlap)][["date", "net_pnl", "margin_ub"]],
            on="date",
            suffixes=("_e011", "_e013"),
        )
        .sort_values("date")
    )
    corr = float(both["net_pnl_e011"].corr(both["net_pnl_e013"])) if len(both) > 1 else float("nan")

    # Combined daily series over the union of trade dates.
    rows: List[Dict] = []
    for d in sorted(d11 | d13):
        p11 = float(vrp.loc[vrp["date"] == d, "net_pnl"].sum())
        p13 = float(pin.loc[pin["date"] == d, "net_pnl"].sum())
        m11 = float(vrp.loc[vrp["date"] == d, "margin_ub"].sum())
        m13 = float(pin.loc[pin["date"] == d, "margin_ub"].sum())
        books = (1 if d in d11 else 0) + (1 if d in d13 else 0)
        rows.append(
            {
                "date": d,
                "n_books": books,
                "e011_pnl": p11,
                "e013_pnl": p13,
                "net_pnl": p11 + p13,
                "margin_used_ub": m11 + m13,
                "margin_breach_ub": bool(m11 + m13 > USABLE_MARGIN),
            }
        )
    combined = pd.DataFrame(rows)
    combined["cum_net"] = combined["net_pnl"].cumsum()

    yearly = (
        combined.assign(year=combined["date"].map(lambda d: d.year))
        .groupby("year")
        .agg(
            trade_days=("net_pnl", "size"),
            overlap_days=("n_books", lambda s: int((s == 2).sum())),
            e011_net=("e011_pnl", "sum"),
            e013_net=("e013_pnl", "sum"),
            combined_net=("net_pnl", "sum"),
        )
        .round(2)
        .reset_index()
        .to_dict(orient="records")
    )

    metrics: Dict = {
        "session_calendar_days": n_sessions,
        "books": {
            "e011_vrp_straddle": _book_metrics(vrp),
            "e013_pin_iron_fly": _book_metrics(pin),
        },
        "overlap": {
            "e011_sessions": len(d11),
            "e013_sessions": len(d13),
            "overlap_sessions": len(overlap),
            "expected_overlap_if_independent": round(expected_overlap, 1),
            "overlap_ratio_observed": round(len(overlap) / max(len(d13), 1), 4),
            "same_day_pnl_correlation": round(corr, 4) if not math.isnan(corr) else None,
            "same_day_joint_win_rate": round(float((both["net_pnl_e011"] > 0).sum() + (both["net_pnl_e013"] > 0).sum()) / (2 * len(both)), 4)
            if len(both)
            else None,
        },
        "combined_book": _book_metrics(combined),
        "capital": {
            "usable_margin_inr": USABLE_MARGIN,
            "margin_model": "Phase 1 estimate_straddle_margin (7.84% of contract value); E013 = upper bound (wings only reduce it)",
            "avg_margin_used_per_trade_day_ub": round(float(combined["margin_used_ub"].mean()), 2),
            "max_concurrent_margin_ub": round(float(combined["margin_used_ub"].max()), 2),
            "capacity_breach_days_ub": int(combined["margin_breach_ub"].sum()),
            "overlap_days_breached_ub": int(combined[(combined["n_books"] == 2)]["margin_breach_ub"].sum()),
            "margin_day_utilization_pct": round(
                float(combined["margin_used_ub"].sum()) / (USABLE_MARGIN * n_sessions) * 100.0, 2
            ),
            "avg_utilization_on_trade_days_pct": round(
                float(combined["margin_used_ub"].mean()) / USABLE_MARGIN * 100.0, 2
            ),
        },
        "yearly": yearly,
    }

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    combined.to_csv(ARTIFACTS / "combo_daily.csv", index=False)
    with open(ARTIFACTS / "combo_metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    return combined, metrics


if __name__ == "__main__":
    df, m = run_combo()
    import pprint

    print("E015 Book Combination — metrics")
    pprint.pprint(m)
