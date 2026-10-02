# E017 — Regime-Based Position Sizing on the E011 Delta-Hedged Straddle

**Contract & Pre-Registration:** [PREREG.md](PREREG.md) — frozen 2026-10-02 before the run.
**Question:** Does halving size in elevated-RV regimes or after loss clusters bring E011's max drawdown under the ₹16,000 (8%) ceiling with expectancy intact — and if not, what fixed fraction (or loss-cluster stop) does?

---

## 1. Verdict — SIZING RULE KILLED ❌; Risk Budget: NO FRACTION REACHES 8%; only *skipping* moves the needle

| Gate | Bar | Observed (Combined Rule) | Status |
|---|---|---:|---|
| 1. Max drawdown | ≤ ₹16,000 | **−₹50,859 (25.43%)** | ❌ FAIL |
| 2. Net EV / trade | ≥ +₹1,200 | +₹2,023.23 | ✅ PASS |
| 3. Total net vs E011 | ≥ ₹3,71,786 | +₹5,92,806 (79.7%) | ✅ PASS |

Expectancy survives sizing (Gates 2–3 pass), but the drawdown barely moves: **−₹51,274 → −₹50,859**. And the risk budget below proves why no fixed fraction could ever pass: the drawdown floor is the **flat per-order fee treadmill**, not position size.

## 2. Results (293 frozen E011 sessions; exact fractional-size arithmetic, f ∈ {0.5, 1.0})

| Metric | E011 base (f=1) | **Combined (primary)** | Regime-only | Cluster-only |
|---|---:|---:|---:|---:|
| Total net PnL | +₹7,43,572 | **+₹5,92,806** | +₹6,10,306 | +₹7,24,664 |
| Net EV / trade | +₹2,537.79 | **+₹2,023.23** | +₹2,082.96 | +₹2,473.25 |
| Win rate | 61.1% | 59.7% | 60.4% | 60.4% |
| Profit factor | 3.99 | 3.82 | 3.76 | 4.17 |
| Sharpe | 2.85 | 2.61 | 2.65 | 2.82 |
| **Max DD** | −₹51,274 (25.64%) | **−₹50,859 (25.43%)** | −₹49,270 (24.64%) | **−₹52,912 (26.46%)** |
| Annual net (÷5.7) | +₹1,30,451 | +₹1,04,001 (−₹26,450/yr) | +₹1,07,071 (−₹23,380/yr) | +₹1,27,134 (−₹3,317/yr) |
| Sessions halved | 0 | 118 of 293 (avg f 0.797) | 79 | 39 |

* **Regime flag** (σ_GK,10d(t−1) > trailing-60 75th pct): 79 sessions halved cost **₹1.33L of PnL for ₹2,004 of DD relief** — elevated-RV sessions are above-average *winners* (the VRP is widest exactly when RV is high), so half-sizing them trades income for almost no tail relief.
* **Cluster flag** (2 consecutive losses → half until a win): actually **deepens** DD by ₹1,638. Under flat-fee drag, half-sizing converts marginal wins into losses (net(f) = f·net(1) − (1−f)·flat), so the rule shaves exactly the recovery legs that repair the equity curve.
* 118 halved sessions under the combined rule still leave DD at 25.4% — the flags do not overlap the drawdown window's cost structure (see §3).

## 3. Why Sizing Cannot Fix This Drawdown — the Friction Treadmill (Measured)

The max DD is **not** a few trend days: it is a 21-month chop, **2022-11-03 → 2024-07-05, 86 sessions**, full-size net −₹45,409 — of which **₹29,476 (65%) is flat per-order fees** (₹94.40 entry/exit + ₹23.60 × 905 hedge orders). Halving a session's size halves its gross and turnover costs but keeps **every rupee of per-order brokerage**. Consequences, all exact under `net(f) = f·net(1) − (1−f)·flat`:

* **DD(f) is U-shaped, with its minimum ≈ −₹40,542 at f ≈ 0.52** — still 2.5× the ceiling.
* Below f ≈ 0.6, downsizing makes the drawdown **worse**: at f = 0.25, DD −₹47,852; at f = 0.06, DD −₹54,935 — *deeper than full size*. A quarter-size book forfeits most of its +₹7.4L gross while still paying ₹83,166 of flat fees over the sample, and the choppy windows rack up the fees fastest.
* Total flat fees across 293 sessions: **₹83,166** (₹27,659 option entry/exit brokerage+GST + ₹55,507 futures brokerage on 2,352 hedge orders). This is the floor no fractional size can cross.

## 4. Part B — E011 Risk Budget (descriptive; frozen variant list in PREREG §6)

**Fixed fractions** (all 293 sessions, size f):

| f | Total net | EV/trade | Sharpe | Max DD | DD % | Annual net | Annual cost vs E011 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1.00 | +₹7,43,572 | +₹2,538 | 2.85 | −₹51,274 | 25.64% | +₹1,30,451 | — |
| 0.75 | +₹5,36,888 | +₹1,832 | 2.74 | −₹45,032 | 22.52% | +₹94,191 | ₹36,260/yr |
| 0.515 (grid min DD) | +₹3,42,604 | +₹1,169 | 2.55 | **−₹40,542** | 20.27% | +₹60,105 | ₹70,346/yr |
| 0.50 | +₹3,30,203 | +₹1,127 | 2.51 | −₹40,938 | 20.47% | +₹57,930 | ₹72,521/yr |
| 0.40 | +₹2,47,529 | +₹845 | 2.33 | −₹43,682 | 21.84% | +₹43,426 | ₹87,025/yr |
| 0.25 | +₹1,23,518 | +₹422 | 1.83 | −₹47,852 | 23.93% | +₹21,670 | ₹1,08,781/yr |

**Breakeven fraction: does not exist.** A 0.001-step scan over f ∈ [0.05, 1.0] finds no fraction with |max DD| ≤ ₹16,000; the best achievable is −₹40,542 (f ≈ 0.515), a 20.3% drawdown. **There is no fixed fraction of 1 lot that keeps E011's DD under 8% on a ₹2L bankroll.**

**Loss-cluster stops at full size** (after k consecutive losing sessions, skip the next 2 signaled sessions, resume; skipped = flat, zero fees):

| Stop | Taken | Total net | EV/trade | Sharpe | Max DD | DD % | Annual net vs E011 |
|---|---:|---:|---:|---:|---:|---:|---:|
| k=2, cooldown 2 | 209 | +₹7,01,829 | +₹3,358 | 2.94 | −₹33,991 | 17.00% | −₹7,323/yr |
| **k=3, cooldown 2** | 261 | **+₹7,58,100** | +₹2,905 | **2.98** | −₹34,728 | 17.36% | **+₹2,549/yr** |

* The **k=3 stop is a free lunch on this sample**: it Pareto-dominates the published E011 book on every metric (+₹14,528 PnL, −₹16,546 DD, Sharpe 2.85→2.98, PF 4.61) because the 32 skipped sessions netted −₹14,528 — sitting out two sessions after three straight losses removes losers at almost no cost. It was pre-declared in PREREG §6 as a descriptive variant, **not** tuned post-hoc; adopting it as the operating policy still requires a new pre-registration (E018) and it still fails the 8% ceiling (17.4%).
* Skipping beats sizing precisely because a skipped session pays no fees — the only way under the friction floor.

**Capital reframe (the honest risk-budget answer):** to hold the observed DD inside the 8% budget, E011 needs **₹6,40,930** of capital at full size; with the k=3 stop, **₹4,34,100**; the E015 combined book (DD ₹32,076) needs **₹4,00,950**. On the mandated ₹2L, the 8% ceiling is unreachable for the naked delta-hedged straddle by any sizing tested (E016 wings, E017 fractions/stops). Remaining levers: fewer hedge orders (rebalance-threshold work), hybrid passive exits (E014), book diversification (E015), or a larger capital base.

## 5. Method Notes & Ceilings

* **Exactness:** per-session PnL is linear in the size fraction under the frozen cost model — flat ₹20/order fees (+18% GST) are size-invariant; STT, exchange, slippage and futures PnL scale with lot multiples; the hedge trigger is per-share so the hedge sequence is identical at any size. Validated: f=1 reconstruction reproduces every frozen `net_pnl` (total +₹7,43,572.25) and the no-hedge sessions (11) carry exactly zero futures-cost residual, pinning the flat constants.
* **Fractional-lot ceiling** (`ponytail:`): 0.5 × 75 = 37.5 shares is not live-tradeable — E017 measures the *information content* of the sizing signal as a fractional bound; the live 1-lot analogue is skip-semantics (exactly what the cluster-stop rows evaluate). Upgrade path: capital scaling or 1-lot skip rules.
* Stop EV/Sharpe are computed on taken sessions only; the equity curve treats skipped sessions as zero (flat, no fees).

## 6. Artifacts & Tests

* `artifacts/sizing_daily.csv` — per-session flags (`regime_elevated`, `cluster_active`), size fractions, scaled PnL and drawdown for the primary rule.
* `artifacts/sizing_metrics.json` — FROZEN params, base/primary/diagnostic metrics, gate evaluations.
* `artifacts/risk_budget.json` — fixed-fraction table, breakeven scan (none exists), DD(f) curve, cluster-stop table.
* 18 tests in [test_e017.py](test_e017.py): decomposition fidelity (frozen totals, hand-pinned row 1, no-hedge residual), scaling linearity and marginal-win sign flips, rule semantics (cluster streak, regime independence, outcome-at-taken-size), no-lookahead regime flags, cluster-stop state machine, analytic breakeven, gates.
