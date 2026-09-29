# Collated Experiment Results

All sims: ₹2,00,000 bankroll (config.TOTAL_CAPITAL), 1 lot era-correct (25→75→65), real Zerodha friction already netted, **no compounding**.
₹/yr = net ÷ window years; **Max DD%** = peak-to-trough of net equity ÷ ₹2,00,000. OOS windows stated per row; nothing annualized across windows.

## Verdicts (≤2 lines each)

- **e001 leak-free replay** — GOOD: honest measurement pipeline (4,245 leak-free labels) and the iron condor survives honesty (PF 3.7–4.3). BAD: naive t-1 momentum spreads bleed (bull PF 0.50, bear 0.85); the old engine's PF 22 is confirmed look-ahead fiction. *Learning: short-vol on flat days is the only daily edge that replicates.*

- **e002 regime models** — GOOD: ML day/archetype selector at the same trade count: +₹446k vs +₹108k, PF 1.20→2.01, max DD cut 58%, calibrated (Brier beats base rate). BAD: directional spreads stay net-negative even under ML; LGBM barely beats logistic. *Learning: the value is allocation, and the condor edge is an expiry-day 0DTE effect that migrated Thu→Tue with NSE's change — use days-to-expiry, not weekday. (Labels carry e001's condor optimism — see e004.)*

- **e003 meta-labeling** — GOOD: filtering raises per-trade quality (avg ₹121→₹333 at 55% keep, net +₹165k > +₹108k). BAD: no per-trade skill (Brier 0.245 ≈ base 0.243) — it wins only by re-learning archetype base rates, and is dominated by e002 (₹490/trade at full count vs ₹493 at 31%). *Learning: day/archetype selection > trade filtering; revisit meta-labeling only with intraday features.*

- **e004 intraday replay** — GOOD: full-window real run done (1,410 sessions): spread books CONFIRMED net-negative under path exits (bull −₹314k, bear −₹147k — e001's spread verdict survives). BAD: condor column is a pricing artifact — fixed-IV BS strips out the theta decay that IS the condor's income (EOD-only days flip sign vs e001, corr −0.25). *Learning: fixed-IV greeks cannot price credit books; e005 exists to settle the condor properly.*

- **e005 theta-aware condor replay** — GOOD: with honest pricing the condor book survives intraday exits (+₹289k documented, PF 2.05, DD 7.3%; 1.4× SL fires on only 4.2% of days — e004's 25% was artifact), the target sweep picks **100% of credit** (+₹761k, PF 3.76, DD ₹3.9k — 50% was the worst operating point), and Kailash's decay-trailing exits also beat the 50% cap 2.1–2.4× (though they trail the plain 100% target by ₹75k; real gamma spikes are understated by the model, so the trail is a defensible risk overlay). BAD: the **inverted-wall audit** shows valid-structure condors LOSE (−₹55k, PF 0.78) — 107.6% of the frozen edge comes from days where a max-OI wall sat on the wrong side of spot (PF 91.8 on those days). *Learning: the "condor edge" is really a wall-breach directional trade rescued by 0DTE crush; validate those marks against intraday option quotes before believing them. And the edge does NOT scale with IV — high-IV non-expiry days earn almost nothing.*

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
| e005 condor, documented exits (SL + 50% target) | 2021-01→2026-09 (5.7 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +288,581 | 50.6k | 25.3% | 14,608 | 7.3% |
| e005 condor, target = 100% of credit (sweep optimum) | 2021-01→2026-09 (5.7 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +760,856 | 133.5k | 66.7% | 3,888 | 1.9% |

Trade counts (matched within each experiment): e001 n=1,386; e002 baseline 920 / ML 919 (dte variant n=919); e003 n=897 (τ=0.40 keeps 494); e004 all-archetype daily replay, no selection.

\* e004 condor row is **invalid as PnL**: fixed-IV Black-Scholes repricing removes intraday theta decay, the condor's entire income — EOD-only days (no stop interference) flip sign vs e001 with −0.25 correlation. Spread rows are valid and confirm e001. The condor question needs theta-aware pricing; e002's condor edge stands until then.

Stop-stress superseded: e005 measured the real 1.4× SL rate at 4.2% of days (e004's 25% was artifact) — the SL is a non-event. Exit-aware re-gating (e002 Add. 4, clean column): under documented exits the selector collapses (logistic+dte +₹283k, rule baseline −₹43k); with the target at 100% of credit every conclusion survives (EV-ranked +₹639k at 7.3% DD, condor-only ML +₹493k at 1.2% DD).

⚠ **Composition warning (e005 Add. 2):** on valid-structure days (put wall < open < call wall) the condor book *loses* — the entire frozen edge concentrates in inverted-wall days where the position is a directional wall-breach trade, not a premium-crush condor. Everything above inherits this; validate those days' marks against intraday option quotes (or re-define the trade as "sell the breached wall") before production.

**Expiry-centric convergence (e002 Add. 5 + e005 Add. 3, answering Kailash Nadh's review):** gating the ML condor book to dte ≤ 1 days **adds money while cutting trades 56% and DD to 1.2%** (+₹377k documented / +₹748k drop-target at 75–77% WR); IV regime is irrelevant on expiry days (every straddle-IV quintile profitable) and anti-correlated off-expiry (high-IV non-expiry days earn ~nothing) — so the right concentration is the expiry gate, not VIX timing. Decay-trailing exits (75–80% of credit after 14:00) beat the 50% cap 2.1–2.4× but trail the plain 100% target by ~₹75k — keep as an optional gamma-dodge overlay.

**Mark validation (e005 `marks_validation.py`): e005's marks are real.** Dhan 5-min option candles (NSE_FNO) on the latest frozen session (2026-09-25): candle opens == bhavcopy opens **exactly on all 6 legs**; closes within ₹0.90 last-trade-vs-settlement noise. The "inverted" walls are prior-OI walls above a spot that crashed 09-22→09-25 (futures open 23,302) — crash-inflated premium crushing on expiry is a real post-crash short-vol effect; stale-mark contamination excluded for this session. Residual: one session validated (expired contracts leave the scrip master); probe historical depth or validate live sessions as they expire.

**Bottom line:** the sandbox has converged on: the condor-shaped book (never the spreads), expiry-gated (dte ≤ 1), dte features, EV ranking, **target = 100% of credit** — with marks validated and the composition mechanism explained. Production handoff with staged capital plan: `production_handoff.md`. Remaining pre-live gates: extend mark validation beyond one session, paper-trade 4 expiry weeks, fix the stale core lot-size/expiry schedule.

---
Recomputed from artifacts 2026-09-29: e001 `artifacts/labels_daily.csv` (max DD from rule-selected daily equity), e002 `artifacts/gating_sim.json` + `gating_variants.json` (self-checked against gating_sim.json), e003 `artifacts/policy_comparison.json`, e004 `artifacts/intraday_replay.csv`, e005 `artifacts/theta_condor.csv` (EOD exits verified identical to e001 leg-for-leg). ₹ levels are not comparable across lot eras (25→75→65); treat cross-era rupees as approximate.
