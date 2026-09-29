# Collated Experiment Results

All sims: ₹2,00,000 bankroll (config.TOTAL_CAPITAL), 1 lot era-correct (25→75→65), real Zerodha friction already netted, **no compounding**.
₹/yr = net ÷ window years; **Max DD%** = peak-to-trough of net equity ÷ ₹2,00,000. OOS windows stated per row; nothing annualized across windows.

## Verdicts (≤2 lines each)

- **e001 leak-free replay** — GOOD: honest measurement pipeline (4,245 leak-free labels) and the iron condor survives honesty (PF 3.7–4.3). BAD: naive t-1 momentum spreads bleed (bull PF 0.50, bear 0.85); the old engine's PF 22 is confirmed look-ahead fiction. *Learning: short-vol on flat days is the only daily edge that replicates.*

- **e002 regime models** — GOOD: ML day/archetype selector at the same trade count: +₹446k vs +₹108k, PF 1.20→2.01, max DD cut 58%, calibrated (Brier beats base rate). BAD: directional spreads stay net-negative even under ML; LGBM barely beats logistic. *Learning: the value is allocation, and the condor edge is an expiry-day 0DTE effect that migrated Thu→Tue with NSE's change — use days-to-expiry, not weekday.*

- **e003 meta-labeling** — GOOD: filtering raises per-trade quality (avg ₹121→₹333 at 55% keep, net +₹165k > +₹108k). BAD: no per-trade skill (Brier 0.245 ≈ base 0.243) — it wins only by re-learning archetype base rates, and is dominated by e002 (₹490/trade at full count vs ₹493 at 31%). *Learning: day/archetype selection > trade filtering; revisit meta-labeling only with intraday features.*

- **e004 intraday replay** — GOOD: simulator complete and validated (7 tests), reuses core BS greeks, no-look-ahead walls/IV/DTE. BAD: no real run yet — blocked on 5-min backfill (Dhan depth unknown). *Learning: at 1 DTE fixed-IV BS reprice is near-intrinsic, so late-week debit-spread targets fire too easily — bias documented before it could mislead.*

## Results (net, era-correct lots)

| Policy | OOS window | Cap used | Net ₹ | ₹/yr | %/yr | Max DD ₹ | DD % |
|---|---|---|---:|---:|---:|---:|---:|
| e001 rule-selected (naive t-1 rule, full span) | 2021-01→2026-09 (5.7 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +87,440 | 15.3k | 7.6% | 67,526 | 33.8% |
| e002 baseline (same rule, OOS slice) | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +108,306 | 28.9k | 14.4% | 67,526 | 33.8% |
| **e002 ML-LGBM selector** | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | **+446,344** | **119.0k** | **59.5%** | **28,543** | **14.3%** |
| e002 ML-logistic selector | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +376,794 | 100.5k | 50.2% | 31,025 | 15.5% |
| e003 meta-filter τ=0.40 (55% keep) | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +164,593 | 43.9k | 21.9% | 28,165 | 14.1% |
| e003 e002-style selector | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +439,345 | 117.2k | 58.6% | 29,303 | 14.7% |
| e004 intraday exits | not run | — | — | — | — | — | — |

Trade counts (matched within each experiment): e001 n=1,386; e002 baseline 920 / ML 919; e003 n=897 (τ=0.40 keeps 494).

**Bottom line:** e002-style day/archetype selection is the only pattern worth productionizing (~59%/yr, DD 14% vs 34%) — but its best WR is 51.8%, still under the 55% config hurdle, and absolute ₹ levels wait on e004's intraday exits.

---
Recomputed from artifacts 2026-09-29: e001 `artifacts/labels_daily.csv` (max DD from rule-selected daily equity), e002 `artifacts/gating_sim.json`, e003 `artifacts/policy_comparison.json`. ₹ levels are not comparable across lot eras (25→75→65); treat cross-era rupees as approximate.
