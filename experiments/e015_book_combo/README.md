# E015 — Book Composition Analysis: E011 VRP Straddle × E013 Pin Fly on one ₹2L account

**Question:** Do the two validated books stack? Session overlap, same-day co-movement, joint drawdown, and ₹2L capital utilization — computed by pure arithmetic over the two frozen published artifacts (no re-simulation, no new parameters).

---

## 1. Verdict — They Stack Well as Alpha, Not as Margin (Yet)

* **Overlap is essentially independent:** 44 sessions trade both books, vs **40.1 expected** if session selection were random. Same-day PnL correlation is weakly positive (**+0.18**) — the books do not lose together on overlap days.
* **Combining cuts the joint drawdown materially:** −₹51,274 (25.6%) E011-alone → **−₹32,076 (16.0%) combined**, while adding E013's entire +₹4.15L. The drawdown still exceeds the 8% institutional ceiling — **E011's tail remains the binding constraint**, wings (Phase 4 architecture) or regime scaling are the fixes, not diversification alone.
* **Margin stacking is the real constraint:** under the conservative Phase 1 upper bound (naked-straddle margin for both books), **10 of the 44 overlap days breach the ₹1,82,000 usable margin**, all in the high-spot 65-lot era (Dec-2024 onward, combined upper bound ₹2.46L–₹3.07L). Single-book days never breach (max ₹1.54L). The Pin Fly's true margin is *lower* than the bound (long wings reduce it) — the real number must come from broker RMS before live stacking.

---

## 2. Overlap & Co-Movement (2021-01 → 2026-09, 1,410 sessions)

| Stat | Value |
|---|---:|
| E011 VRP sessions | 293 (20.8% of calendar) |
| E013 Pin Fly sessions | 193 (13.7% of calendar) |
| Overlap (both books same day) | **44** (22.8% of Pin Fly sessions) |
| Expected overlap if independent | 40.1 |
| Same-day PnL correlation (overlap days) | **+0.18** |
| Joint book-session win rate on overlap days | 93.2% |

The books select sessions by different mechanisms — E011 by a volatility-premium percentile gate, E013 by expiry-day morning compression — and they do not cluster on the same days.

## 3. Combined Book (442 trade-days)

| Metric | E011 alone | E013 alone | **Combined** |
|---|---:|---:|---:|
| Total net PnL | +₹7,43,572 | +₹4,14,721 | **+₹11,58,293** |
| Net EV / trade-day | +₹2,537.79 | +₹2,148.81 | **+₹2,620.57** |
| Win rate | 61.1% | 83.9% | **68.3%** |
| Profit factor | 3.99 | 9.41 | **4.93** |
| Sharpe (repo convention) | 2.85 | 5.52 | **4.14** |
| Max drawdown | −₹51,274 (25.6%) | −₹11,940 (5.97%) | **−₹32,076 (16.0%)** |
| Annual run-rate | +₹1,30,451 | +₹72,758 | **+₹2,03,209** |

Combined max drawdown trough: **2023-09-22** (E011's 2022–23 choppy cluster). The five worst combined days are all single-book days — no overlap day appears in the worst-five list; E013 caps the downside exactly when E011 bleeds.

Yearly combined net: 2021 −₹2.4k · 2022 +₹1.04L · 2023 −₹0.4k · 2024 +₹1.75L · 2025 +₹5.96L · 2026 +₹2.86L.

## 4. Capital Utilization (₹1,82,000 usable, Phase 1 engine)

| Stat | Value |
|---|---:|
| Avg margin used per trade day (upper bound) | ₹1,03,477 (**56.9%** of usable) |
| Max concurrent margin (upper bound) | ₹3,07,026 (2025-12-02) |
| Margin-day utilization over the full calendar | 17.8% |
| Capacity-breach days (upper bound) | **10** (all stacked overlap days) |
| Breach era | Dec-2024 → Sep-2026 (65-lot, high spot) |

**Method note:** margin = `CollateralManager.estimate_straddle_margin` per book-session (7.84% of contract value). For the Pin Fly this is an explicit **upper bound** — its long wings only reduce required margin, never increase it — so the 10 breaches are conservative; the true stacking feasibility depends on broker RMS margin for the iron fly. Action for Phase 6: verify fly margin in the live account before running both books concurrently; if stacking breaches persist, apply a priority rule (E013 takes the slot on overlap days — higher Sharpe, lower DD).

## 5. Artifacts

* `artifacts/combo_metrics.json` — full metric blocks, overlap stats, capital analysis, yearly breakdown.
* `artifacts/combo_daily.csv` — 442 date rows with per-book PnL, margin (upper bound), breach flag, cumulative curve.
