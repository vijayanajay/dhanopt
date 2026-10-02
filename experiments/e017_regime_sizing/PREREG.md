# E017 — Regime-Based Position Sizing on the E011 Delta-Hedged Straddle
**Pre-Registration Protocol (Frozen 2026-10-02, before the sizing run)**

**Question:** E011 passed Sharpe/PF/slippage gates but FAILED the drawdown gate (max DD −₹51,274 = 25.6% of ₹2L vs the ≤8% = ₹16,000 ceiling); E016 proved wings make it worse. Does **halving position size when the realized-vol regime is elevated or after loss clusters** bring max drawdown under ₹16,000 while keeping expectancy intact — and if not, what fixed fraction (or loss-cluster stop) does?

---

## 1. Base (Frozen E011 — Untouched)
* Signal: VRPₜ₋₁ ≥ 80th percentile of trailing 60 sessions, VRP > 0 (`vrp_signal`); the same 293 frozen sessions from `experiments/e011_vrp_delta_hedge/artifacts/vrp_daily.csv`.
* Entry Bar 1 Open, ATM strike, |Δ_net| ≥ 0.15 rebalancing at t+1 bar Open, exit 15:15, era-correct lot sizes, full Zerodha friction. No re-simulation: sizing acts per-session on the frozen per-session records; sessions excluded by the Phase-1 margin gate stay excluded.

## 2. The Only Degree of Freedom — Size Fraction
$$f_t = 0.5 \text{ if (elevated RV regime } \textbf{OR} \text{ loss-cluster active)} \text{ else } 1.0$$

* **Elevated RV regime:** σ_GK,10d(t−1) > **75th percentile** of its own trailing **60 sessions** — `rolling(60, min_periods=30).quantile(0.75).shift(1)` on `sigma_gk_10d_t1`, the identical no-look-ahead machinery as the VRP entry gate. NaN hurdle (warm-up) → **not** elevated (fail-open to full size).
* **Loss cluster:** the two most recent **taken** sessions both closed net-negative → half size **until a taken session closes net-positive**. Outcomes are measured on the scaled book (a half-size session that nets < 0 is a loss); net ≥ 0 resets the streak.
* Both flags are known at decision time (t−1 data / own trade history). No other parameter changes.

## 3. Sizing Mechanics — Exact Fractional Arithmetic
From the engine cost model, per-session PnL is **linear in the size fraction**:
`net(f) = f·net(1) − (1−f)·flat`, with `flat = ₹94.40 (entry+exit brokerage+GST) + ₹23.60 × hedge_trades`.
* ₹20/order brokerage + 18% GST are per-order flat — same order count at any size.
* Everything else (STT, exchange charges, ₹1.5-pt option slippage, futures PnL/STT/exchange) is proportional to lot multiples — scales with f.
* Hedge trade count is size-invariant: the trigger is per-share (|Δ_net| ≥ 0.15 on per-share delta, orders in per-share units scaled by lot), so the hedge sequence is identical at f = 0.5.
* Validated before use: flat + variable decomposition must reproduce every frozen `net_pnl` exactly at f = 1, and the recovered variable friction must be ≥ the analytic option-book variable component (residual = futures turnover costs, ≥ 0).

**Known ceilings (deliberate):** fractional lots (0.5 × 75 = 37.5) are not live-tradeable — this measures the **information content of the sizing signal** as a fractional bound. The live 1-lot implementation is *skip* flagged sessions instead; a skip-semantics diagnostic is reported. `ponytail:` upgrade path = 1-lot granularity (skip semantics) or capital scaling; ceiling noted in README.

## 4. Pre-Registered Evaluations
* **PRIMARY:** combined rule (regime OR cluster). Gates apply here.
* **Attribution diagnostics** (declared now, no gate-bearing role): regime-only; cluster-only.

## 5. Pre-Registered Kill Criteria (on PRIMARY)

| # | Metric | Pass Threshold | Observed | Status |
|---|---|---|---:|---|
| 1 | Max peak-to-trough drawdown | ≤ ₹16,000 (8.0% of ₹2L) | *pending* | — |
| 2 | Net EV / trade | ≥ +₹1,200 (~47% of E011's +₹2,537.79) | *pending* | — |
| 3 | Total net PnL | ≥ ₹3,71,786 (50% of +₹7,43,572.25) | *pending* | — |

**Verdict rule:** all pass → Phase 6 shadow candidate (with the 1-lot granularity caveat). Gate 1 alone fails → rule at f = 0.5 insufficient; the risk budget (§6) states the fraction/stop that clears the ceiling. Gates 2 or 3 fail → sizing rule uneconomic; retire.

## 6. Part B — Risk Budget (Descriptive, Declared Now, No Gates)
Same exact arithmetic, reported as tables:
* **Fixed fractions** f ∈ {1.0, 0.75, 0.5, 0.4, 0.3, 0.25} plus the **breakeven fraction f\*** = largest f on a 0.001 grid over [0.05, 1.0] with |max DD| ≤ ₹16,000.
* **Loss-cluster stops at full size:** after k ∈ {2, 3} consecutive losing taken sessions, skip the next **2** signaled sessions (cooldown), then resume; repeat while the streak persists. Skipped sessions contribute 0.
* Columns each: max DD (₹, % of ₹2L), total net, EV/trade (taken), Sharpe (5.7-yr convention), annual PnL (÷5.7), annual cost vs E011 (+₹1,30,451.27/yr = 7,43,572.25/5.7).

## 7. Reproduce
`uv run python -m experiments.e017_regime_sizing.sizing` → `artifacts/sizing_daily.csv`, `artifacts/sizing_metrics.json`, `artifacts/risk_budget.json`.
