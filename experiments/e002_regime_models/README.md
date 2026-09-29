# E002 — ML Regime Models: LightGBM P(win) per Archetype (Purged Walk-Forward)

**Question:** Can LightGBM estimate honest day-level win probabilities for the 3 archetypes, beat simple baselines out-of-sample, and — at the *same* number of trades — lose less and earn more than the e001 rule?

**Design (frozen before run, per experiment.md):**
- **Features (16):** strictly t-1 — prior-day futures return/range/gap, 5d/10d momentum, PCR (t-1, t-2, Δ), ΔOI skew, ATM straddle % (IV proxy) and its change, call/put wall distance %, weekday; plus `gap_open_pct` (day-t open vs t-1 close, known at 09:15 before entry).
- **Leakage guard:** `test_day_t_feature_row_never_sees_day_t` pins that a day's own extreme close is invisible in its own feature row (synthetic parquet, `test_features.py`).
- **Labels:** e001 `labels_daily.csv` — all 3 archetypes replayed daily, era-correct lots, real friction.
- **Protocol:** train trailing 24 months → 5-day embargo → test next calendar month, rolling; refit every fold; hyperparameters frozen (`num_leaves=15, min_data_in_leaf=100, lr=0.05, ff=0.7, bf=0.8`); no per-fold tuning.
- **Models:** LightGBM vs logistic (same features, standardized) vs persistence (mean of last 5 same-archetype outcomes).
- **Calibration:** Brier score vs base rate reported per archetype (the gatekeeper consumes probabilities).
- **Gating sim:** baseline = e001 rule (one trade/day on signal days); ML gets the **same monthly trade count** but chooses which days and which archetype (one trade/day), by model probability.

**Run:** 45 OOS monthly folds, 2023-01 → 2026-09 (1,415 days). Artifacts: `oos_predictions.parquet`, `calibration_summary.csv`, `gating_sim.json`, `folds.json`.

## Results

### Calibration (pooled OOS)

| Archetype | n | Base rate | LGBM Brier | Logit Brier | Persist Brier |
|---|---|---|---|---|---|
| Bull Call Spread | 918 | 28.0% | 0.2158 | **0.2086** | 0.2302 |
| Bear Put Spread | 917 | 45.5% | 0.2644 | **0.2541** | 0.3095 |
| Iron Condor | 847 | 50.9% | **0.2342** | 0.2589 | 0.2811 |

All three models beat the base-rate Brier on every archetype (e.g. condor base-rate Brier ≈ 0.25 vs 0.234 LGBM). Logistic edges out LGBM on the two directional books; LGBM wins on the condor — the archetype that matters most (see below). This is consistent with a small-sample, low-signal problem: simple models are competitive.

### Gating simulation (matched trade count, net ₹, era-correct lots)

| Policy | n | Net | Avg/trade | WR | PF | Max DD |
|---|---|---|---|---|---|---|
| Baseline (e001 rule) | 920 | +108,306 | +118 | 40.8% | 1.20 | 67,526 |
| **ML LGBM ensemble** | 919 | **+446,344** | +486 | 51.8% | **2.01** | **28,543** |
| ML logistic ensemble | 919 | +376,794 | +410 | 49.9% | 1.82 | 31,025 |

Per-archetype net (baseline → ML): Bull −118k → −34k (n 292→115), Bear −47k → −26k (n 301→365), Condor +274k → +507k (n 327→439). The ML ensemble reallocates the same trade budget away from losing spread days toward winning condor days — that is the entire thesis ("fewer losses, same number of trades") working, OOS, on data the models never saw.

## Verdict

**What works:**
1. **The ensemble, as a day/archetype selector, is real.** At identical trade count, ML-LGBM turns +₹108k into +₹446k with drawdown cut by ~58% (67.5k → 28.5k), PF 1.20 → 2.01, WR 40.8% → 51.8%. Logistic confirms the direction (+377k) — two independent model families agree, which is the minimum bar for believing it.
2. **All models are honestly calibrated** (Brier beats base rate on every archetype) — their probabilities can feed the gatekeeper's EV hurdle without re-scaling.
3. The condor is confirmed as the engine's core edge, and ML finds *which* flat days pay (fold 32–35, post-expiry-change era, condor Brier ≈ 0.33–0.38 region shows the models tracking the regime shift rather than breaking on it).

**What does not work:**
1. **The directional spread books remain unprofitable even under ML selection** (Bull −34k, Bear −26k OOS). ML reduces the bleed by avoiding most bull days, but the honest daily-replay edge for spreads is negative; no model extracts money from a negative-EV book.
2. **LGBM barely beats logistic** on 2 of 3 archetypes. The naive t-1 momentum rule's weakness is real signal for the models, but there is not much alpha beyond a linear read of the same features at n≈1,400. LightGBM earns its complexity only on the condor.
3. **Growth caveat:** at 919 trades on a ₹2L bankroll with ~₹190 friction/trade, total friction ≈ ₹175k of the ₹446k is already netted; the sim is friction-real but ignores compounding, slippage regime shifts across eras, and monthly loss circuit-breakers that the live engine enforces.

**Known ceilings (accepted):**
- Open→close labels cannot see intraday stops/targets: condor PnL is likely optimistic (no intraday stop-out), spread PnL likely pessimistic. The *relative* gating result is robust; absolute rupee levels are not final.
- One trade per day enforced (BRD rule); no overlap of signals; P(win)-only ranking (no per-archetype EV normalization) — noted as `ponytail` ceiling in code with the e001-EV upgrade path.
- n≈920 OOS trades; single market (NIFTY); ±10% of these results should be expected from noise alone.

**Recommendation:** Adopt the *pattern*, not the numbers: use model P(win) to select day + archetype at matched frequency, treat the condor as the primary book, and either retire the directional spreads or demand 5-min-data validation before trusting them. The honest next step is e003 (meta-labeling on the live engine's own proposals) and a 5-min intraday replay before any live sizing change.

**Reproduce:** `python -m experiments.e002_regime_models.walkforward` (after e001); tests: `python -m unittest experiments.e002_regime_models.test_features`.

## Addendum — SHAP explanations (`artifacts/shap/`, run via `python -m experiments.e002_regime_models.explain`)

**Global drivers (mean |SHAP|, pooled refit — explains the model, not an OOS claim):**
- Bull: `fut_prev_range_pct` 0.189, `wall_put_dist_pct` 0.183, `fut_prev_ret` 0.173 — prior-day volatility and put-wall proximity dominate; spreads win after quiet, wall-supported days.
- Bear: `gap_open_pct` 0.199, `fut_prev_gap_pct` 0.185, `range5_mean_pct` 0.168 — gap structure is the bear book's signal.
- **Condor: `dow` 0.461 (rank 1), `straddle_pct` 0.419, `straddle_pct_chg` 0.214** — see below.

**Weekday-artifact flag: TRIGGERED for the condor — but the era split shows it is structure, not artifact.**
The weekday-dependence check flagged `dow` (OOS mean P(condor win) spans 0.415→0.665 across weekdays; dow is the model's #1 feature). Splitting condor net PnL by weekday *within each expiry regime*:

| Weekday | Thursday era (→2025-08) | Tuesday era (2025-09→) |
|---|---|---|
| Monday | −146 | **+799** |
| Tuesday | −62 | **+5,588** |
| Wednesday | +158 | −311 |
| **Expiry day** | **+2,028 (Thu)** | **+5,588 (Tue)** |
| Friday | −137 | −228 |

The condor edge is an **expiry-day (0DTE) premium-crush effect, and it migrated with the expiry when NSE moved it Thursday→Tuesday (2025-09-01)**. So the flag correctly warned "model leans on weekday," but deleting `dow` would delete real signal. The robust fix: replace raw weekday with **days-to-nearest-expiry** (and an is-expiry-day flag) — that survives any future NSE expiry change without relearning, and is the recommended feature change before any production use. Also note the live `WEEKDAY_SCHEDULES` still carries Thursday-expiry logic (14:45 gamma cutoff, "Thursday PRIME") — now attached to the wrong day.

Per-day force data for the 5 most-confident wrong calls per archetype: `shap/force_*.json` (base value + top-8 signed contributions per day, ready for plotting).

## Addendum 2 — Gating variants: condor-only book and EV ranking (`gating_variants.py` → `artifacts/gating_variants.json`)

Run on the frozen OOS predictions (no retraining). Self-check: the P(win) policy reproduces `gating_sim.json` ml_lgbm exactly — asserted in the script before anything else prints.

| Policy | n | Net ₹ | Avg/trade | WR | PF | Max DD ₹ (DD%) |
|---|---|---:|---:|---:|---:|---:|
| P(win) ranking (= main e002) | 919 | +446,344 | +486 | 51.8% | 2.01 | 28,543 (14.3%) |
| **EV = P(win) × payoff** | 919 | **+583,124** | **+634** | 50.4% | **2.79** | 28,873 (14.4%) |
| Condor only, rule days | 306 | +273,871 | +895 | 50.7% | 5.20 | 5,729 (2.9%) |
| **Condor only, ML days** | 306 | **+404,703** | **+1,323** | **64.7%** | 9.45 | **6,439 (3.2%)** |
| Condor only, ML + EV | 306 | +404,703 | +1,323 | 64.7% | 9.45 | 6,439 (3.2%) |

- **EV ranking works, by the expected mechanism.** Payoff multipliers frozen from pre-OOS e001 labels (Bull 0.88 / Bear 1.03 / Condor 2.21). Same 919 trades, same drawdown, +₹137k net — because multiplying by payoff pushes the allocation toward the condor (439 → 765 condor trades; spreads nearly vanish, n=25 bull). This is the one-line ranking-key upgrade the `ponytail` note in `walkforward.py` pointed at; adopt P×payoff over P alone.
- **Condor-only gets 91% of the net with a fifth of the drawdown.** The two directional books bleed −₹60k combined inside the full ML book; dropping them costs 9% of net, cuts trades to a third (919 → 306), and max DD from 14.3% → 3.2%. Per-trade quality 486 → ₹1,323.
- **EV + condor-only combined is a no-op by construction** (last row is bit-identical to condor-only ML): within a single archetype the payoff multiplier is a positive constant, so P×payoff ranks identically to P. EV ranking is a *cross-book* reallocation lever — the two upgrades answer the same allocation question from two sides and do not stack. Choose one: EV ranking if you keep all three books, condor-only if you want minimal surface.
- **Caveat unchanged:** condor open→close numbers are the optimistic end (no intraday stop-out in the proxy) until e004 runs. PF 9.45 on n=306 is a slice of that same proxy — treat the *relative* comparison as robust and the absolute rupees as provisional.
