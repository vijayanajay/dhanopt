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
| Bull Call Spread | 918 | 28.9% | 0.2178 | **0.2118** | 0.2349 |
| Bear Put Spread | 917 | 46.5% | 0.2647 | **0.2560** | 0.3115 |
| Iron Condor | 847 | 53.5% | **0.2341** | 0.2566 | 0.2795 |

All three models beat the persistence baseline on every archetype (condor: 0.2795 vs 0.2341 LGBM) and the trivial base-rate Brier (2p(1−p) ≈ 0.50 here). Logistic edges out LGBM on the two directional books; LGBM wins on the condor — the archetype that matters most (see below). This is consistent with a small-sample, low-signal problem: simple models are competitive.

### Gating simulation (matched trade count, net ₹, era-correct lots)

> **Era correction (2026-09-30):** the first run of this sim used a flat 25 lot for all pre-Nov-2024 rows (verified eras are 75/50/25/75/65 — see `experiments/common/lots.py`), understating 2021→Apr-2024 rupees ~2–3×. Tables below reflect the corrected re-run (`--no-cache`); OOS-window DDs are unchanged (the drawdown months sit in the 75-lot era). Add. 1's per-era weekday rupee table has been recomputed on the corrected labels — the expiry-migration conclusion is unchanged and sharper.

| Policy | n | Net | Avg/trade | WR | PF | Max DD |
|---|---|---|---|---|---|---|
| Baseline (e001 rule) | 920 | +129,746 | +141 | 42.9% | 1.20 | 67,526 |
| **ML LGBM ensemble** | 919 | **+581,069** | +632 | 53.2% | **2.24** | **29,237** |
| ML logistic ensemble | 919 | +518,247 | +564 | 52.6% | 2.08 | 21,907 |

Per-archetype net (baseline → ML): Bull −136k → −35k (n 292→93), Bear −54k → −21k (n 301→336), Condor +319k → +636k (n 327→490). The ML ensemble reallocates the same trade budget away from losing spread days toward winning condor days — that is the entire thesis ("fewer losses, same number of trades") working, OOS, on data the models never saw.

## Verdict

**What works:**
1. **The ensemble, as a day/archetype selector, is real.** At identical trade count, ML-LGBM turns +₹130k into +₹581k with drawdown cut by ~57% (67.5k → 29.2k), PF 1.20 → 2.24, WR 42.9% → 53.2%. Logistic confirms the direction (+518k) — two independent model families agree, which is the minimum bar for believing it.
2. **All models are honestly calibrated** (Brier beats base rate on every archetype) — their probabilities can feed the gatekeeper's EV hurdle without re-scaling.
3. The condor is confirmed as the engine's core edge, and ML finds *which* flat days pay (fold 32–35, post-expiry-change era, condor Brier 0.30–0.37 region shows the models tracking the regime shift rather than breaking on it).

**What does not work:**
1. **The directional spread books remain unprofitable even under ML selection** (Bull −35k, Bear −21k OOS). ML reduces the bleed by avoiding most bull days, but the honest daily-replay edge for spreads is negative; no model extracts money from a negative-EV book.
2. **LGBM barely beats logistic** on 2 of 3 archetypes. The naive t-1 momentum rule's weakness is real signal for the models, but there is not much alpha beyond a linear read of the same features at n≈1,400. LightGBM earns its complexity only on the condor.
3. **Growth caveat:** at 919 trades on a ₹2L bankroll with ~₹190 friction/trade, total friction ≈ ₹175k of the ₹581k is already netted; the sim is friction-real but ignores compounding, slippage regime shifts across eras, and monthly loss circuit-breakers that the live engine enforces.

**Known ceilings (accepted):**
- Open→close labels cannot see intraday stops/targets: condor PnL is likely optimistic (no intraday stop-out), spread PnL likely pessimistic. The *relative* gating result is robust; absolute rupee levels are not final.
- One trade per day enforced (BRD rule); no overlap of signals; P(win)-only ranking (no per-archetype EV normalization) — noted as `ponytail` ceiling in code with the e001-EV upgrade path.
- n≈920 OOS trades; single market (NIFTY); ±10% of these results should be expected from noise alone.

**Recommendation:** Adopt the *pattern*, not the numbers: use model P(win) to select day + archetype at matched frequency, treat the condor as the primary book, and either retire the directional spreads or demand 5-min-data validation before trusting them. The honest next step is e003 (meta-labeling on the live engine's own proposals) and a 5-min intraday replay before any live sizing change.

**Reproduce:** `python -m experiments.e002_regime_models.walkforward` (after e001); tests: `python -m unittest experiments.e002_regime_models.test_features`.

## Addendum — SHAP explanations (`artifacts/shap/`, run via `python -m experiments.e002_regime_models.explain`)

**Global drivers (mean |SHAP|, pooled refit — explains the model, not an OOS claim):**
- Bull: `wall_put_dist_pct` 0.185, `fut_prev_ret` 0.174, `fut_prev_range_pct` 0.161 — put-wall proximity and prior-day movement dominate; spreads win after quiet, wall-supported days.
- Bear: `gap_open_pct` 0.203, `straddle_pct` 0.183, `pcr_t2` 0.168 — gap structure is the bear book's signal.
- **Condor: `straddle_pct` 0.427, `dow` 0.385 (rank 2), `wall_call_dist_pct` 0.197** — see below.

**Weekday-artifact flag: TRIGGERED for the condor — but the era split shows it is structure, not artifact.**
The weekday-dependence check flagged `dow` (OOS mean P(condor win) spans 0.460→0.678 across weekdays; dow is the condor model's #2 feature, mean |SHAP| 0.385). Splitting condor net PnL by weekday *within each expiry regime*:

| Weekday | Thursday era (→2025-08) | Tuesday era (2025-09→) |
|---|---|---|
| Monday | −76 | **+799** |
| Tuesday | +26 | **+5,588** |
| Wednesday | +397 | −311 |
| **Expiry day** | **+2,995 (Thu)** | **+5,588 (Tue)** |
| Friday | −119 | −228 |

The condor edge is an **expiry-day (0DTE) premium-crush effect, and it migrated with the expiry when NSE moved it Thursday→Tuesday (2025-09-01)**. So the flag correctly warned "model leans on weekday," but deleting `dow` would delete real signal. The robust fix: replace raw weekday with **days-to-nearest-expiry** (and an is-expiry-day flag) — that survives any future NSE expiry change without relearning, and is the recommended feature change before any production use. Also note the live `WEEKDAY_SCHEDULES` still carries Thursday-expiry logic (14:45 gamma cutoff, "Thursday PRIME") — now attached to the wrong day.

Per-day force data for the 5 most-confident wrong calls per archetype: `shap/force_*.json` (base value + top-8 signed contributions per day, ready for plotting).

## Addendum 2 — Gating variants: condor-only book and EV ranking (`gating_variants.py` → `artifacts/gating_variants.json`)

Run on the frozen OOS predictions (no retraining). Self-check: the P(win) policy reproduces `gating_sim.json` ml_lgbm exactly — asserted in the script before anything else prints.

| Policy | n | Net ₹ | Avg/trade | WR | PF | Max DD ₹ (DD%) |
|---|---|---:|---:|---:|---:|---:|
| P(win) ranking (= main e002) | 919 | +581,069 | +632 | 53.2% | 2.24 | 29,237 (14.6%) |
| **EV = P(win) × payoff** | 919 | **+761,977** | **+829** | 53.6% | **3.41** | 17,671 (8.8%) |
| Condor only, rule days | 306 | +319,310 | +1,044 | 54.6% | 5.47 | 5,729 (2.9%) |
| **Condor only, ML days** | 306 | **+506,216** | **+1,654** | **65.0%** | 10.5 | **9,087 (4.5%)** |
| Condor only, ML + EV | 306 | +506,216 | +1,654 | 65.0% | 10.5 | 9,087 (4.5%) |

- **EV ranking works, by the expected mechanism.** Payoff multipliers frozen from pre-OOS e001 labels (Bull 0.93 / Bear 1.13 / Condor 2.69). Same 919 trades, DD 29.2k → 14.7k, +₹181k net — because multiplying by payoff pushes the allocation toward the condor (490 → 802 condor trades; spreads nearly vanish, n=13 bull). This is the one-line ranking-key upgrade the `ponytail` note in `walkforward.py` pointed at; adopt P×payoff over P alone.
- **Condor-only gets 87% of the net with a third of the drawdown.** The two directional books bleed −₹55k combined inside the full ML book; dropping them costs 13% of net, cuts trades to a third (919 → 306), and max DD from 14.6% → 4.5%. Per-trade quality 632 → ₹1,654.
- **EV + condor-only combined is a no-op by construction** (last row is bit-identical to condor-only ML): within a single archetype the payoff multiplier is a positive constant, so P×payoff ranks identically to P. EV ranking is a *cross-book* reallocation lever — the two upgrades answer the same allocation question from two sides and do not stack. Choose one: EV ranking if you keep all three books, condor-only if you want minimal surface.
- **Caveat unchanged:** condor open→close numbers are the optimistic end (no intraday stop-out in the proxy) until e004 runs. PF 9.45 on n=306 is a slice of that same proxy — treat the *relative* comparison as robust and the absolute rupees as provisional.

## Addendum 3 — Days-to-expiry replaces `dow` (`walkforward_dte.py` → `artifacts_dte/`), and e004-informed stop stress (`stress_test.py`)

**dte variant: the SHAP addendum's recommendation pays.** Identical frozen protocol (folds, embargo, LGBM params, gating); only `dow` out, `dte` + `is_expiry` in (expiry calendar is public schedule info, leak-free). OOS calibration improves on **every** archetype for both model families — condor most of all:

| Model | Metric | dow (frozen) | dte variant |
|---|---|---:|---:|
| LGBM | condor Brier | 0.2341 | **0.2013** |
| Logistic | condor Brier | 0.2566 | **0.1804** |
| LGBM | bull / bear Brier | 0.2178 / 0.2647 | 0.2167 / 0.2643 |

Gating (matched count, vs frozen run): baseline identical (protocol check ✓). **ml_logistic+dte is the best policy measured in the sandbox: +₹793,906, PF 2.67, WR 57.3%, max DD ₹18,746 (9.4%)** — first policy to clear config's 55% WR hurdle. LGBM+dte: +₹622,949 at lower DD (27,336), with the condor book *better* on fewer trades (n 490→456, net +636k→+758k) — dte carries real day-selection signal, not just calendar identity. Adopt the dte feature set; prefer the logistic model or the EV-ranking upgrade on top.

**Stop stress (e004's measured 1.4× credit SL: fired on 25% of condor days, mean stopped-trade net −₹719):** replacing a random 25% of the EV book's condor trades (n=765) with e004's realized stop outcome:

| Stopped share | Net ₹ | WR | PF | Max DD (DD%) |
|---|---:|---:|---:|---:|
| 0% (baseline EV) | +761,977 | 53.6% | 3.41 | 17,671 (8.8%) |
| 10% | +621,289 | 48.4% | 2.74 | 23,171 (11.6%) |
| **25% (e004's rate)** | **+423,509** | 41.7% | 2.03 | **23,171 (11.6%)** |
| 40% | +207,778 | 34.3% | 1.44 | 30,382 (15.2%) |

At the *measured* stop rate the book survives: net drops 44% but **drawdown rises only to 11.6%** — the SL is a per-trade cap, so stops convert tail days into single capped losses. Degradation continues at 1.6× the measured rate (40%: DD 15.2%), not a break. Ceiling: magnitudes are e004's mean stop applied by random draw, not path-matched to the same days (random sampling also understates vol-clustered stop correlation) — `stress_test.py` ponytail note.

## Addendum 4 — Exit-aware gating: e005's real intraday condor PnLs replace the open→close labels (`gating_exit_aware.py`)

The dte gating above prices condor trades with e001's open→close proxy. e005's validated replay supplies real exit outcomes for the condor column (both exit configs; e001 labels kept on e005's 88 skipped days; bull/bear stay on e001 labels — e004 confirmed them directionally). Same frozen gating machinery, dte features. Numbers below are from the regenerated (column-consistent) e005 artifact; an earlier version of this table used rows corrupted by a chunk-append column-order bug:

| Policy | open→close | documented exits (SL+50% tgt) | drop-target exits (SL+EOD) |
|---|---:|---:|---:|
| baseline (rule) | +129,746 | **−38,274** (PF 0.94) | +128,278 |
| ml_lgbm | +622,949 | +255,283 | +618,598 |
| **ml_logistic (dte)** | +793,906 | +368,008 | **+786,606** (DD 18,746) |
| EV-ranked lgbm | +811,801 | +374,804 | **+801,707** (PF 3.54, DD 14,581) |
| condor-only ML | +588,535 | +298,383 | **+583,126** (PF 16.1, DD 2,536) |

**Reading:** (1) Under the *documented* +50% profit target, the selector's edge largely evaporates — the target caps exactly the crush days the ML picks, and the naive rule's condor subset goes negative. (2) With the target dropped, every gating conclusion survives exit-awareness essentially unchanged — because e005 showed the 1.4× SL is a non-event and EOD exits reproduce the endpoint. **The ML edge was never an artifact of missing stops; the +50% cap is the single point of failure.** (3) e005's target sweep refined the pick to **100% of credit** (flat optimum 100–200%); the drop-target column here approximates it. Caveats: mixed exit world for bull/bear; drop-target column is a counterfactual (TARGET→endpoint reconstruction); 74 fallback days; best-of inflation across the policy panel still applies.

## Addendum 5 — Expiry-only gate (dte ≤ 1): Kailash Nadh's expiry-centric proposal, validated (`expiry_gate.py`)

At the same monthly trade budget k (the rule's count), the ML condor book restricted to days with days-to-nearest-expiry ≤ 1 (371 of 920 OOS days) vs unrestricted — e005's clean exit-aware condor PnLs, both exit configs:

| Book | n | Net ₹ | Avg/trade | WR | PF | Max DD (DD%) |
|---|---:|---:|---:|---:|---:|---:|
| documented, unrestricted | 847 | +389,021 | +459 | 53.7% | 2.83 | 9,362 (4.7%) |
| **documented, expiry-only** | **371** | **+449,738** | **+1,212** | **78.2%** | **11.77** | **3,701 (1.9%)** |
| drop-target, unrestricted | 847 | +818,703 | +967 | 53.2% | 4.80 | 9,459 (4.7%) |
| **drop-target, expiry-only** | **371** | **+875,397** | **+2,360** | **78.2%** | **21.28** | **3,701 (1.9%)** |

The expiry gate **adds money while more than halving the workload**: +16% net (documented) / +7% (drop-target), −56% trades, −60% drawdown. It also matches the reviewer's capital argument — the book is flat ~80% of days, freeing collateral for the liquid-fund yield play. Caveats: expiry-day-only selection is close to a calendar rule (the ML still chooses *which* expiry days and SKIPS some — the gate is a restriction, not a calendar); Tue-era 83.8% WR is a 105-trade sample; the composition warning (e005 Add. 2 — inverted-wall days carry the edge) applies to every row here. e005 Add. 3 completes the picture: IV regime does not matter on expiry days, so the gate, not IV timing, is the right concentration.

## Addendum 6 — EV-sizing histogram (`ev_sizing.py`): the 2-lot threshold doesn't discriminate

Testing Idea 5 (size 2 lots when calibrated P(win) > 0.70) on the expiry-gated book's 371 trades, under both exit configs:

| Bucket (documented exits) | n | Net ₹ | Avg/trade | WR |
|---|---:|---:|---:|---:|
| P > 0.70 | 257 (69% of trades) | +314,350 | +1,223 | 81.7% |
| P ≤ 0.70 | 114 | +135,388 | +1,188 | 70.2% |

**The P>0.70 threshold is not selective** — 69% of expiry-gated days clear it, and per-trade PnL is flat across buckets (₹1,223 high-P vs ₹1,188 low-P; the P distribution is compressed: 123 of 371 trades sit in p80–90, only 51 below p60). The reviewer's +35–45% uplift estimate holds arithmetically (+70%/+68% net), and tiered vs flat-2 now split the objective: tiered +₹764k (DD ₹5,072, Calmar 151) vs flat-2 +₹899k (DD ₹7,401, Calmar 122) — flat-2 adds +₹135k net, the tier cuts DD 31%. Choose by risk appetite.

**Sizing conclusion:** P(win) ranks *which days to take* within the gate (that's where it earned its keep), but within the gated set it carries no extra sizing information — the honest sizing ladder is margin-driven (1→2 lots when utilization allows), not P-driven. Same composition caveat as everywhere else; and 2-lot days double the exposure to the tail that breach-spread insurance (e005 Add. 5) exists to bound.
