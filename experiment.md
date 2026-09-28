# Experiment Plan: ML-Augmented Decisioning for the Nifty Options Engine

**Status:** Design — implementation lives entirely under `experiments/`; no core file changes.
**Question this answers:** Can simple ML (LightGBM + SHAP) improve *when to trade* and *which strategy to trade* so that we grow capital, cut losses, and keep roughly the same number of trades?
**Ground rule:** ML estimates probabilities. Deterministic rules decide. The `RuleGatekeeper` stays untouched.

---

## 0. Why the current numbers can't be used yet (Phase 0 must run first)

The current calibration feed (`calibrated_params.json`) is produced by a replay with look-ahead bias:

- `simulate_session_from_parquet` branches on `day_pct = (close - open)/open` — a quantity known only at 15:30 — then enters at open. Result: Bear Put Spread 87.4% WR / PF 26 is mechanically guaranteed, not an edge.
- Lot size is hardcoded at 75 for all years (was 50 through the 2015–2024 era; 75 only from Nov 2024).
- `get_calibrated_strategy_edge()` fails open (returns WR 0.70 / PF 2.0 when calibration is missing).
- Weekly expiry was Thursday until 2025-08, Tuesday from 2025-09-01 (NSE FAOP68747). Any weekday statistic pooled across that boundary mixes two different market structures.

Until Phase 0 lands, treat every win rate / EV in `calibrated_params.json` as invalid.

## Phase 0 — Fix the measurement (leak-free replay)

New module `experiments/replay.py` (imports, never copies, `core.friction.zerodha` and `core.feeds.bhavcopy`):

1. **Decision uses t-1 information only.**
   - `sig_pct  = (close[t-1] - open[t-1]) / open[t-1]`
   - `sig_pcr  = pcr_oi[t-1]`, `sig_wall_dist`, 5-day momentum ending t-1.
   - Rule (baseline, deliberately dumb): `sig_pct >= +0.25%` → Bull Call Spread on day t; `<= -0.25%` → Bear Put Spread; else Iron Condor.
   - This is a momentum-continuation rule executable at 09:15 on day t. It may be a *bad* rule — that's fine, it's the honest baseline.
2. **Replay all 3 archetypes every day** (not one per day): bull spread, bear spread, condor — each with entry at day-t open, exit at day-t close.
   - Known simplification (`ponytail`-style ceiling): daily bars can't simulate intraday SL/target paths. Open→close is the honest proxy; label all results as such. Intraday fidelity requires 5-min history — out of scope for v1.
3. **Lot-size era table:**
   | Era | Lot |
   |---|---|
   | 2015 → 2024-11-19 | 50 |
   | 2024-11-20 → present | 75 |
   | pre-2015 | exclude from ₹ PnL (features only) |
   Verify boundaries against NSE circulars before trusting absolute rupee figures from any era.
4. **Output:** one row per (date, archetype): `date, weekday, archetype, gross_pnl, friction, net_pnl, win` — written to `experiments/artifacts/labels_daily.csv`.
5. **Expectation check:** if this honest replay still shows PF > 3, suspect the replay, not celebrate.

## Phase 0b — Fail-closed calibration (core fix, small diff)

- `get_calibrated_strategy_edge()` returns `None` when JSON or key is missing; strategies map `None → win_rate = 0.0`; the gatekeeper's existing `EDGE_HURDLE` veto then yields TIER 0 no-trade. Delete the 0.70 / 2.0 / ₹800 fallbacks.
- `get_time_of_entry_performance` hardcodes defaults (`0.793`, `15.0`, ...) — replace with `None` → status `UNMEASURED (daily bhavcopy cannot validate intraday windows; needs 5-min data)`. Keep only the operational vetos (opening range, pre-square-off), which are policy, not statistics.
- Regeneration path: `python backtest.py` (single command, single source of truth).

## Phase 1 — Dataset & features (t-1 information only)

`experiments/features.py` builds one tidy daily frame from existing parquet partitions + optional merges:

- **Price/momentum:** t-1 open→close %, prior 5d/10d returns, gap at t-open vs t-1 close, 5d avg range, distance from 20d high/low.
- **Options microstructure (t-1):** PCR_OI, ΔOI skew (CE vs PE change), straddle ATM ÷ spot (IV proxy), call/put wall distance in %, wall OI concentration.
- **Vol regime:** India VIX level & 5d change (download NSE India VIX history — free CSV), Parkinson vol from daily OHLC.
- **Calendar:** weekday, days-to-expiry, expiry-weekday flag (Thursday-era vs Tuesday-era — never let the model see only one).
- **Optional extensions:** NIFTY spot index history (long, free), FII/DII flows.
- **Cross-sectional multiplier (optional, Phase 1b):** same features for all ~180 F&O symbols → next-day direction, for the regime model's sample count. Strategy-selection labels stay NIFTY-only.
- Leakage rule, absolute: **every feature value is computable before 09:15 on day t.** Enforce with a unit check: `features.loc[t]` may only touch rows `< t`.

## Phase 2 — Labels

From `labels_daily.csv`: three binary targets per day — `bull_won`, `bear_won`, `condor_won` (net of friction, era-correct lot). Optional regression targets: `net_pnl` per archetype (for EV refinement later; v1 stays classification).

## Phase 3 — Models

Three LightGBM binary classifiers (one per archetype), not a cascade:

| Hyperparameter | Frozen value |
|---|---|
| num_leaves | 15 |
| min_data_in_leaf | 100 |
| learning_rate | 0.05 |
| feature_fraction | 0.7 |
| bagging_fraction | 0.8 |
| early stopping | time-ordered validation set |

- No per-fold hyperparameter tuning (that's where leakage sneaks back).
- **Mandatory baselines, same folds:** (a) logistic regression, (b) persistence heuristic ("yesterday's regime persists"), (c) always-trade replay.
- If LightGBM doesn't beat logistic + persistence out-of-sample, the answer is "ML adds nothing here" — a valid, money-saving result.

## Phase 4 — Purged walk-forward protocol (no leakage)

1. Train on trailing 24 months → **5-day embargo gap** → test next 1 month → roll forward monthly.
2. With 2021+ data: ~20–45 OOS months. If pre-2015 data is added: features-only training (scale-free features), OOS evaluation restricted to 2015+.
3. Refit every fold. Because expiry weekday changed 2025-09, per-fold refits are the mechanism that adapts — pooled fits would blend two regimes.
4. **Report calibration, not accuracy:** Brier score + reliability curve per fold and pooled (the gatekeeper consumes probabilities against a 55% hurdle — miscalibrated P poisons EV).
5. Never evaluate a hyperparameter change against the same OOS months twice without recording it in this file (anti-overfitting discipline). Freeze this protocol before the first full run.

## Phase 5 — Decision integration & A/B simulation

- Expected EV per archetype: `P_win × target_profit − (1 − P_win) × max_loss − friction` — the same formula the audit engine already uses; ML only replaces the made-up P.
- **Gating sim (`experiments/gating_sim.py`):** always-trade baseline vs ML-gated at **matched trade count** (threshold set to admit the same number of trades as baseline). Compare net PnL, profit factor, max drawdown, loss-trade count. This is the direct test of "fewer losses, same number of trades."
- If adopted: model outputs feed `TradeProposal.win_rate` only. Gatekeeper, sizing, windows unchanged.

## Phase 6 — SHAP explanations

- Global `TreeExplainer` summary per model: which features drive predicted losing days; prune features with near-zero importance; **catch artifacts** (e.g., model keying on weekday because of the 2025 expiry shift → if SHAP shows weekday dominance, drop the feature and refit).
- Per-day force plots: turn a no-trade veto into a narrative ("P=0.41, driven by Δstraddle +0.6σ, gap-down −0.4%").
- Caveat: correlated features (PCR vs wall distance) split credit — use SHAP as a guide, not proof.

## Phase 7 — Acceptance gates (all must hold to recommend adoption)

1. Honest replay baseline (Phase 0) documented — no PF > 3 anomalies unexplained.
2. ML beats logistic + persistence + always-trade on pooled OOS (net PnL and drawdown, not just accuracy).
3. Calibration passes (Brier better than base rate; reliability curve near diagonal).
4. Trade count within ±10% of baseline in the gating sim.
5. Protocol was frozen before results were seen; every protocol change is logged in this file's changelog.

## Layout

```
experiments/
├── replay.py          # Phase 0 leak-free replay (imports core.*, never edits it)
├── features.py        # Phase 1 t-1 features + leakage self-check
├── train_regime.py    # Phase 3–4 models, baselines, purged walk-forward
├── gating_sim.py      # Phase 5 matched-count A/B
├── explain.py         # Phase 6 SHAP reports
└── artifacts/         # labels_daily.csv, folds.json, models/, plots/
```

## Changelog

- v1 (2026-09-29): initial design. Phase 0 promoted to hard prerequisite after look-ahead bias, lot-size, fail-open, and expiry-regime findings.
