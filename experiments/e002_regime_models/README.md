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

## Addendum 3 — Days-to-expiry replaces `dow` (`walkforward_dte.py` → `artifacts_dte/`), and e004-informed stop stress (`stress_test.py`)

**dte variant: the SHAP addendum's recommendation pays.** Identical frozen protocol (folds, embargo, LGBM params, gating); only `dow` out, `dte` + `is_expiry` in (expiry calendar is public schedule info, leak-free). OOS calibration improves on **every** archetype for both model families — condor most of all:

| Model | Metric | dow (frozen) | dte variant |
|---|---|---:|---:|
| LGBM | condor Brier | 0.2342 | **0.2014** |
| Logistic | condor Brier | 0.2589 | **0.1763** |
| LGBM | bull / bear Brier | 0.2158 / 0.2644 | 0.2145 / 0.2633 |

Gating (matched count, vs frozen run): baseline identical (protocol check ✓). **ml_logistic+dte is the best policy measured in the sandbox: +₹653,520, PF 2.46, WR 55.1%, max DD ₹18,746 (9.4%)** — first policy to clear config's 55% WR hurdle. LGBM+dte: +₹439,906 at lower DD (26,786), with the condor book *better* on fewer trades (n 439→409, net +507k→+602k) — dte carries real day-selection signal, not just calendar identity. Adopt the dte feature set; prefer the logistic model or the EV-ranking upgrade on top.

**Stop stress (e004's measured 1.4× credit SL: fired on 25% of condor days, mean stopped-trade net −₹719):** replacing a random 25% of the EV book's condor trades (n=765) with e004's realized stop outcome:

| Stopped share | Net ₹ | WR | PF | Max DD (DD%) |
|---|---:|---:|---:|---:|
| 0% (baseline EV) | +583,124 | 50.4% | 2.79 | 28,873 (14.4%) |
| 10% | +458,519 | 46.0% | 2.26 | 28,567 (14.3%) |
| **25% (e004's rate)** | **+309,162** | 39.6% | 1.73 | **29,909 (15.0%)** |
| 40% | +168,428 | 33.7% | 1.35 | 60,939 (30.5%) |

At the *measured* stop rate the book survives: net nearly halves but **drawdown is unchanged** — the SL is a per-trade cap, so stops convert tail days into single capped losses. The book only breaks at 1.6× the measured rate (DD 30.5%). Ceiling: magnitudes are e004's mean stop applied by random draw, not path-matched to the same days (random sampling also understates vol-clustered stop correlation) — `stress_test.py` ponytail note.

## Addendum 4 — Exit-aware gating: e005's real intraday condor PnLs replace the open→close labels (`gating_exit_aware.py`)

The dte gating above prices condor trades with e001's open→close proxy. e005's validated replay supplies real exit outcomes for the condor column (both exit configs; e001 labels kept on e005's 88 skipped days; bull/bear stay on e001 labels — e004 confirmed them directionally). Same frozen gating machinery, dte features. Numbers below are from the regenerated (column-consistent) e005 artifact; an earlier version of this table used rows corrupted by a chunk-append column-order bug:

| Policy | open→close | documented exits (SL+50% tgt) | drop-target exits (SL+EOD) |
|---|---:|---:|---:|
| baseline (rule) | +108,306 | **−42,980** (PF 0.92) | +106,839 |
| ml_lgbm | +439,906 | +135,774 | +433,876 |
| **ml_logistic (dte)** | +653,520 | +283,222 | **+649,104** (DD 18,746) |
| EV-ranked lgbm | +646,433 | +267,130 | **+639,125** (PF 2.97, DD 14,581) |
| condor-only ML | +498,382 | +245,225 | **+492,500** (PF 14.75, DD 2,336) |

**Reading:** (1) Under the *documented* +50% profit target, the selector's edge largely evaporates — the target caps exactly the crush days the ML picks, and the naive rule's condor subset goes negative. (2) With the target dropped, every gating conclusion survives exit-awareness essentially unchanged — because e005 showed the 1.4× SL is a non-event and EOD exits reproduce the endpoint. **The ML edge was never an artifact of missing stops; the +50% cap is the single point of failure.** (3) e005's target sweep refined the pick to **100% of credit** (flat optimum 100–200%); the drop-target column here approximates it. Caveats: mixed exit world for bull/bear; drop-target column is a counterfactual (TARGET→endpoint reconstruction); 74 fallback days; best-of inflation across the policy panel still applies.

## Addendum 5 — Expiry-only gate (dte ≤ 1): Kailash Nadh's expiry-centric proposal, validated (`expiry_gate.py`)

At the same monthly trade budget k (the rule's count), the ML condor book restricted to days with days-to-nearest-expiry ≤ 1 (375 of 920 OOS days) vs unrestricted — e005's clean exit-aware condor PnLs, both exit configs:

| Book | n | Net ₹ | Avg/trade | WR | PF | Max DD (DD%) |
|---|---:|---:|---:|---:|---:|---:|
| documented, unrestricted | 847 | +301,360 | +356 | 50.5% | 2.58 | 9,362 (4.7%) |
| **documented, expiry-only** | **371** | **+376,977** | **+1,016** | **75.5%** | **10.97** | **2,336 (1.2%)** |
| drop-target, unrestricted | 847 | +676,387 | +799 | 50.6% | 4.51 | 9,459 (4.7%) |
| **drop-target, expiry-only** | **371** | **+747,983** | **+2,016** | **76.5%** | **20.27** | **2,336 (1.2%)** |

The expiry gate **adds money while more than halving the workload**: +25% net (documented) / +11% (drop-target), −56% trades, −75% drawdown. It also matches the reviewer's capital argument — the book is flat ~80% of days, freeing collateral for the liquid-fund yield play. Caveats: expiry-day-only selection is close to a calendar rule (the ML still chooses *which* expiry days and SKIPS some — the gate is a restriction, not a calendar); Tue-era 100% WR is a 52-day sample; the composition warning (e005 Add. 2 — inverted-wall days carry the edge) applies to every row here. e005 Add. 3 completes the picture: IV regime does not matter on expiry days, so the gate, not IV timing, is the right concentration.

## Addendum 6 — EV-sizing histogram (`ev_sizing.py`): the 2-lot threshold doesn't discriminate

Testing Idea 5 (size 2 lots when calibrated P(win) > 0.70) on the expiry-gated book's 371 trades, under both exit configs:

| Bucket (documented exits) | n | Net ₹ | Avg/trade | WR |
|---|---:|---:|---:|---:|
| P > 0.70 | 223 (60% of trades) | +222,998 | +1,000 | 80.3% |
| P ≤ 0.70 | 148 | +153,979 | +1,040 | 68.2% |

**The P>0.70 threshold is not selective** — 60% of expiry-gated days clear it, and per-trade PnL is flat across buckets (₹1,000 high-P vs ₹1,040 low-P; the P distribution is compressed: 113 of 371 trades sit in p80–90, only 15 below p50). The reviewer's +35–45% uplift estimate holds arithmetically (+59%/+57% net) but is achievable with **flat 2-lot sizing**: tiered +₹600k/DD ₹4,672 vs flat-2 +₹754k at the *same* DD (the worst day was itself a high-P day), so the tier is strictly dominated — Calmar 161 flat vs 128 tiered.

**Sizing conclusion:** P(win) ranks *which days to take* within the gate (that's where it earned its keep), but within the gated set it carries no extra sizing information — the honest sizing ladder is margin-driven (1→2 lots when utilization allows), not P-driven. Same composition caveat as everywhere else; and 2-lot days double the exposure to the tail that breach-spread insurance (e005 Add. 5) exists to bound.
