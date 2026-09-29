"""EV-sizing histogram (Kailash's Idea 5): what does 2-lot sizing on top-quartile
calibrated-P days actually add to the expiry-gated condor book?

Rebuilds the expiry-gated ML book (same loop as expiry_gate.py) with each trade's
calibrated LGBM P(win) attached, buckets the 371 trades by P, and prices the 2-lot rule:
1 lot everywhere + 1 extra lot on P > 0.70 days. Reported under both e005 exit configs.

Run: python -m experiments.e002_regime_models.ev_sizing
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

import pandas as pd

from experiments.e002_regime_models import walkforward as W
from experiments.e002_regime_models.gating_exit_aware import e005_pnls
from experiments.e002_regime_models.gating_variants import CONDOR, pick_slots
from experiments.e002_regime_models.walkforward import PNL_COLUMNS, RULE_TO_ARCH, _policy_stats

HERE = Path(__file__).resolve().parent
DTE = HERE / "artifacts_dte"
CUT = 0.70


def gated_trades_with_p(preds: pd.DataFrame, pnl_map: pd.Series) -> List[Tuple]:
    """Expiry-gated condor book (exactly expiry_gate.py: per-month top-k condor slots by
    LGBM P among dte<=1 days) with each picked trade's P attached."""
    frame = preds.copy()
    key = frame["date"].dt.strftime("%Y-%m-%d")
    frame[PNL_COLUMNS[CONDOR]] = key.map(pnl_map).fillna(frame[PNL_COLUMNS[CONDOR]])
    trades: List[Tuple] = []
    for _, month in frame.groupby(frame["date"].dt.to_period("M")):
        k = int(month["rule_signal"].isin(RULE_TO_ARCH).sum())
        if k <= 0:
            continue
        cand = month[(month["dte"] <= 1) & month[CONDOR.replace(" ", "_") + "_sim"]]
        picked = pick_slots(cand, k, lambda r, a: r[f"lgbm__{a}"], [CONDOR])
        p_by_date = cand.set_index("date")[f"lgbm__{CONDOR}"]
        for d, arch, pnl in picked:
            trades.append((d, arch, pnl, float(p_by_date.get(d, float("nan")))))
    return trades  # date, arch, pnl, p


def main() -> int:
    preds = pd.read_parquet(DTE / "oos_predictions.parquet")
    preds["date"] = pd.to_datetime(preds["date"])

    from experiments.e002_regime_models.walkforward_dte import expiry_calendar
    import config
    preds = preds.merge(expiry_calendar(config.HISTORICAL_DATA_DIR), on="date", how="left")

    documented, drop_target = e005_pnls()
    out = {}
    for name, series in (("documented", documented), ("drop_target", drop_target)):
        trades = gated_trades_with_p(preds, series)
        df = pd.DataFrame(trades, columns=["date", "archetype", "pnl", "p"])
        buckets = {
            f"p_gt_{CUT}": df[df.p > CUT],
            f"p_le_{CUT}": df[df.p <= CUT],
        }
        base = _policy_stats(df["pnl"])
        top = buckets[f"p_gt_{CUT}"]
        two_lot = base["net_total"] + float(top["pnl"].sum())  # +1 extra lot on top-quartile days
        out[name] = {
            "n": base["n"], "net_total": base["net_total"], "win_rate": base["win_rate"],
            "buckets": {b: {"n": int(len(s)), "net": round(float(s.pnl.sum()), 0),
                            "avg": round(float(s.pnl.mean()), 1),
                            "wr": round(float((s.pnl > 0).mean()), 3)} for b, s in buckets.items()},
            "two_lot_net": round(two_lot, 0),
            "two_lot_uplift_pct": round((two_lot / base["net_total"] - 1) * 100, 1),
            "p_hist_deciles": {f"p{d}": int(((df.p >= d / 10) & (df.p < (d + 1) / 10)).sum())
                               for d in range(4, 10)},
        }
        print(f"\n[{name}] expiry-gated book: n={base['n']} net={base['net_total']:,.0f} "
              f"wr={base['win_rate']:.3f}")
        for b, s in out[name]["buckets"].items():
            print(f"  {b:<10} n={s['n']:>3} net={s['net']:>10,.0f} avg={s['avg']:>8.1f} wr={s['wr']:.3f}")
        print(f"  P deciles (p40-p100 counts): {out[name]['p_hist_deciles']}")
        print(f"  2-lot on P>{CUT} days: net={two_lot:,.0f} "
              f"(+{out[name]['two_lot_uplift_pct']}% vs flat 1 lot)")

    with open(DTE / "ev_sizing.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nwritten: {DTE / 'ev_sizing.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
