# Collated Experiment Results

All sims: ₹2,00,000 bankroll (config.TOTAL_CAPITAL), 1 lot era-correct (75→50→25→75→65, see `experiments/common/lots.py`), real Zerodha friction already netted, **no compounding**.
₹/yr = net ÷ window years; **Max DD%** = peak-to-trough of net equity ÷ ₹2,00,000. OOS windows stated per row; nothing annualized across windows.

## Verdicts (≤2 lines each)

- **e001 leak-free replay** — GOOD: honest measurement pipeline (4,245 leak-free labels) and the iron condor survives honesty (PF 4.1 all days, 4.7 rule-selected). BAD: naive t-1 momentum spreads bleed (bull PF 0.54, bear 0.86); the old engine's PF 22 is confirmed look-ahead fiction. *Learning: short-vol on flat days is the only daily edge that replicates.*

- **e002 regime models** — GOOD: ML day/archetype selector at the same trade count: +₹581k vs +₹130k, PF 1.20→2.24, max DD cut 57%, calibrated (Brier beats persistence on every archetype). BAD: directional spreads stay net-negative even under ML; LGBM barely beats logistic. *Learning: the value is allocation, and the condor edge is an expiry-day 0DTE effect that migrated Thu→Tue with NSE's change — use days-to-expiry, not weekday. (Labels carry e001's condor optimism — see e004.)*

- **e003 meta-labeling** — GOOD: filtering raises per-trade quality (avg ₹145→₹377 at 63% keep, net +₹214k > +₹130k). BAD: no per-trade skill (Brier 0.247 ≈ base 0.246) — it wins only by re-learning archetype base rates, and is dominated by e002 (₹645/trade at full count vs ₹557 at 29%). *Learning: day/archetype selection > trade filtering; revisit meta-labeling only with intraday features.*

- **e004 intraday replay** — GOOD: full-window real run done (1,410 sessions): spread books CONFIRMED net-negative under path exits (bull −₹314k, bear −₹147k — e001's spread verdict survives). BAD: condor column is a pricing artifact — fixed-IV BS strips out the theta decay that IS the condor's income (EOD-only days flip sign vs e001, corr −0.25). *Learning: fixed-IV greeks cannot price credit books; e005 exists to settle the condor properly.*

- **e005 theta-aware condor replay** — GOOD: with honest pricing the condor book survives intraday exits (+₹470k documented, PF 2.38, DD 3.3%; 1.4× SL fires on only 4.2% of days — e004's 25% was artifact), the target sweep picks **100% of credit** (+₹1.09M, PF 4.18, DD ₹5.5k — 50% was the worst operating point), and Kailash's decay-trailing exits also beat the 50% cap ~2× (though they trail the plain 100% target by ₹91k; real gamma spikes are understated by the model, so the trail is a defensible risk overlay). BAD: the **inverted-wall audit** shows valid-structure condors are only breakeven (+₹35k, PF 1.11) — ~97% of the frozen edge comes from days where a max-OI wall sat on the wrong side of spot (PF 75.9 on those days). *Learning: the "condor edge" is really a wall-breach directional trade rescued by 0DTE crush; validate those marks against intraday option quotes before believing them. And the edge does NOT scale with IV — high-IV non-expiry days earn almost nothing.*

## Results (net, era-correct lots)

| Policy | OOS window | Cap used | Net ₹ | ₹/yr | %/yr | Max DD ₹ | DD % |
|---|---|---|---:|---:|---:|---:|---:|
| e001 rule-selected (naive t-1 rule, full span) | 2021-01→2026-09 (5.7 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +152,346 | 26.7k | 13.4% | 67,526 | 33.8% |
| e002 baseline (same rule, OOS slice) | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +129,746 | 34.6k | 17.3% | 67,526 | 33.8% |
| **e002 ML-LGBM selector** | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | **+581,069** | **154.9k** | **77.5%** | **29,237** | **14.6%** |
| e002 ML-logistic + days-to-expiry (Add. 3) | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | **+793,906** | **211.7k** | **105.9%** | **18,746** | **9.4%** |
| e002 EV ranking (P × payoff, same n=919) | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +761,977 | 203.2k | 101.6% | 17,671 | 8.8% |
| e002 condor-only, ML days (n=306) | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +506,216 | 135.0k | 67.5% | 9,087 | 4.5% |
| e002 ML-logistic selector | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +518,247 | 138.2k | 69.1% | 21,907 | 11.0% |
| e003 meta-filter τ=0.40 (63% keep) | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +213,963 | 57.1k | 28.5% | 36,581 | 18.3% |
| e003 e002-style selector | 2023-01→2026-09 (3.75 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +578,639 | 154.3k | 77.2% | 25,799 | 12.9% |
| e004 path exits: bull spread (all days) | 2021-01→2026-09 (5.7 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | −313,851 | −55.1k | −27.5% | 314,588 | 157.3% |
| e004 path exits: bear spread (all days) | 2021-01→2026-09 (5.7 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | −146,502 | −25.7k | −12.9% | 160,690 | 80.3% |
| e004 path exits: condor ⚠ artifact | 2021-01→2026-09 (5.7 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | −547,744* | −96.1k | −48.0% | 547,810 | 273.9% |
| e005 condor, documented exits (SL + 50% target) | 2021-01→2026-09 (5.7 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +469,637 | 82.4k | 41.2% | 6,676 | 3.3% |
| e005 condor, target = 100% of credit (sweep optimum) | 2021-01→2026-09 (5.7 y) | ₹2.0L, 1 lot, ≤₹2.5k risk/trade | +1,086,580 | 190.6k | 95.3% | 5,504 | 2.8% |

Trade counts (matched within each experiment): e001 n=1,386; e002 baseline 920 / ML 919 (dte variant n=919); e003 n=897 (τ=0.40 keeps 567); e004 all-archetype daily replay, no selection; e005 n=1,321 simulated condor days.

\* e004 condor row is **invalid as PnL**: fixed-IV Black-Scholes repricing removes intraday theta decay, the condor's entire income — EOD-only days (no stop interference) flip sign vs e001 with −0.25 correlation. Spread rows are valid and confirm e001. The condor question needs theta-aware pricing; e002's condor edge stands until then.

Stop-stress superseded: e005 measured the real 1.4× SL rate at 4.2% of days (e004's 25% was artifact) — the SL is a non-event. Exit-aware re-gating (e002 Add. 4, clean column): under documented exits the selector's edge shrinks but survives (logistic+dte +₹368k, rule baseline −₹38k); with the target at 100% of credit every conclusion survives (EV-ranked +₹802k at 7.3% DD, condor-only ML +₹583k at 1.3% DD).

⚠ **Composition warning (e005 Add. 2):** on valid-structure days (put wall < open < call wall) the condor book is only **breakeven (PF 1.11)** — the frozen edge concentrates in inverted-wall days where the position is a directional wall-breach trade, not a premium-crush condor. Everything above inherits this; validate those days' marks against intraday option quotes (or re-define the trade as "sell the breached wall") before production.

**Expiry-centric convergence (e002 Add. 5 + e005 Add. 3, answering Kailash Nadh's review):** gating the ML condor book to dte ≤ 1 days **adds money while cutting trades 56% and DD to 1.9%** (+₹450k documented / +₹875k drop-target at 78% WR); IV regime is irrelevant on expiry days (every straddle-IV quintile profitable) and anti-correlated off-expiry (high-IV non-expiry days earn ~nothing) — so the right concentration is the expiry gate, not VIX timing. Decay-trailing exits (75–80% of credit after 14:00) beat the 50% cap ~2× but trail the plain 100% target by ~₹91k — keep as an optional gamma-dodge overlay.

**Mark validation (e005 `marks_validation.py` + `marks_validation_v2.py`): e005's marks are real — now across eras, not one session.** Dhan's Expired-Options API (`/v2/charts/rollingoption`, minute-level, depth to 2021-01-04 = the window's first day) recovers fixed-strike legs for expired contracts: 4/5 sampled sessions validated 2021→2026; closes match within timing noise everywhere covered; the one fully-covered session (2026-09-25) matches **to the paisa** and cross-checks v1's other-endpoint result. Caveats logged, not waved: edge-of-window legs differ a few points at the open slot (worst −21.1 on a ₹50 far wing — rolling-API stitching, flagged NOT exact); walls beyond ATM±10 (wide-wall days, e.g. 2022-06-10) are uncoverable by design. The "inverted" walls are prior-OI walls above a crashed spot — the crash-crush mechanism is price-consistent in every validated session.

**Breach-only book + slippage cliff (e005 Add. 5 + `slippage_cliff.py`, answering review round 2):** on 249 dte≤1 breached-wall days the 2-leg defined-risk spread makes +₹940,697 (98.8% WR, 2 STOPs, worst day −₹6,139 = defined max); the 4-leg condor on the same days earns more (+₹987,124, DD ₹657) but carries the gap-through tail. **Production pick: breach spread** (tail insurance worth ₹46k/5.7y), valid-structure days carry no trade. The 2-leg structure absorbs **23.1× modeled slippage (34.6 pts/leg)** before net breaks; the monthly DD cap binds earlier (~12×). EV-sizing tier (P>0.70 → 2 lots) not selective: 69% of trades clear the bar, per-trade PnL flat across buckets; tier vs flat-2 splits the objective (Calmar 151 vs 122) — flat-2 makes ₹135k more, the tier cuts DD 31%.

**Bottom line:** the sandbox has converged on a **fully mechanical breach-only book**: dte ≤ 1 + wall-breach test → sell the breached wall + 150-pt wing, SL 1.4×, target 100% of credit; no trade on valid-structure days; no ML required (98.8% WR leaves nothing for a selector). Marks validated on 5 sessions across both eras (2021→2026); slippage breakeven 34.6 pts/leg. Production handoff with decision box and staged capital plan: `production_handoff.md`. Remaining pre-live gates: sweep the remaining ~40 breach trades' open marks, paper-trade 4 expiry weeks. ~~Fix the stale core config~~ — **DONE**: `NIFTY_LOT_SIZE` 65 (2025-12-30 era) + Tuesday-expiry `WEEKDAY_SCHEDULES` are now in core, with lot-hardcoded test pins updated; 75 core + 36 experiment tests green.

---
Recomputed from artifacts 2026-09-30 (post lot-era correction: the flat-25 pre-Nov-2024 table was replaced with the verified 75/50/25/75/65 eras, so all 2021→Apr-2024 rupees were rescaled and every downstream artifact re-run): e001 `artifacts/labels_daily.csv` (max DD from rule-selected daily equity), e002 `artifacts/gating_sim.json` + `gating_variants.json` (self-checked against gating_sim.json), e003 `artifacts/policy_comparison.json`, e004 `artifacts/intraday_replay.csv`, e005 `artifacts/theta_condor.csv` (EOD exits verified identical to e001 leg-for-leg). ₹ levels are not comparable across lot eras (75→50→25→75→65); treat cross-era rupees as approximate.
