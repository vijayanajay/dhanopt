# E003 — Meta-Labeling: ML on the Rule Engine's Own Trades

**Question:** Train one model ONLY on trades the e001 rule would take (rule-selected day+archetype), predicting P(this trade wins). Does filtering/redeploying by that probability beat the rule at matched trade count — and how does it compare with e002's day/archetype selector?

**Design:** one LightGBM (same frozen params) on rule trades only (~1,387 train-eligible rows; 897 OOS); identical purged folds to e002 (24m train → 5d embargo → 1m test); policies compared at matched monthly count: baseline (all rule trades) vs meta top-K vs e002-style selector; plus a threshold sweep (skip P < τ), meta-labeling's natural operating point. Artifacts: `meta_oos_predictions.parquet`, `policy_comparison.json`.

## Results

> **Era correction (2026-09-30):** re-run after the lot-era fix in `experiments/common/lots.py` (flat 25 before Nov-2024 → verified 75/50/25/75/65). Same qualitative verdict, fresher numbers throughout.

**Calibration (OOS, rule trades only):** Brier 0.2473 vs 0.2464 for always predicting the 44% base rate — **no better than always predicting the base rate**. Accuracy 0.567 vs 0.560 for always predicting "loss" (base rate 44.0% win) — a coin-flip over the trivial rule. The meta model has **no per-trade discriminative power** on the rule's own trades.

**Matched-count policies (n=897 each):**

| Policy | Net | Avg/trade | WR | PF | Max DD |
|---|---|---|---|---|---|
| Baseline (rule) | +129,746 | +145 | 44.0% | 1.20 | 67,526 |
| Meta top-K | +129,746 | +145 | 44.0% | 1.20 | 67,526 |
| **e002-style selector** | **+578,639** | +645 | 53.2% | 2.28 | 25,799 |

(Meta top-K is identical to baseline by construction: K = the full rule set leaves zero freedom.)

**Threshold sweep (filter operating point):**

| τ | keep | n | Net | Avg/trade | PF |
|---|---|---|---|---|---|
| 0.40 | 63% | 567 | +213,963 | +377 | 1.59 |
| 0.45 | 53% | 475 | +198,522 | +418 | 1.66 |
| 0.50 | 39% | 351 | +181,993 | +519 | 1.85 |
| 0.55 | 29% | 259 | +144,275 | +557 | 1.94 |

## Verdict

**What works:**
1. Meta-labeling's filter *does* improve per-trade quality: τ=0.40 keeps 63% of trades, raises avg/trade 145→₹377, and **total net rises** (+₹214k vs +₹130k). Even cutting trades by 37%, the book makes more money.
2. But the mechanism is not per-trade skill: with Brier ≈ base rate, the sweep wins by **re-learning archetype base rates** (the model's P is essentially the rule trade's archetype base rate plus noise — so thresholding silently selects condor trades over bull trades). It is a blunt version of the same conclusion e002 reached properly.
3. Base rates of rule trades reproduce e001 exactly (Bull .298 / Bear .472 / Condor .546) — pipeline consistency check passed.

**What does not work:**
1. **No within-archetype discrimination.** On the trades the rule already takes, t-1 features carry no additional signal about which specific trade wins (Brier 0.2473 ≈ 0.2464; accuracy barely clears loss-only). The rule's trade list is too homogeneous / the features too coarse for trade-level meta-labeling at this granularity.
2. **Dominated by e002's selector at every operating point:** e002 achieves ₹645/trade at FULL trade count (n=897, net ₹579k) vs meta's best sweep point ₹557/trade at 29% of trades (n=259, net ₹144k). Better per-trade quality AND 3.5× the trades. For this engine, the day/archetype selector strictly dominates meta-labeling.
3. Sweep operating point was chosen post-hoc from 4 τ values — treat the sweep as illustrative, not as a tuned result (mild selection bias, logged per the frozen-protocol rule).

**Recommendation:** keep e002-style selection as the production pattern. Meta-labeling would become interesting again only with richer per-trade features (intraday path stats via e004, live option Greeks, IV term structure) — i.e., when the trade list itself carries more information than the day-level features.

**Reproduce:** `python -m experiments.e003_meta_labeling.meta_labeling` (after e001/e002); tests: `python -m unittest experiments.e003_meta_labeling.test_meta_labeling`.
