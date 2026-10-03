# E016 — VRP-Gated Iron Fly: Defined-Risk Wings on the E011 Delta-Hedged Straddle

> **⚠ STRUCK FIGURES — `₹7,43,572` is VOID (e018) and `₹1,56,941` inherits it.** The wings finding (cap the tail, not the drawdown) is untested on a correct contract.


**Contract & Pre-Registration:** [PREREG.md](PREREG.md) — frozen 2026-10-02 before the replay run.
**Question:** Does converting the naked short straddle into an Iron Fly (long CE + PE wings, all other frozen E011 rules unchanged) bring max drawdown under ₹16,000 while retaining positive expectancy?

---

## 1. Verdict — KILLED ❌ (All Three Gates Fail Decisively)

| Gate | Bar | Observed (Adaptive Fly) | Status |
|---|---|---:|---|
| 1. Max drawdown | ≤ ₹16,000 | **−₹2,03,033 (101.5% of ₹2L)** | ❌ FAIL |
| 2. Net EV / trade | ≥ +₹500 | **−₹535.63** | ❌ FAIL |
| 3. Total net vs E011 | ≥ 40% of +₹7,43,572 | **−₹1,56,941 (−21.1%)** | ❌ FAIL |

The wings **multiplied** the tail risk they were meant to cap.

## 2. Results (293 frozen E011 sessions, 2021–2026, identical signal/timing/threshold)

| Metric | E011 Naked (published) | E016 Adaptive Fly (1σ, floor 150) |
|---|---:|---:|
| Total net PnL | **+₹7,43,572** | −₹1,56,941 |
| Net EV / trade | +₹2,537.79 | −₹535.63 |
| Win rate | 61.1% | 29.4% |
| Profit factor | 3.99 | 0.55 |
| Sharpe | 2.85 | −1.61 |
| Max drawdown | −₹51,274 (25.6%) | **−₹2,03,033 (101.5%)** |
| Avg hedges / day | 8.03 | 4.55 |
| Avg friction / trade | ₹912 | ₹1,112 |
| Max single-session loss | −₹9,171 | −₹7,502 |

### Fixed-width diagnostic table (not used for selection; monotonic toward naked as W→∞)

| Wing width | Total net | Net EV | Win rate | PF | Max DD |
|---:|---:|---:|---:|---:|---:|
| 100 pts | −₹2,27,291 | −₹776 | 22.9% | 0.28 | −₹2,35,502 |
| 150 pts | −₹1,65,575 | −₹565 | 27.7% | 0.53 | −₹2,10,240 |
| 200 pts | −₹66,790 | −₹228 | 34.1% | 0.81 | −₹1,75,717 |
| 250 pts | +₹36,960 | +₹126 | 39.3% | 1.11 | −₹1,56,399 |
| 300 pts | +₹1,37,001 | +₹468 | 43.7% | 1.41 | −₹1,36,866 |

Every profitable configuration still fails Gate 1 by ~10×. The naked straddle strictly dominates every winged variant on this signal.

## 3. Why the Wings Bleed — The Mechanism (Measured, Not Asserted)

Decomposing the 293-session PnL against the naked book:

1. **E011's profit engine is the option book, not the hedge:** naked decomposition = options **+₹9,02,397** gross + futures hedges +₹1,08,480 (10.7%). Wings gut the first term: fly option gross collapses to **+₹1,28,284** (−86%), because 1σ wings surrender ~**89 pts/session** of straddle premium — over half the credit — while preserving the short-gamma *sign* of the position.
2. **Per-session loss is capped, but the loss *frequency* is not:** max single fly loss ₹7,502 < naked ₹9,171. But the capped upside truncates the recovery legs — win rate falls 61% → 29% — so the fly loses **less per bad day yet loses far more often**. 293 sessions of that bleed is −₹1.57L, and the cumulative curve sinks 2.03L below water: **the wings cap the tail, not the drawdown.** (Correlation with the naked book's daily PnL: 0.68 — same trend days hurt both, the fly just bleeds slowly every other day too.)
3. **The hedge still pays for trend protection it no longer receives credit for:** fly hedges are *profitable* on balance (+₹40,480 gross) and hedge churn falls (8.0 → 4.6/day) as wing deltas offset gamma — but the 9 trend days (hedge gross < −₹3k) still cost −₹35,959. Worst days remain the same sessions (2021-07-09, 2022-01-21, 2024-02-02): a trend day destroys the fly from *inside* the wings (short strike < spot < wing) while the futures hedge bleeds on whipsaw.
4. **Friction scales with legs, income scales down:** 4-leg entry/exit at ₹20/leg with identical STT/GST machinery adds ~₹58k friction (₹3.26L vs ₹2.67L) on ~45% less gross income.

**Structural conclusion:** with a *continuously delta-hedged* short-gamma book, drawdown is governed by cumulative friction + hedging whipsaw on trend clusters — not by convexity tail exposure. Defined-risk wings trade away exactly the premium that pays for the hedging. The correct instruments for E011's tail are **position sizing on regime** (scale to half size when realized vol regime is elevated / after consecutive loss clusters) or **per-session hard stops on trend confirmation**, to be pre-registered separately.

## 4. Comparison to E013 (Why Wings Worked There but Not Here)

E013's Pin Fly holds for 2h40m on compressed-range days with no hedge — wings cap a *bounded, static* exposure. E011 holds 5h50m through the full intraday path with dynamic hedging — wings cap the payoff while the hedging engine keeps paying trend costs. Same structure, opposite economics; the difference is the **holding dynamics**, not the wings.

## 5. Artifacts & Tests

* `artifacts/fly_daily.csv` — 293 sessions with wing widths, hedge counts, PnL decomposition.
* `artifacts/metrics.json` — frozen params, adaptive result, 5-point diagnostic table, gates.
* 10 tests in [test_e016.py](test_e016.py): width rule (floor/grid/monotonicity), wing seam (defaults unchanged, credit reduction, hedge neutrality, geometric loss cap), frozen-run structure, and naked-baseline fidelity (+₹7,43,572.25 reproduced).
