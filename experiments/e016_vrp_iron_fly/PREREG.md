# E016 — VRP-Gated Iron Fly: Defined-Risk Wings on the E011 Delta-Hedged Straddle
**Pre-Registration Protocol (Frozen 2026-10-02, before the replay run)**

**Question:** E011 passed Sharpe (2.85) and slippage-cliff gates but FAILED the drawdown gate (max DD −₹51,274 = 25.6% of ₹2L vs the ≤8% ceiling). Does converting the naked short straddle into an **Iron Fly** (long CE + PE wings) — keeping every other frozen E011 rule identical — bring max drawdown under ₹16,000 while retaining positive expectancy?

---

## 1. What Changes vs E011 (and What Does Not)

**Identical to E011 (frozen, untouched):**
* Signal: VRPₜ₋₁ ≥ 80th percentile of trailing 60 sessions, VRP > 0 (`vrp_signal`).
* Entry at Bar 1 Open (09:20 IST), ATM strike = round(spot/50)×50.
* Delta threshold rebalancing: |Δ_net| ≥ **0.15**, fills strictly at t+1 bar Open.
* Exit 15:15 IST (Bar 71 close); expiry-day settlement at intrinsic.
* Friction: identical schedule, now applied at ₹20/leg (2 legs → ₹40 entry/exit as published; 4 legs → ₹80).
* Phase 1 collateral gate unchanged (straddle margin = upper bound for the fly; long wings only reduce required margin).
* Lots: era-correct via `experiments.common.lots`.

**New (the only degree of freedom — wing width):**
* Buy 1 lot CE wing at strike + W and 1 lot PE wing at strike − W at entry; hold to exit.
* **Adaptive width rule:** W = **max(150, 1.0 × σ_GK,10d,ₜ₋₁ × √(DTE/365) × S)** index points, rounded to the 50-point strike grid. Wide enough that the wing delta ~0 at entry (hedge churn collapses), tight enough to retain meaningful credit. Rationale: 1σ of the *realized* distribution over the position horizon — the risk we are actually insuring.
* Per-side overrides (`wing_offset_ce` / `wing_offset_pe`) exist in the engine for diagnostics only; the frozen rule is symmetric.

**Mechanics note (from the pre-run smoke test):** with wings on, the portfolio delta includes the wings' own (positive) deltas, so net gamma shrinks and hedge count drops sharply (verified: 3 → 0 hedges on 2021-03-01). Friction lines scale exactly with leg count; STT/exchange stay on net premium turnover.

## 2. Replay Scope
All 293 frozen E011 signaled sessions (`vrp_daily.csv`), same candles, same IV/DTE, same threshold. One pass at the frozen rule; one fixed-width diagnostic table (W ∈ {100, 150, 200, 250, 300}) reported separately — the diagnostic is **not** used for selection.

## 3. Pre-Registered Kill Criteria (vs E011's failed gate)

| # | Metric | Pass Threshold | Observed | Status |
|---|---|---|---:|---|
| 1 | Max peak-to-trough drawdown | ≤ ₹16,000 (8.0% of ₹2L) | *pending* | — |
| 2 | Total net PnL retains positive expectancy | Net EV/trade ≥ +₹500 | *pending* | — |
| 3 | Total net PnL | ≥ 40% of E011's +₹7,43,572 (≥ +₹2.97L) | *pending* | — |

**Verdict rule:** pass = {1, 2, 3} all true → wings become the Phase 6 shadow candidate. Fail on 1 alone → escalate width rule (e.g. 1.25σ) in a NEW pre-registration. Fail on 2 or 3 → wings uneconomic; naked straddle architecture retired from live consideration.
