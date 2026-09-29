"""Expiry-only gate: restrict the exit-aware condor ML book to dte <= 1 (Kailash's proposal).

Same frozen gating frame and matched monthly count k (the rule's trade count); candidates
restricted to condor-simulable days with days-to-nearest-expiry <= 1, ML picks which of
those to take (underfill allowed — fewer trades, never forced trades). Compared against
the unrestricted condor-ML book, under both e005 exit configs.

Run: python -m experiments.e002_regime_models.expiry_gate
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from experiments.e002_regime_models import walkforward as W
from experiments.e002_regime_models.gating_exit_aware import e005_pnls
from experiments.e002_regime_models.gating_variants import CAPITAL, CONDOR, pick_slots
from experiments.e002_regime_models.walkforward import PNL_COLUMNS, RULE_TO_ARCH, _policy_stats

HERE = Path(__file__).resolve().parent
DTE = HERE / "artifacts_dte"


def expiry_only_condor(preds: pd.DataFrame, k_per_month: pd.Series) -> List[Tuple]:
    """Top-k condor slots restricted to dte<=1 days, one trade per day."""
    trades: List[Tuple] = []
    for _, month in preds.groupby(preds["date"].dt.to_period("M")):
        k = int(k_per_month.get(month["date"].dt.to_period("M").iloc[0], 0))
        if k <= 0:
            continue
        cand = month[(month["dte"] <= 1) & month[CONDOR.replace(" ", "_") + "_sim"]]
        trades += pick_slots(cand, k, lambda r, a: r[f"lgbm__{a}"], [CONDOR])
    return trades


def main() -> int:
    preds = pd.read_parquet(DTE / "oos_predictions.parquet")
    preds["date"] = pd.to_datetime(preds["date"])

    from experiments.e002_regime_models.walkforward_dte import expiry_calendar
    import config
    cal_df = expiry_calendar(config.HISTORICAL_DATA_DIR)
    preds = preds.merge(cal_df, on="date", how="left")
    print(f"dte attached: {preds['dte'].notna().sum()}/{len(preds)} rows | "
          f"dte<=1 days: {(preds['dte'] <= 1).sum()}")

    documented, drop_target = e005_pnls()
    key = preds["date"].dt.strftime("%Y-%m-%d")
    out = {}
    for name, series in (("documented", documented), ("drop_target", drop_target)):
        frame = preds.copy()
        frame[PNL_COLUMNS[CONDOR]] = key.map(series).fillna(frame[PNL_COLUMNS[CONDOR]])

        k_map = frame.groupby(frame["date"].dt.to_period("M")).apply(
            lambda m: (m["rule_signal"].isin(RULE_TO_ARCH)).sum())
        unrestricted = pick_slots_union(frame, k_map)
        restricted = expiry_only_condor(frame, k_map)

        for label, trades in (("unrestricted", unrestricted), ("expiry_only", restricted)):
            df = pd.DataFrame(trades, columns=["date", "archetype", "pnl"]).sort_values("date")
            s = _policy_stats(df["pnl"])
            s["max_dd_pct"] = round(s["max_dd"] / CAPITAL * 100, 1)
            out[f"{name}_{label}"] = s

    print(f"\n{'book':<28}{'n':>5}{'net':>11}{'avg':>8}{'wr':>7}{'pf':>7}{'maxDD':>9}{'DD%':>7}")
    for name in ("documented", "drop_target"):
        for label in ("unrestricted", "expiry_only"):
            r = out[f"{name}_{label}"]
            print(f"{name + ' ' + label:<28}{r['n']:>5}{r['net_total']:>11,.0f}{r['avg_net']:>8.1f}"
                  f"{r['win_rate']:>7.3f}{r['pf']:>7.2f}{r['max_dd']:>9,.0f}{r['max_dd_pct']:>6.1f}%")

    with open(DTE / "expiry_gate.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nwritten: {DTE / 'expiry_gate.json'}")
    return 0


def pick_slots_union(frame: pd.DataFrame, k_map: pd.Series) -> List[Tuple]:
    """The unrestricted condor-ML book (top-k condor slots per month, all days)."""
    trades: List[Tuple] = []
    for _, month in frame.groupby(frame["date"].dt.to_period("M")):
        k = int(k_map.get(month["date"].dt.to_period("M").iloc[0], 0))
        if k > 0:
            trades += pick_slots(month, k, lambda r, a: r[f"lgbm__{a}"], [CONDOR])
    return trades


if __name__ == "__main__":
    raise SystemExit(main())
