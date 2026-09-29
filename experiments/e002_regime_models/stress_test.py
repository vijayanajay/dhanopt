"""Stress test: e004's real stop distribution applied to the EV-ranked gating book.

e004 measured the 1.4x-credit SL firing on 25% of condor days (mean net -718.9).
The e002 books' condor PnL comes from the open->close proxy, which cannot see that
stop. Here we replace a fraction of the EV book's condor trade PnLs with e004's
realized mean stopped-trade outcome and report net / DD at matched trade count.

# ponytail: magnitude is e004's realized MEAN stop (-718.9, mixed lot eras), applied
# as a random 25% draw — not path-matched to the same days. Upgrade path: re-price
# the whole book with e005's theta-aware path sim.

Run: python -m experiments.e002_regime_models.stress_test
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from experiments.e002_regime_models.gating_variants import (
    ARTIFACTS, CAPITAL, CONDOR, ARCH_KEYS, payoff_multipliers, pick_slots)
from experiments.e002_regime_models.walkforward import (PNL_COLUMNS, RULE_TO_ARCH, _policy_stats)

HERE = Path(__file__).resolve().parent
STOP_PNL = -718.9  # e004 realized mean net of condor STOP exits (intraday_replay.csv)
STRESS_FRACTIONS = (0.10, 0.25, 0.40)


def build_ev_book() -> pd.DataFrame:
    """Rebuilds the EV = P(win) x payoff book (identical to gating_variants ml_ev)."""
    preds = pd.read_parquet(ARTIFACTS / "oos_predictions.parquet")
    preds["date"] = pd.to_datetime(preds["date"])
    payoff = payoff_multipliers(
        HERE.parent / "e001_leakfree_replay" / "artifacts" / "labels_daily.csv", preds["date"].min())
    trades = []
    for _, month in preds.groupby(preds["date"].dt.to_period("M")):
        base = month[month["rule_signal"].isin(RULE_TO_ARCH)]
        k = len(base)
        if k > 0:
            trades += pick_slots(month, k, lambda r, a: float(r[f"lgbm__{a}"]) * payoff[a], ARCH_KEYS)
    return pd.DataFrame(trades, columns=["date", "archetype", "pnl"]).sort_values("date")


def main() -> int:
    book = build_ev_book()
    base_stats = _policy_stats(book["pnl"])
    condor = book[book["archetype"] == CONDOR]
    print(f"EV book: n={base_stats['n']} net={base_stats['net_total']:,.0f} "
          f"wr={base_stats['win_rate']:.3f} dd={base_stats['max_dd']:,.0f} "
          f"| condor trades={len(condor)} condor net={condor['pnl'].sum():,.0f}")

    rows, detail = [], {}
    for frac in STRESS_FRACTIONS:
        stressed = book.copy()
        idx = condor.sample(frac=frac, random_state=42).index
        stressed.loc[idx, "pnl"] = STOP_PNL
        s = _policy_stats(stressed["pnl"])
        s["max_dd_pct"] = round(s["max_dd"] / CAPITAL * 100, 1)
        s["frac"] = frac
        rows.append(s)
        detail[f"stress_{int(frac*100)}"] = s
        print(f"stress {int(frac*100):>3}% of condor trades stopped: n={s['n']} "
              f"net={s['net_total']:>9,.0f} wr={s['win_rate']:.3f} pf={s['pf']:.2f} "
              f"dd={s['max_dd']:>8,.0f} ({s['max_dd_pct']}%)")

    out = {"stop_pnl": STOP_PNL, "baseline_ev": base_stats, "policies": detail}
    with open(ARTIFACTS / "stress_test.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nwritten: {ARTIFACTS / 'stress_test.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
