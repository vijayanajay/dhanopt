# Collated Experiment Results

All sims: ₹2,00,000 bankroll (config.TOTAL_CAPITAL), 1 lot era-correct (25→75→65), real Zerodha friction already netted, **no compounding**.
₹/yr = net ÷ window years; **Max DD%** = peak-to-trough of net equity ÷ ₹2,00,000. OOS windows stated per row; nothing annualized across windows.

## Verdicts (≤2 lines each)

- **e001 leak-free replay** — GOOD: honest measurement pipeline (4,245 leak-free labels) and the iron condor survives honesty (PF 3.7–4.3). BAD: naive t-1 momentum spreads bleed (bull PF 0.50, bear 0.85); the old engine's PF 22 is confirmed look-ahead fiction. *Learning: short-vol on flat days is the only daily edge that replicates.*

- **e002 regime models** — GOOD: ML day/archetype selector at the same trade count: +₹446k vs +₹108k, PF 1.20→2.01, max DD cut 58%, calibrated (Brier beats base rate). BAD: directional spreads stay net-negative even under ML; LGBM barely beats logistic. *Learning: the value is allocation, and the condor edge is an expiry-day 0DTE effect that migrated Thu→Tue with NSE's change — use days-to-expiry, not weekday. (Labels carry e001's condor optimism — see e004.)*

- **e003 meta-labeling** — GOOD: filtering raises per-trade quality (avg ₹121→₹333 at 55% keep, net +₹165k > +₹108k). BAD: no per-trade skill (Brier 0.245 ≈ base 0.243) — it wins only by re-learning archetype base rates, and is dominated by e002 (₹490/trade at full count vs ₹493 at 31%). *Learning: day/archetype selection > trade filtering; revisit meta-labeling only with intraday features.*

- **e004 intraday replay** — GOOD: full-window real run done (1,410 sessions): spread books CONFIRMED net-negative under path exits (bull −₹314k, bear −₹147k — e001's spread verdict survives). BAD: condor column is a pricing artifact — fixed-IV BS strips out the theta decay that IS the condor's income (EOD-only days flip sign vs e001, corr −0.25; expiry-day edge vanishes). *Learning: condor verdict still open; the 1.4× credit SL firing on 25% of days is a real, new sizing input.*

## Results (net, era-correct lots)

| Policy | OOS window | Cap used | Net ₹ | ₹/yr | %/yr | Max DD ₹ | DD % |
|---|---|---|---:|---:|---:|---:|---:|
| e001 rule-selected (naive t-1 rule, full span) | 2021-01→2026-09 (5.7 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +87,440 | 15.3k | 7.6% | 67,526 | 33.8% |
| e002 baseline (same rule, OOS slice) | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +108,306 | 28.9k | 14.4% | 67,526 | 33.8% |
| **e002 ML-LGBM selector** | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | **+446,344** | **119.0k** | **59.5%** | **28,543** | **14.3%** |
| e002 ML-logistic + days-to-expiry (Add. 3) | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | **+653,520** | **174.3k** | **87.1%** | **18,746** | **9.4%** |
| e002 EV ranking (P × payoff, same n=919) | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +583,124 | 155.5k | 77.7% | 28,873 | 14.4% |
| e002 condor-only, ML days (n=306) | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +404,703 | 107.9k | 54.0% | 6,439 | 3.2% |
| e002 ML-logistic selector | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +376,794 | 100.5k | 50.2% | 31,025 | 15.5% |
| e003 meta-filter τ=0.40 (55% keep) | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +164,593 | 43.9k | 21.9% | 28,165 | 14.1% |
| e003 e002-style selector | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +439,345 | 117.2k | 58.6% | 29,303 | 14.7% |
| e004 path exits: bull spread (all days) | 2021-01→2026-09 (5.7 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | −313,851 | −55.1k | −27.5% | 314,588 | 157.3% |
| e004 path exits: bear spread (all days) | 2021-01→2026-09 (5.7 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | −146,502 | −25.7k | −12.9% | 160,690 | 80.3% |
| e004 path exits: condor ⚠ artifact | 2021-01→2026-09 (5.7 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | −547,744* | −96.1k | −48.0% | 547,810 | 273.9% |

Trade counts (matched within each experiment): e001 n=1,386; e002 baseline 920 / ML 919 (dte variant n=919); e003 n=897 (τ=0.40 keeps 494); e004 all-archetype daily replay, no selection.

\* e004 condor row is **invalid as PnL**: fixed-IV Black-Scholes repricing removes intraday theta decay, the condor's entire income — EOD-only days (no stop interference) flip sign vs e001 with −0.25 correlation. Spread rows are valid and confirm e001. The condor question needs theta-aware pricing; e002's condor edge stands until then.

Stop-stress on the EV book (e004's measured 1.4× SL rate, 25% of condor trades stopped at −₹719 mean): net +₹583k → +₹309k, **DD unchanged 14.4% → 15.0%** (per-trade cap); book breaks only at 40% stopped (DD 30.5%).

**Bottom line:** the only confirmed edges are (a) e002-style selection — best with days-to-expiry (logistic+dte: +₹653k, 87%/yr, 9.4% DD, the only policy clearing the 55% WR hurdle) or EV ranking (+₹583k, survives e004's measured stop rate with DD intact) — and (b) NOT trading the directional spreads, confirmed under two independent pricings. The condor's true intraday profile is the one open question — everything else is measured.

---
Recomputed from artifacts 2026-09-29: e001 `artifacts/labels_daily.csv` (max DD from rule-selected daily equity), e002 `artifacts/gating_sim.json` + `gating_variants.json` (self-checked against gating_sim.json), e003 `artifacts/policy_comparison.json`, e004 `artifacts/intraday_replay.csv` (max DD from daily-replayed equity). ₹ levels are not comparable across lot eras (25→75→65); treat cross-era rupees as approximate.
