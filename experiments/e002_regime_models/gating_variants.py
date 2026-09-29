"""E002 add-on: gating variants — condor-only book and EV-normalized selection.

Reuses artifacts/oos_predictions.parquet (no retraining). Two questions:
1. Condor-only: drop both directional books; ML picks WHICH days the condor
   trades, matched to the rule's condor count per month.
2. EV ranking: score = P(win) x payoff_arch instead of P(win) alone, where
   payoff_arch = mean(win pnl) / |mean(loss pnl)| frozen from pre-OOS labels.

Self-check: the reproduced P(win) policy must match artifacts/gating_sim.json
(ml_lgbm) before the variant numbers mean anything.

Run: python -m experiments.e002_regime_models.gating_variants
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import numpy as np
import pandas as pd

from experiments.e002_regime_models.walkforward import ARCH_KEYS, PNL_COLUMNS, RULE_TO_ARCH, _policy_stats

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
CAPITAL = 200_000.0
CONDOR = "Iron Condor"


def payoff_multipliers(labels_csv: Path, before: pd.Timestamp) -> Dict[str, float]:
    """Per-archetype payoff ratio from realized labels strictly before the OOS window."""
    df = pd.read_csv(labels_csv, parse_dates=["date"])
    df = df[(df["date"] < before) & (df["simulated"]) & df["net_pnl"].notna()]
    out: Dict[str, float] = {}
    for arch in ARCH_KEYS:
        pnl = df.loc[df["archetype"] == arch, "net_pnl"]
        wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
        out[arch] = round(float(wins.mean() / abs(losses.mean())), 3) if len(wins) and len(losses) else 1.0
    return out


def pick_slots(month: pd.DataFrame, k: int, score: Callable[[pd.Series, str], float],
               archs: List[str]) -> List[Tuple[pd.Timestamp, str, float]]:
    """Top-k (day, archetype) slots by score, one trade per day (same loop as e002)."""
    scored: List[Tuple[float, pd.Timestamp, str]] = []
    for _, r in month.iterrows():
        for arch in archs:
            if not r[arch.replace(" ", "_") + "_sim"]:
                continue
            s = score(r, arch)
            if pd.notna(s):
                scored.append((float(s), r["date"], arch))
    scored.sort(key=lambda t: (-t[0], t[1]))
    chosen: set = set()
    picks: List[Tuple[pd.Timestamp, str, float]] = []
    for s, d, arch in scored:
        if d in chosen:
            continue
        chosen.add(d)
        picks.append((d, arch, r_pnl(month, d, arch)))
        if len(picks) == k:
            break
    return picks


def r_pnl(month: pd.DataFrame, d: pd.Timestamp, arch: str) -> float:
    sub = month[month[arch.replace(" ", "_") + "_sim"]]
    return float(sub.set_index("date")[PNL_COLUMNS[arch]].get(d, np.nan))


def run_variants(preds: pd.DataFrame, payoff: Dict[str, float]) -> Dict[str, Dict]:
    trades: Dict[str, List[Tuple[pd.Timestamp, str, float]]] = {
        "ml_pwin_repro": [], "ml_ev": [], "condor_rule": [], "condor_ml": [],
    }
    for _, month in preds.groupby(preds["date"].dt.to_period("M")):
        base = month[month["rule_signal"].isin(RULE_TO_ARCH)]
        k_full = len(base)
        flat = month[(month["rule_signal"] == "FLAT") & month[CONDOR.replace(" ", "_") + "_sim"]]
        k_condor = len(flat)

        if k_full > 0:
            trades["ml_pwin_repro"] += pick_slots(month, k_full, lambda r, a: r[f"lgbm__{a}"], ARCH_KEYS)
            trades["ml_ev"] += pick_slots(
                month, k_full, lambda r, a: float(r[f"lgbm__{a}"]) * payoff[a], ARCH_KEYS)
        if k_condor > 0:
            for _, r in flat.iterrows():
                trades["condor_rule"].append((r["date"], CONDOR, r[PNL_COLUMNS[CONDOR]]))
            trades["condor_ml"] += pick_slots(month, k_condor, lambda r, a: r[f"lgbm__{a}"], [CONDOR])

    out: Dict[str, Dict] = {}
    for name, tl in trades.items():
        df = pd.DataFrame(tl, columns=["date", "archetype", "pnl"]).sort_values("date")
        stats = _policy_stats(df["pnl"])
        stats["max_dd_pct"] = round(stats["max_dd"] / CAPITAL * 100, 1)
        for arch in ARCH_KEYS:
            sub = df[df["archetype"] == arch]["pnl"]
            stats[f"n_{arch}"] = int(len(sub))
            stats[f"net_{arch}"] = round(float(sub.sum()), 0) if len(sub) else 0.0
        out[name] = stats
    return out


def main() -> int:
    preds = pd.read_parquet(ARTIFACTS / "oos_predictions.parquet")
    preds["date"] = pd.to_datetime(preds["date"])
    oos_start = preds["date"].min()

    payoff = payoff_multipliers(HERE.parent / "e001_leakfree_replay" / "artifacts" / "labels_daily.csv", oos_start)
    print("frozen payoff multipliers (pre-OOS labels):", payoff)

    results = run_variants(preds, payoff)

    # Self-check: reproduction must match the committed gating_sim.json ml_lgbm row.
    with open(ARTIFACTS / "gating_sim.json") as f:
        ref = json.load(f)["ml_lgbm"]
    repro = results["ml_pwin_repro"]
    for key in ("n", "net_total", "win_rate", "pf", "max_dd"):
        assert repro[key] == ref[key], f"repro mismatch {key}: {repro[key]} vs {ref[key]}"
    print("self-check OK: P(win) reproduction matches gating_sim.json ml_lgbm\n")

    order = [("ml_pwin_repro", "P(win) e002 (repro)"), ("ml_ev", "EV = P x payoff"),
             ("condor_rule", "Condor only, rule days"), ("condor_ml", "Condor only, ML days")]
    print(f"{'policy':<26}{'n':>5}{'net':>11}{'avg':>8}{'wr':>7}{'pf':>7}{'maxDD':>9}{'DD%':>7}")
    for key, label in order:
        r = results[key]
        print(f"{label:<26}{r['n']:>5}{r['net_total']:>11,.0f}{r['avg_net']:>8.1f}"
              f"{r['win_rate']:>7.3f}{r['pf']:>7.2f}{r['max_dd']:>9,.0f}{r['max_dd_pct']:>6.1f}%")
        for arch in ARCH_KEYS:
            print(f"    {arch:<22} n={r[f'n_{arch}']:>4} net={r[f'net_{arch}']:>10,.0f}")

    with open(ARTIFACTS / "gating_variants.json", "w") as f:
        json.dump({"payoff_multipliers": payoff, "policies": results}, f, indent=2, default=str)
    print(f"\nwritten: {ARTIFACTS / 'gating_variants.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
