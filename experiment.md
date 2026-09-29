# Experiment Plan: ML-Augmented Decisioning for the Nifty Options Engine

**Status:** Design — implementation lives entirely under `experiments/`; no core file changes.
**Question this answers:** Can simple ML (LightGBM + SHAP) improve *when to trade* and *which strategy to trade* so that we grow capital, cut losses, and keep roughly the same number of trades?
**Ground rule:** ML estimates probabilities. Deterministic rules decide. The `RuleGatekeeper` stays untouched.
**Goal (restated):** Find an **ensemble of models** that makes the right decision most of the time — **not** never-trade / trade-as-little-as-possible. Fewer losses with roughly the same number of trades is success; an engine that says NO every day is a failure mode of this research, not a win.

---

## Sandbox Policy (hard constraint)

1. **Nothing under `experiments/` may modify any file outside `experiments/`.** Originals (`core/`, `backtest/`, `config.py`, `run_engine.py`, `trade.py`, `data/`) are read-only inputs to experiments.
2. All experiments live in numbered folders `experiments/e00x_<name>/`, one folder per experiment, containing its code, its README, and its artifacts. Shared code (feature builders, replay helpers) lives in `experiments/common/` and is imported — never duplicated.
3. Every experiment folder **must** contain a `README.md` with a `## Verdict` section stating plainly **what works** (with numbers) and **what does not work** (with numbers). No verdict = experiment not finished. Verdicts are written once, after the frozen protocol has run — not iterated until the numbers look good.
4. Artifacts (CSVs, models, plots) stay inside the experiment folder under `artifacts/`. Experiments never write into `data/` (that belongs to the core engine) — with the single exception that a future promotion step (e002+) may *propose* a new `calibrated_params.json`, which the user applies manually after review.
5. Promotion path: an experiment's findings graduate into `core/` only after its acceptance gates pass and the user approves the diff. Until then, the live engine is unaffected by anything in `experiments/`.
6. New dependencies (lightgbm, shap, scikit-learn) are experiment-only; they must not be required to run `run_engine.py` or `trade.py`.

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
3. **Lot-size era table (verified against NSE circulars FAOP67372 Oct 2024 / FAOP70616 Oct 2025):**
   | Era | Lot | Source |
   |---|---|---|
   | start of data (2021) → 2024-11-19 | 25 | pre-revision contracts |
   | 2024-11-20 → 2025-12-29 | 75 | FAOP67372: new lot on contracts introduced Nov 20, 2024 |
   | 2025-12-30 → present | 65 | FAOP70616: new series with Jan-2026 expiry cycle, weekly ≈ Dec 30, 2025 |
   | pre-2021 | out of scope v1 (lot eras differ further; extend later if needed) |
   Caveat: within a transition day the *expiring* weekly contract keeps the old lot while new series use the new one; per-day replay uses the new-lot date as the boundary. Absolute ₹ from earlier eras are comparable only after this normalization — and the strategy-selection labels are affected only via friction weights, which is why net-PnL comparisons across eras should also be sanity-checked in **points**, not just rupees.
4. **Output:** one row per (date, archetype): `date, weekday, archetype, gross_pnl, friction, net_pnl, win` — written to `experiments/e001_leakfree_replay/artifacts/labels_daily.csv`.
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
├── common/            # shared helpers (parquet loading, era lots) — no experiment logic
├── e001_leakfree_replay/   # Phase 0: t-1 decision, open→close replay, 3 archetypes, era lots
│   ├── replay.py
│   ├── README.md      # Verdict: what works / what doesn't, with numbers
│   └── artifacts/     # labels_daily.csv, comparison report
├── e002_regime_models/     # Phases 2–6 (created when e001 verdict lands)
├── e003_meta_labeling/     # ML on the rule engine's own triggered trades (parallel candidate)
└── e00N_...                # one folder per experiment, each with README + Verdict
```

## Changelog

- v1 (2026-09-29): initial design. Phase 0 promoted to hard prerequisite after look-ahead bias, lot-size, fail-open, and expiry-regime findings.
- v2 (2026-09-29): added Sandbox Policy (e00x folders, read-only originals, README Verdict requirement), ensemble goal statement, verified lot-era table (25→75→65) from NSE circulars FAOP67372 / FAOP70616, corrected Phase 0 spec (decision from t-1 close, entry at day-t open, all 3 archetypes every day).
- v3 (2026-09-29): e002 verdict — ML day/archetype selector at matched trade count: net ₹108k→₹446k, PF 1.20→2.01, DD −58%; all models honestly calibrated; directional spreads remain negative even under ML selection. SHAP addendum: condor edge is an expiry-day (0DTE) effect that migrated Thursday→Tuesday with the 2025-09 expiry change — replace `dow` with days-to-expiry before production. e003 verdict — meta-labeling has no per-trade discrimination (Brier ≈ base rate), dominated by e002's selector; interesting again only with per-trade intraday features. New: `core/feeds/intraday.py` + `download_intraday.py` (5-min candle store, validated, holiday-aware) and `experiments/e004_intraday_replay/` (BS-repriced SL/target/EOD path simulator, validated on synthetic paths; full run blocked on intraday backfill).
- v4 (2026-09-29): `collated_results.md` (one-page verdicts + cap / ₹/yr / max-DD% table). Gating variants (no retraining, self-checked against committed sim): EV ranking P(win)×payoff lifts net +₹446k→₹583k at same count/DD; condor-only ML book keeps 91% of net at 3.2% DD. Dhan 5-min depth probed: reaches ≥2021-01-04, e004 unblocked. Bug fix: empty Dhan frame (holiday) now raises MissingDataError instead of a misleading ValueError; `gating_variants.py` added.
- v5 (2026-09-29): e004 REAL RUN complete — full 5-min backfill 2021-01→2026-09 (1,409/1,415 e001 days; 6 NSE holidays have no 5-min data), 1,410 sessions replayed with path exits. Spread books CONFIRMED net-negative (bull −₹314k, bear −₹147k; SL caps bull tail days, −474k→−314k). Condor column is a fixed-IV artifact: EOD-only days flip sign vs e001 (corr −0.25), expiry-day edge vanishes — fixed-IV BS strips the theta decay that IS condor income; verdict stays open pending theta-aware pricing. Usable new input: 1.4× credit SL fires on 25% of condor days. e004 integration fix: `_load_prior_partition` parsed bhavcopy stems with the wrong format (every file failed → all days silently skipped); now parses `%Y%m%d` with an indexed cache. Replay is chunk-checkpointed and resume-safe. Gating-variant note: EV + condor-only combined is a no-op by construction (payoff is a constant within one archetype).
- v6 (2026-09-29): dte feature variant (SHAP addendum's recommendation) — `walkforward_dte.py`, frozen protocol, `dow`→`dte`+`is_expiry`: calibration improves on every archetype/both families (condor LGBM 0.2342→0.2014, logistic 0.2589→0.1763); **ml_logistic+dte is the sandbox's best policy: +₹653,520, PF 2.46, WR 55.1%, DD 9.4%** — first to clear the 55% hurdle. Stop stress (`stress_test.py`): at e004's measured 25% condor SL rate the EV book keeps DD flat (14.4%→15.0%) with net +583k→+309k; breaks only at 40% stopped. dte artifacts in `artifacts_dte/` (frozen run untouched).
- v7 (2026-09-29): EV×dte combo (`gating_dte_ev.py`): EV ranking on dte features = +₹646,433 at PF 3.04 and **7.3% DD** — best risk-adjusted policy (they stack; EV is cross-book, dte is per-model). **e005 THETA-AWARE CONDOR REPLAY settles the condor question** (`e005_theta_condor/`): endpoint-anchored pricing (real leg opens in, real closes out — EOD exits verified identical to e001 leg-for-leg) + delta/gamma path + theta glide; condor edge SURVIVES intraday exits (+₹285,669, PF 2.12, max DD 7.3%; expiry-day 0DTE effect confirmed live, 100% WR Tue-era). 1.4× SL is a non-event (56/1,321 days; e004's 25% was artifact). **The +50% profit target forfeits ₹471k — dropping it lifts the book to +₹757k**, the sandbox's highest zero-risk config win. Two rejected e005 designs documented (ATM-σ ratios, per-leg IV ratios — both explode at 0-1 DTE).
- v8 (2026-09-29): exit-aware re-gating (`gating_exit_aware.py`): e005's real condor PnLs swapped into the dte gating (both exit configs, e001 fallback on 88 skipped days). Under documented exits the selector's edge collapses (logistic+dte +₹241k, rule baseline −₹61k) — the +50% target caps exactly the crush days the ML picks; with the target dropped every conclusion survives (logistic+dte +₹650k, EV-ranked +₹656k at 7.3% DD, condor-only ML +₹495k at 1.2% DD). **The ML edge was never an artifact of missing stops; the +50% cap is the single point of failure.** Caveats: mixed exit world for bull/bear, drop-target counterfactual, best-of inflation.
- v9 (2026-09-29): target sweep (`target_sweep.py`, one prep per day across 6 levels) — **pick 100% of credit** (+₹760,856, PF 3.76, DD ₹3,888; flat optimum 100–200%, the documented 50% is the worst operating point). The sweep's sanity assert exposed a chunk-append CSV column-order corruption in the original e005 artifact (72 rows misaligned, WR overstated; conclusions unchanged) — writer fixed with a fixed column schema, artifact + gating regenerated (clean numbers: e005 documented +₹288,581/PF 2.05; exit-aware logistic+dte +₹283k documented / +₹649k drop-target; EV +₹639k). **Inverted-wall audit (`audit_inverted_walls.py`): valid-structure condors LOSE (−₹55,428, PF 0.78); 107.6% of the frozen e001/e002/e005 edge sits on inverted-wall days (PF 91.8) where the position is a directional wall-breach trade rescued by 0DTE crush. Composition warning logged in collated_results.md — validate those marks against intraday option quotes before production.**
- v10 (2026-09-29): reviewer-driven tests (Kailash Nadh's external review). Decay-trailing exit (`exit_sweep.py`): all trail configs (75–80% of credit from 13:30/14:00/14:30) beat the documented 50% cap 2.1–2.4× at DD ₹3,888, but trail the plain 100%-of-credit target by ~₹75k (best: 80% @ 14:30, +₹685,327) — model understates real gamma spikes, so the trail is a defensible risk overlay, not a net improver in-sim. **Expiry-only gate (`expiry_gate.py`): VALIDATED** — ML condor book restricted to dte ≤ 1 (371 of 847 trades) adds net (+₹376,977 documented / +₹747,983 drop-target), WR to 75–77%, DD down to 1.2%. **IV-regime buckets (`iv_regimes.py`): hypothesis REJECTED** — edge lives in low/mid IV on non-expiry days (q2 best, PF 3.99; q5 PF 1.34) and IV is irrelevant on expiry days (all quintiles profitable) — the concentration is the expiry gate, not VIX sizing. Docs: e005 Add. 3, e002 Add. 5, collated updated with the combined production-ready config.
- v11 (2026-09-29): **mark validation DONE** (`marks_validation.py`): Dhan serves 5-min OHLC+OI for NSE_FNO options; on the latest frozen session (2026-09-25) candle opens == bhavcopy opens exactly on all 6 condor legs, closes ≤ ₹0.90 (last-trade vs settlement noise) — **e005's marks are real; stale-mark contamination excluded.** Mechanism confirmed: inverted walls = prior-OI walls above a spot that crashed 09-22→09-25 (futures open 23,302) — crash-inflated premium crushing on expiry is real post-crash short-vol. Scrip hazard logged (FINNIFTY shares NIFTY strikes; map by exact trading symbol). Residual: one session validated (expired contracts delisted); extend via historical-candle depth or live sessions. Production handoff written (`production_handoff.md`): expiry-gated condor config, 3 pre-live gates, staged capital plan ₹2L→₹6L, collateral-yield play, scaling stops at 3 lots (capacity unproven).
- v12 (2026-09-29): **breached-wall spread backtest** (`breach_spread.py`, Idea 3 formalized): on 249 dte≤1 gapped-over-wall days the 2-leg defined-risk spread makes +₹734,388 (98.8% WR, 2 STOPs, worst day −₹6,139 = defined max) — but the 4-leg condor on the same days at the 100% target makes **more** (+₹780,604, DD ₹551) since the unbreached wing also pays on crush days. Verdict: the spread is **tail insurance** (known worst day ~₹7.9k vs the condor's gap-through tail), not a PnL upgrade; and valid-structure days (319/yr) should carry no trade at all (PF 0.78). **EV-sizing histogram (`ev_sizing.py`, Idea 5): threshold rejected** — 60% of gated trades clear P>0.70 and per-trade PnL is flat across buckets (₹1,000 vs ₹1,040); tiered 2-lot (+₹600k/DD ₹4,672) is dominated by flat 2-lot (+₹754k, same DD); P(win) ranks *which days*, not *how much size* — sizing ladder is margin-driven.
