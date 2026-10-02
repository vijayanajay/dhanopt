# Quantitative Action Plan: Institutional-Grade Nifty Options Engine
**Architectural Blueprint & Execution Roadmap (Kailash Nadh Perspective)**  
*Target Environment:* Windows (pwsh) / Linux (bash) | Python 3.11+ | Single Source of Truth  
*Base Capital:* ₹2,00,000 (Account Bankroll) | Current Regulatory Era: **65 Lot Size** (NSE FAOP70616)  
*Status:* Active Master Plan (Replaces Discredited BRD v2.1 Directional Models) — **revised 2026-10-02**

> **Current honest position.** Expected monthly return of this entire program: **₹885**, every rupee of it collateral yield. **Alpha: ₹0.** One strategy candidate survives twenty experiments (e013, 0DTE pin harvest), and it has never been observed filling on live data. Every other rupee of PnL this repo has ever printed is now void or refuted. Full record: [RETROSPECTIVE.md](file:///d:/Code/dhanopt/RETROSPECTIVE.md).

---

## 1. Executive Summary & Foundational Reality

Every options strategy previously celebrated in this sandbox ([e001](file:///d:/Code/dhanopt/experiments/e001_leakfree_replay) to [e010](file:///d:/Code/dhanopt/experiments/e010_ml_gate)) collapsed under rigorous audit:
1. **The Day-t Look-Ahead Leak:** Strategies relied on max-OI walls computed from **15:30 EOD option chains**, an information leak of 6 hours. When tested against real opening OI ([e007](file:///d:/Code/dhanopt/experiments/e007_open_oi)), edge collapsed from +₹940,697 to **−₹309 (4 trades, PF 0.96)**.
2. **Directional Spreads Bleed:** Naive momentum continuation ([e004](file:///d:/Code/dhanopt/experiments/e004_intraday_replay)) lost −₹314k (bull) and −₹147k (bear) under realistic intraday paths.
3. **ML Without Monetary Edge:** ML models ([e010](file:///d:/Code/dhanopt/experiments/e010_ml_gate)) achieved real statistical discrimination (Brier 0.295 < 0.318), yet lost −₹121k because the underlying spread structure possessed negative expectancy after Zerodha friction and bid-ask drag.

And on 2026-10-02, a second, deeper conviction:
4. **The Contract-Identity Defect ([e011](file:///d:/Code/dhanopt/experiments/e011_vrp_delta_hedge) and everything built on it):** the VRP signal inverted the ATM straddle of the expiry nearest to *t-1* and then shifted by one row. The contract tradable on *t* is the expiry nearest to *t*. The published **+₹7,43,572.25 (Sharpe 2.85, PF 3.99)** is void: the inverted "IV" was a bisection artifact (mean 0.476, max 1.929, 35 sessions above 1.00), and the entry gate fired **2.55× more often on roll days** — the strategy was trading its own instrumentation error. **e011, e015, e016 and e017 are void.** The fix and the re-test are §Phase 2 below.

### What the "Top 1%" Do Differently
Institutional prop desks (Graviton, NK Securities, Quadeye, Tower, Jane Street) do not gamble on 5-minute directional momentum or static 1.4× stop-loss Iron Condors. They monetize three structural phenomena. **This repo has now measured all three, plus the one popular alternative, and the scoreboard is the point of this plan:**

| Structural phenomenon | Mechanism | This repo's verdict |
|---|---|---|
| **1. Variance Risk Premium** | IV systematically above RV over multi-year horizons (risk aversion, institutional hedging demand); harvested delta-neutral, not by stop-outs | **Tested twice. VOID then DEAD.** e011's result was a contract-identity artifact; e018 re-tested Option 1 on the corrected signal and lost **−₹61,306** (EV −₹435, PF 0.82, DD 48.4%). The premium is real (mean IV−RV 0.048); the *structure* cannot pay its own friction. |
| **2. Volatility Surface & Skew Asymmetry** | Monetize OTM-put overpricing (retail crashophobia) via ratio / relative-value structures | **KILLED.** e012: **−₹98,802, PF 0.13, 15 consecutive losses.** 4-leg friction turned +₹33/trade gross into −₹859/trade net. |
| **3. 0DTE Gamma Inventory & Pinning** | Market-maker delta hedging around structural strikes near expiry | **THE ONE SURVIVOR.** e013 pin harvest: **+₹4,14,721, PF 9.41, Max DD ₹11,940 (5.97%)** — the only book in twenty experiments inside the 8% drawdown ceiling. Unverified on live fills. |
| *(4. Cash-equity momentum — the popular alternative to options)* | Cross-sectional 12-1 momentum on free EOD data, "no friction decay" | **DEAD, twice, and honestly.** e019 falsified the premise (daily beat monthly 3.8×; costs ~3% of capital) and lost to its own equal-weight benchmark by **0.81 Sharpe**. e020 diluted to the top decile: 24.8% CAGR — and **+0.04 Sharpe** of excess. The return was beta. |

This action plan defines the exact steps to build, test, and validate what remains, using **only the data resident on disk or reachable from existing endpoints**, eliminating all guesswork and unstated assumptions.

### 1.1 The Void & Dead Ledger (2026-10-02)

The single most important table in this document. **No figure in the "claimed" column may be used in any model, sizing table, or pitch.**

| Exp. | Claimed | Audited | Status | One-line reason |
|---|---|---|---|---|
| e001–e007 | up to +₹9.41L | −₹232,823 / −₹140,520 / −₹309 | VOID (wall leak) | Walls = day-t EOD OI; the signal was the leak. |
| e010 | ML gate, −₹1.21L | −₹1.21L | DEAD (confirmed) | Real discrimination, negative-expectancy structure. |
| **e011** | **+₹7,43,572, Sharpe 2.85** | **0** | **VOID** | Contract identity: t's contract priced with t−1's expiry and tenor. |
| e012 | — | −₹98,802, PF 0.13 | DEAD | Skew ratio spread; friction exceeds edge. |
| e013 | +₹4,14,721, PF 9.41 | +₹4,14,721, PF 9.41 | **SURVIVING CANDIDATE** | Clean by construction (dte≤1 replays only); fills unverified. |
| e014 | Maker TCA | Maker −53%/−62% vs taker | CLOSED (negative) | E013 legs stand; E011 arms void with the book. |
| **e015** | +₹11,58,293, Sharpe 4.14 | **0** | **VOID** | Combined book inherits e011's void leg. |
| **e016** | Iron-fly wings, −₹1,56,941 | **0** | **VOID** | Wings test on the mispriced signal. |
| **e017** | Regime sizing, "needs ₹6.4L" | **0** | **VOID** | Risk budget computed on the void book. |
| **e018** | — | **−₹61,306, EV −₹435, PF 0.82, DD 48.4%** | **DEAD** (fix survives) | Correct contract identity, 0 violations — and no edge. |
| **e019** | — | monthly 3.1% / 0.34; benchmark 21.3% / 1.15 | **DEAD** | Excess Sharpe **−0.81**; friction-decay premise falsified. |
| **e020** | — | 24.8% CAGR / 1.19 Sharpe | **DEAD** | Excess Sharpe **+0.04** — the return is beta. |

**Carried forward:** the contract-identity engine, the hold-to-expiry mark path, the arithmetic-impossibility audit, the free cash price store, point-in-time liquidity, corporate-action back-adjustment, the anti-beta gate, the death-rate diagnostic, and the control-reproduces-predecessor pattern.

---

## 2. Inventory of Available Data Assets

All research in this roadmap must strictly consume data from the following verified partitions:

```
dhanopt/
├── data/
│   ├── historical/                     # EOD NSE FO Bhavcopy (Parquet partitions)
│   │   ├── year=2021/ ... year=2026/   # Contract-level: open, high, low, close, volume, oi, strike, expiry
│   ├── intraday/
│   │   └── interval=5/                 # 5-minute NIFTY 50 spot OHLCV (1,410+ sessions, 2021–2026)
│   ├── cash/                           # FREE NSE daily CASH bhavcopy (added 2026-10-02, e019)
│   │   └── <date>.parquet              # 1,420 sessions × 6,475 symbols, 215 MB, survivorship-safe
│   └── calibrated_params.json          # (Frozen; fail-closed calibration rules)
├── experiments/
│   ├── e008_wall_flip/artifacts/
│   │   ├── walls_576.tar.gz            # 576 sessions of 5-min option chains (OI, quotes) for dte <= 1
│   │   └── walls/<date>.json           # Minute-level chain dumps
│   ├── e018_vrp_weekly/                # Contract-identity-correct VRP engine + verdict (signal DEAD)
│   ├── e019_momentum/                  # Cash-momentum engine + dual-URL bhavcopy downloader (DEAD)
│   ├── e020_diluted_momentum/          # Diluted follow-up, reuses e019's engine (DEAD)
│   └── common/
│       ├── lots.py                     # Historical lot sizes: 75 -> 50 -> 25 -> 75 -> 65
│       └── leak_registry.py            # Information-set tracking (t-1 vs day-t) + e011 conviction
```

`data/cash/` is the newest and most reusable asset in the repo: free, complete, point-in-time, and enough for any cross-sectional equity study. Its downloader ([download_cash.py](file:///d:/Code/dhanopt/experiments/e019_momentum/download_cash.py)) is idempotent and probes both NSE archive URL schemes across the Aug-2024 cutover.

---

## 3. The Master Execution Phases

```mermaid
flowchart TD
    P1[Phase 1: Capital & Collateral Optimization — DONE] --> P2[Phase 2: True VRP — VOID e011]
    P2 --> P2B[Phase 2b: Contract-Correct VRP (e018) — DEAD]
    P1 --> P2C[Phase 2c: Cash Momentum (e019/e020) — DEAD]
    P2B --> P3[Phase 3: Volatility Skew & Ratio — KILLED e012]
    P3 --> P4[Phase 4: 0DTE Pin Dynamics — ONLY SURVIVOR e013]
    P4 --> P5[Phase 5: Execution Microstructure — GATE FAILED e014]
    P5 --> P6[Phase 6: Shadow Execution & Production Gatekeeper]
```

---

### Phase 1: Zero-Risk Baseline — Capital & Collateral Yield [COMPLETED ✅]
*Objective:* Guarantee an immediate, market-independent baseline yield on the ₹2,00,000 bankroll before taking any derivatives risk. Stop earning 3.0% in bank savings.
*Status:* **COMPLETED.** Engine implemented in [core/collateral.py](file:///d:/Code/dhanopt/core/collateral.py); verified in [tests/test_collateral.py](file:///d:/Code/dhanopt/tests/test_collateral.py).
*Why it matters more than it did:* with every strategy void or dead, this is the **only certified-positive flow in the program** — ~₹10.6k/yr gross at Oct-2026 rates (₹885/mo). The user action below is the highest-expected-value item outstanding in this plan.

#### 1.1 Capital Allocation & Haircut Math
Under SEBI collateral circulars, Liquid and Overnight mutual funds pledged via depository (CDSL/NSDL) count toward the **50% cash-equivalent margin** requirement with a standardized broker haircut (~10%).

| Capital Component | Allocation | Broker Haircut | Usable Collateral Margin | SEBI Classification | Gross Annual Yield |
|---|---:|---:|---:|---|---:|
| **Overnight Mutual Fund (Growth)** | ₹1,80,000 (90%) | 10% (₹18,000) | ₹1,62,000 | Cash-Equivalent (100%) | ₹9,540 (~5.3%) |
| **Cash Buffer (Savings/Sweeps)** | ₹20,000 (10%) | 0% (₹0) | ₹20,000 | Pure Cash (100%) | ₹600 (~3.0%) |
| **Total Bankroll Account** | **₹2,00,000** | **₹18,000** | **₹1,82,000** (91.0% efficiency) | **100% Cash-Equivalent** | **₹10,140** (~5.07% blended) |

#### 1.2 Net Yield Accounting Across Tax Slabs (Post-Apr 2023 Finance Act)
Under post-2023 debt mutual fund taxation (taxed at slab rate, indexation eliminated):
* **Gross Yield Generated:** ₹10,140 / year (~₹845.00/month blended across fund units + cash sweeps).
* **Baseline Bank Savings (3.0% on ₹2,00,000):** ₹6,000 gross / ₹4,200 net (30% slab).
* **30% Tax Bracket (Top Slab):** Net **₹7,098 / year** (~₹591.50/month) $\implies$ **+₹2,898/year net risk-free alpha** over bank savings.
* **20% Tax Bracket:** Net **₹8,112 / year** (~₹676.00/month) $\implies$ **+₹3,312/year net risk-free alpha** over bank savings.
* **5% Tax Bracket:** Net **₹9,633 / year** (~₹802.75/month) $\implies$ **+₹3,933/year net risk-free alpha** over bank savings.
* **Gross Alpha Spread vs Bank Savings:** **+₹4,140/year** (+2.07% blended spread) guaranteed without market risk.

*Rate caveat:* written at repo 6.0–6.5%. The current Oct-2026 mark is **~₹10.6k/yr gross, ~₹7.4–10k post-tax by bracket** — see [COLLATERAL_PLAYBOOK.md](file:///d:/Code/dhanopt/COLLATERAL_PLAYBOOK.md) for the full mechanics.

#### 1.3 Execution Headroom Verification (1-Lot Nifty ATM Straddle, Era 65)
* **Estimated Required Margin for 1 Short Straddle:** **₹1,24,852** (evaluated at Nifty Spot 24,500, Era Lot 65, 7.84% margin rate).
* **Available Usable Margin:** **₹1,82,000** (₹1,62,000 pledged collateral + ₹20,000 cash buffer).
* **Headroom / Free Buffer:** **₹57,148** (45.8% surplus above required margin).
* **SEBI 50:50 Compliance:** Required cash-equivalent = ₹62,426; Available = ₹1,82,000 $\implies$ **100% compliant** (overnight fund pledged units count 100% toward cash component).

#### 1.4 Recommended Fund Selection
Select any low-cost, institutional direct growth overnight fund (AUM > ₹10,000 Cr, TER < 0.10%, zero exit load):
1. *SBI Overnight Fund Direct-Growth* (ISIN: INF200K01UT0)
2. *HDFC Overnight Fund Direct-Growth* (ISIN: INF179K01VE4)
3. *ICICI Prudential Overnight Fund Direct-Growth* (ISIN: INF109K01Z74)

#### 1.5 Execution Checklist & Verification
- [x] Implement programmatic collateral allocation & margin validation ([core/collateral.py](file:///d:/Code/dhanopt/core/collateral.py)).
- [x] Unit test margin verification, straddle estimation & SEBI cash-equivalent rules ([tests/test_collateral.py](file:///d:/Code/dhanopt/tests/test_collateral.py) — 6 passing tests in 0.001s).
- [x] Executable CLI dashboard (`uv run python -m core.collateral` or `uv run python core/collateral.py`).
- [x] Fail-closed capital gate wired into the options replay engine ([experiments/e011_vrp_delta_hedge/replay_vrp.py](file:///d:/Code/dhanopt/experiments/e011_vrp_delta_hedge/replay_vrp.py)). *The engine is void; the margin gate it carries is not, and is re-usable by any future replay.*
- [ ] **User Action (highest priority in this plan):** Transfer idle funds to broker account & purchase direct growth overnight fund units.
- [ ] **User Action:** Initiate broker margin pledge flow via depository (CDSL/NSDL).
- [x] Reference complete operational manual in [COLLATERAL_PLAYBOOK.md](file:///d:/Code/dhanopt/COLLATERAL_PLAYBOOK.md).

---

### Phase 2: True Variance Risk Premium (VRP) & Dynamic Delta-Hedging [VOID ❌ → RE-TESTED & DEAD ❌]
*Objective:* Harvest the structural spread between Implied Volatility ($IV$) and Realized Volatility ($RV$) without taking directional market risk.
*Status:* **The e011 result is VOID. The hypothesis was then re-tested honestly in [e018](file:///d:/Code/dhanopt/experiments/e018_vrp_weekly/) on the corrected signal and is DEAD. This phase produced the most valuable artifact in the repo — the contract-identity fix — and no tradeable edge.**

#### 2.1 The Conviction (2026-10-02) — what e011 actually measured
`extract_eod_straddle` takes the expiry nearest to **t-1**, inverts its ATM straddle, and `compute_volatility_dataset` shifts by one row. The shift is correct; the *instrument* is not. The contract tradable on **t** is the expiry nearest to **t**. When t-1 was an expiry day they differ, and the pinned straddle was inverted with a tenor roughly one-fifth of its real life. Measured on all 293 e011 signal sessions:

| | e011 (void) | contract-identity-correct |
|---|---:|---:|
| mean signal IV | 0.476 | **0.163** |
| max signal IV | 1.929 | **0.473** |
| sessions IV > 1.00 | 35 | **0** |
| sessions IV ≥ 0.60 | 68 | **0** |
| mean tenor credited | 0.95 days | **4.71 days** |
| roll-day enrichment in the signal | **2.55×** | **1.00×** (none) |

**The gate selected on the bug.** Roll sessions are 21% of trading days but 54% of e011's signals. The book was not trading a volatility regime; it was trading the days its own inversion broke. Every sensitivity table in the old §2.4–2.8 (volatility window sweep, delta-rebalance sweep, slippage cliff to 5×) is a sweep of a bug, and all of it is struck from the record.

**Propagation:** e015 (book combination), e016 (iron-fly wings) and e017 (regime sizing + risk budget) each froze e011's artifacts and reasoned carefully on top of them. All three are void. The conviction is written into [experiments/common/leak_registry.py](file:///d:/Code/dhanopt/experiments/common/leak_registry.py) so it cannot be inherited a fourth time. **e013 is clean** — it replays only genuine `dte ≤ 1` sessions, so contract identity holds by construction.

#### 2.2 The Re-Test — E018, Contract-Identity VRP [KILLED ❌]
*Pre-registered* at [experiments/e018_vrp_weekly/PREREG.md](file:///d:/Code/dhanopt/experiments/e018_vrp_weekly/PREREG.md), frozen before any code: a **weekly 3–7 DTE wide defined-risk condor held to expiry**, built off the t-1 bhavcopy store, with all marks taken from real bhavcopy closes. This is Option 1 tested on its own terms.

| # | Gate | Bar | Observed | Status |
|---|---|---|---|---|
| 1 | Capacity | ≥ 30 trades | **141** (24.7/yr) | ✅ PASS |
| 2 | Edge | EV ≥ +₹400 and PF ≥ 1.5 | **EV −₹435, PF 0.82** | ❌ FAIL |
| 3 | Drawdown | ≤ 15% of ₹2L (₹30,000) | **−₹96,835 (48.4%)** | ❌ FAIL |
| 4 | Contract identity | 0 mismatches | **0 across 141 trades** | ✅ PASS |
| 5 | Friction resilience | net > 0 at 2.0× slippage | **−₹92,306; breakeven 0.51 pts/leg** | ❌ FAIL |
| 6 | No roundness | WR ≤ 85% | **63.8%** | ✅ PASS |

```
Total net PnL   -61,306      Sharpe (-0.38)     Avg friction  ₹861/trade
Win rate         63.8%       Profit factor 0.82 Max DD  -96,835 (48.4%)
Wins   n=90  mean +3,022   |   Losses n=51  mean -6,535
```

**Mechanism (measured): the credit is smaller than the transaction.** Mean entry credit is **75 pts** on a mean lot of 55 — about ₹4,100 gross — against **₹861/trade** of friction (₹160 brokerage + STT + exchange + GST + 8 × 1.5 pts slippage, ₹660 of it slippage alone). The book needs a **0.51-pt half-spread just to break even**; real NSE weekly spreads on 3–7 DTE wings run several points wide. This is the same floor e017 hit from the other side — ₹83,166 of flat per-order fees that no position size could cross — found again from a *shorter* holding period. Wide wings capped the tail but truncated recovery (51 losers average −₹6,535 against 90 winners at +₹3,022), the same trade-off e016 documented.

**The verdict is honest in both directions:** the contract-identity bug is fixed, and the edge does not survive the fix. The corrected signal shows a real, stable IV−RV spread (mean 0.048, p80 hurdle 0.075) — it dies as a *structure*, not as a phenomenon. A future attempt needs a higher credit-to-fee ratio: longer holds (2–4 weeks, where credit is a larger multiple of the same flat fees), or index/futures vol products with per-contract rather than per-leg costs.

**Two bugs the sanity bars caught mid-run** (both documented in the e018 README, both now pinned by tests):
* **Stale expiry-day marks — ₹104,000 of phantom loss.** The bhavcopy `close` on expiry day is a *last-trade* price, measured at 0.30 on options that expire at 0.00, and on 34 of 141 trades it implied an exit debit larger than a condor's arithmetic maximum. At expiry, time value is exactly zero, so the mark is **intrinsic against the futures close**. Marking correctly moved the book −₹165,194 → −₹61,306. Net changed; verdict did not. `test_exit_marks_respect_condor_arithmetic_max` now fails if this returns.
* **Contract identity in the replay** — the mirror of e011's bug. `target_expiry` is deliberately *not* shifted, because which expiry is front on day t is a public-calendar fact knowable at t-1. `_identity_ok` re-derives it from the trade date's own partition on every trade, and that is gate 4.

#### 2.3 Phase 2 Deliverables — what survives, what dies
* [x] ~~Published e011 result (+₹7,43,572)~~ — **VOID.** The artifacts remain on disk as the exhibit for the conviction; no number in them may be used.
* [x] ~~Volatility estimator / BS inversion engine~~ — **superseded.** The correct engine is [e018 volatility_fixed.py](file:///d:/Code/dhanopt/experiments/e018_vrp_weekly/volatility_fixed.py): front expiry resolved from the trade date's own partition, straddle read from t-1, clean IV distribution, roll-day enrichment eliminated, 1,410 sessions in ~3 minutes. **Keep this file; discard the signal it feeds.**
* [x] ~~Delta-hedging replay with t+1 fills~~ — machinery valid, object void. Same disposition as the collateral gate in §1.5.
* [x] ~~Sensitivity matrix / slippage cliff~~ — **struck.** These are sensitivity sweeps of a bug; a sensitivity table on an unvalidated signal is a table of how the bug responds to knobs.
* [x] **Contract-identity fix + 17 tests** ([test_e018.py](file:///d:/Code/dhanopt/experiments/e018_vrp_weekly/test_e018.py)) — roll rejection, front-expiry selection, per-trade re-derivation, IV plausibility, t-1 no-lookahead, condor arithmetic bounds, era-correct lots, fail-closed legs, DTE band. **This is the deliverable.**
* [x] **Hold-to-expiry mark path** — entry at day-t EOD close, settle at the expiry date's EOD close, marked on real bhavcopy prices with no Black-Scholes reconstruction anywhere. No PnL depends on a model's opinion of a price.
* [x] **Arithmetic-impossibility audit** — a condor's maximum loss is closed-form; any backtest violating it has a pricing bug. Cheap, general, should be a house test (now §5.9).
* [x] Registered in [experiments/common/leak_registry.py](file:///d:/Code/dhanopt/experiments/common/leak_registry.py) with the e011 conviction and both e018 rows.

---

### Phase 2c: Cash-Equity Momentum on Free EOD Data [DEAD ❌ — E019 & E020]
*Objective:* Replace options PnL with cross-sectional 12-1 momentum on free NSE daily cash data — the standard "friction doesn't bite in cash equities" argument.
*Status:* **Both cells dead.** The engine is exemplary and carries forward; the strategy is refuted twice, and the premise behind it is measurably false.
*Note:* this is not a numbered roadmap phase — it is the branch taken when the brainstorm asked what else the free data on disk could do. It is recorded here because it is the only test of the fourth hypothesis in §1.

#### 2c.1 E019 — the premise is false
*Pre-registered* at [PREREG.md](file:///d:/Code/dhanopt/experiments/e019_momentum/PREREG.md) before a single download.

| Leg | Net CAGR | Sharpe | Max DD | Costs paid |
|---|---:|---:|---:|---:|
| Cross-sectional, monthly | 3.14% | 0.34 | −55.4% | ₹28,812 |
| Cross-sectional, daily | 12.01% | 0.87 | −51.7% | ₹148,029 |
| **Equal-weight benchmark (no signal)** | **21.29%** | **1.15** | **−24.2%** | — |
| NIFTYBEES time-series | 7.56% | 0.63 | −16.9% | ₹6,261 |

**Option 2's premise is falsified by its own run.** "Free EOD data has genuine predictive power *without friction decay*" — the friction half is false: **daily rebalancing beat monthly by 3.8×**, the exact opposite of the prediction, and monthly costs were ₹28,812 over 4.5 years on a ₹2L book ≈ **3% of capital**. They could not bind. The reason to leave options for cash equities is *not* that friction decays the edge.

And momentum does not survive being traded: excess Sharpe versus the same-universe equal-weight portfolio was **−0.81**. Gate 6 (beat the benchmark by ≥ 0.2 Sharpe) is the primary gate and it exists because a long-only book in a bull market earns 21% CAGR from beta alone.

Two measured mechanisms, both worth keeping:
* **Momentum is real in the cross-section.** Pooled over 71,080 name-periods, rank vs next-21-day return: bottom decile +0.58%, top decile **+3.24%** — a genuine +2.66% spread.
* **…and the winners die.** Top-20 holdings stop trading within 21 days **3.4× more often** than the universe (1.51% vs 0.44%). Any study computing forward returns only over names still printing drops exactly those losers. That is why the raw decile spread looks so good and the book does not.

*Honest gate failure:* the pre-declared ≥60 monthly rebalances bar was missed at 54, because 12-1 momentum needs 252+21 sessions of warm-up. **The bar was not moved** — e020 later set its own bar from the measured warm-up and disclosed it.

#### 2c.2 E020 — dilution fixes everything except alpha
*Pre-registered* at [PREREG.md](file:///d:/Code/dhanopt/experiments/e020_diluted_momentum/PREREG.md); long top **decile** (~135 names) instead of top-20, same store, same point-in-time universe, same t-1 fill rule, same cost model.

| Configuration | CAGR | Sharpe | Max DD | Excess Sharpe vs EW |
|---|---:|---:|---:|---:|
| Top-20 (E019 control) | 3.1% | 0.34 | −55.4% | **−0.81** |
| **Top decile, ~135 names (E020)** | **24.8%** | **1.19** | **−32.7%** | **+0.04** |
| Equal-weight benchmark | 21.3% | 1.15 | −24.2% | — |
| Long-short *diagnostic* (net, ungated) | 3.7% | 0.58 | −14.0% | — |

**Verdict: FAIL on 2 of 7 gates — the two that mattered.** Gates 1–4 and 7 pass: 54 rebalances, 135 names on 100% of days, CAGR 24.8%, Sharpe 1.19, DD −32.7%, positive at 2× cost. Then:

* **Gate 5 (anti-beta) fails at +0.04 Sharpe of excess.** The return is beta. Dilution moved net CAGR 3.1% → 24.8% and cut the drawdown 23 points, and **not one point of it was skill** — a reader shown only the CAGR column would call this a success. It is not one.
* **Gate 6 (death rate) fails at 1.87×** (0.81% vs 0.43% universe) against a 1.5× bar. Dilution halved the excess death rate (3.4× → 1.87×) but momentum still selects fragile names. This is a property of the *signal*, not the portfolio; no weighting scheme fixes it.

**The control is the most important line in the table.** Re-running e019's exact configuration inside e020 reproduced **excess Sharpe −0.81 to the decimal**. An engine that cannot reproduce its predecessor is not measuring momentum; this one can, so the rest of the numbers deserve trust. This is now §5.10.

*The one live cell:* the pre-declared long-top-decile / short-bottom-decile diagnostic earns **3.7% net, Sharpe 0.58** — a real momentum spread, and not a book a retail account can hold at scale without a borrow arrangement this repo cannot model honestly. Further long-only work on this cross-section is spent: the beta decomposition says it.

#### 2c.3 Deliverables that carry forward
- [x] **Free cash price store** — 1,420 sessions × 6,475 symbols, 215 MB, idempotent dual-URL downloader, survivorship-safe by construction (union of all trading symbols; no index-membership list applied backwards). Reusable for any cross-sectional equity study.
- [x] **Corporate-action back-adjustment** — 453 events across 397 symbols, back-adjusted at clean 1:1/1:2/1:3/1:4 ratios. RELIANCE's 1:1 bonus reads as a **−49.8% crash** in raw bhavcopy (a momentum screen drops the name exactly when it might qualify — a bias *against* the large caps that lead the factor) and becomes +0.98%.
- [x] **Point-in-time liquidity** — trailing-252 median turnover ending t-1, computed once instead of 1,100 times.
- [x] **The anti-beta gate** — the only reason either experiment produced a decision instead of a celebration. Now §5.8.
- [x] **The death-rate diagnostic** — a property of the signal that no standard backtest reports. Now §5.9.
- [x] **Negative result, reusable:** Indian cash-equity momentum turnover costs do *not* bind at 21-session rebalance.

---

### Phase 3: Volatility Skew & Asymmetric Ratio Architecture [COMPLETED / KILLED ❌]
*Objective:* Monetize the structural overpricing of OTM puts (crashophobia) through self-financing ratio spreads rather than directional buying/selling.
*Status:* **COMPLETED & KILLED.** Engine built in [experiments/e012_skew_ratio/](file:///d:/Code/dhanopt/experiments/e012_skew_ratio/).
*Results:* **Net −₹98,801.92**, **Profit Factor 0.13**, **Win Rate 14.78%**, **15 consecutive losses** across 115 trades (2021–2026).
*Note:* these labels are **wall-free**, so neither leak touches this verdict. It stands as measured.
*Kill Criteria Status:*
  * Kill 1 (Profit Factor $\ge 1.80$): **DECISIVE FAIL (0.13)**.
  * Kill 2 (Win Rate $\ge 70\%$, $\le 3$ consec losses): **DECISIVE FAIL (14.8%, 15 consec losses)**.
  * Kill 3 (Capacity $\ge 25$/yr): **FAIL (20.2 trades/yr)**.
*Mechanism Post-Mortem:*
  1. Selling two $15\Delta$ puts does not self-finance one $35\Delta$ put + wing; entry averaged a net debit of **45.9 index points**.
  2. Rapid intraday theta decay on the $35\Delta$ leg destroyed position value on non-crash days (88.7% of sessions).
  3. 4-leg friction (₹892/trade) turned +₹33/trade gross into a −₹859/trade net bleed. Strategy definitively killed.

#### 3.1 Quantitative Hypothesis
Retail market participants persistently overpay for deep Out-Of-The-Money (OTM) Put protection on Nifty index options. The Put-Call Implied Volatility skew is consistently positive:
$$\text{Skew}_{25\Delta} = \frac{\sigma_{\text{IV}}(25\Delta \text{ PE}) - \sigma_{\text{IV}}(25\Delta \text{ CE})}{\sigma_{\text{IV}}(\text{ATM})}$$
When $\text{Skew}_{25\Delta}$ expands to historical extremes (90th percentile), selling the overpriced OTM put to fund an ATM/NTM long put or strangle creates a positive-expectancy relative value book.

#### 3.2 Implementation & Testing Protocol
Build `experiments/e012_skew_ratio/`:
1. **Dataset:** Contract-level Bhavcopy partitions in `data/historical/`.
2. **Strike Curve Parameterization:**
   For each trading session $t-1$, fit IV across $10\Delta, 25\Delta, 50\Delta (\text{ATM}), 75\Delta, 90\Delta$.
3. **Strategy Structure (1×2 Put Ratio Spread):**
   * Buy 1 lot of $35\Delta$ Put.
   * Sell 2 lots of $15\Delta$ Put.
   * Net position: Built for zero net debit or a small net credit.
   * Tail Risk Protection: Hard cap margin risk with 1 lot of far OTM $2\Delta$ wing (defined-risk broken-wing fly).
4. **Exit Dynamics:**
   * Close at 50% max profit.
   * Hard stop at $1.5\times$ initial credit or spot breaching the short strike.

#### 3.3 Pre-Registered Kill Criteria for Phase 3
| Metric | Threshold Bar | Observed | Status |
|---|---|---:|---:|
| Profit Factor | $PF \ge 1.80$ over 2021–2026 walk-forward | **0.13** | ❌ **FAIL** |
| Win Rate | $\ge 70\%$ on valid signal sessions ($\le 3$ consec losses) | **14.8% (15 max losses)** | ❌ **FAIL** |
| Total Trades | $\ge 25$ occurrences per year | **20.2 / yr** | ❌ **FAIL** |

---

### Phase 4: 0DTE Expiry Microstructure & Pin Dynamics [COMPLETED / VALIDATED CANDIDATE 🎯 — THE ONLY SURVIVOR]
*Objective:* Exploit market maker delta inventory and structural hedging behavior during 0DTE sessions (Tuesday/Thursday).
*Status:* **COMPLETED and the only strategy claim in this plan that survives both convictions.** Engine built in [experiments/e013_0dte_pin/](file:///d:/Code/dhanopt/experiments/e013_0dte_pin/).
*Why it survives:* the replay selects only genuine `dte ≤ 1` sessions, so the contract being traded and the contract being priced are the same object by construction. It never depended on a wall convention (the original leak) and never on a shifted tenor (the second). Its walls are informational context for a *regime* classification, not the trade trigger.
*Results:*
  * **Pin Harvest (Iron Butterfly, $\text{Ratio} \le 0.65$):** **Net +₹4,14,721.03**, **Net EV +₹2,148.81 / trade**, **Win Rate 83.94%**, **Profit Factor 9.41**, **Max DD ₹11,940 (5.97% < 8.0%)**, **Sharpe 5.52** across 193 sessions (33.9 trades/yr).
  * **Gamma Breakout ($\text{Ratio} \ge 1.20$):** **Net −₹46,269.29**, **Net EV −₹564.26**, **Profit Factor 0.58**, **Win Rate 31.7%** (direction dead).
*Kill Criteria Status:*
  * Kill 1 (Net EV $\ge +₹600$): **PASS (Pin Iron Fly: +₹2,148.81 / trade)**.
  * Kill 2 (Fill Feasibility $\ge 80\%$): **DATA CEILING on e008 artifacts (0.0% observable due to ATM omission in `fetch_walls.py`)** $\implies$ Validates that live execution requires [e009](file:///d:/Code/dhanopt/experiments/e009_wall_capture) full-chain live capture.
*Standing caveats (do not drop these):* 83.94% WR is at the roundness bar — §5.4 applies; and **no live fill has ever been observed for this book.** It is a candidate, not a deployment.

#### 4.1 Market Microstructure Reality
On weekly expiry days, open interest creates massive gamma sensitivity for option sellers.
* **The Pinning Regime:** If morning spot movement is within the ATM straddle breakeven ($S_0 \pm \text{Straddle}_0$), option sellers defend strikes; gamma hedging drives mean reversion toward the max-OI pin strike.
* **The Gamma Squeeze Regime:** If spot breaks past the opening straddle range with expanding volume after 13:00 IST, market makers are forced to aggressively hedge delta in the direction of the break, causing explosive one-way moves.

#### 4.2 Replay Architecture Using E008 Chain Data
Consume `experiments/e008_wall_flip/artifacts/walls_576.tar.gz` and the 5-minute spot store:
1. **Session Classification at 12:30 IST:**
   * Calculate cumulative realized range from 09:15 to 12:30 vs Opening Straddle Premium:
     $$\text{Expansion Ratio} = \frac{\text{High}_{12:30} - \text{Low}_{12:30}}{\text{ATM Straddle Premium at 09:20}}$$
2. **Strategy A (Pin Harvest - Iron Butterfly):**
   * If $\text{Expansion Ratio} \le 0.65$: Enter Iron Fly at ATM strike at 12:35 IST Open (strictly Bar 40).
   * Hold until 15:15 IST (capturing the afternoon theta collapse).
3. **Strategy B (Gamma Breakout Follower):**
   * If $\text{Expansion Ratio} \ge 1.20$: Do NOT sell credit. Buy directional debit spread in the direction of the breakout.
4. **Information Set Rule:** All signals evaluated on bars $\le 39$ (12:30 IST), execution strictly at bar 40 Open (12:35 IST).

#### 4.3 Pre-Registered Kill Criteria for Phase 4
| Metric | Threshold Bar | Observed | Status |
|---|---|---:|---:|
| Post-12:30 Expectancy (Pin Fly) | Net EV $\ge +₹600$ per lot | **+₹2,148.81 / trade** | ✅ **PASS (Strong)** |
| Post-12:30 Expectancy (Breakout) | Net EV $\ge +₹600$ per lot | **−₹564.26 / trade** | ❌ **FAIL (Killed)** |
| Fill Feasibility (in e008 data) | $\ge 80\%$ legs observable | **0.0% (ATM omitted)** | ⚠ **REQUIRES E009 LIVE DATA** |

---

### Phase 5: Execution Microstructure & Limit Order TCA [COMPLETED / GATE FAILED ❌]
*Objective:* Eliminate the "Taker Penalty" that systematically destroys retail multi-leg options trading.
*Status:* **COMPLETED & GATE FAILED.** Engine built in [core/execution/maker.py](file:///d:/Code/dhanopt/core/execution/maker.py); TCA run in [experiments/e014_maker_tca/](file:///d:/Code/dhanopt/experiments/e014_maker_tca/).
*Results:* Passive-only (maker, all-or-none) execution **fails Gates 2 & 3 on the surviving book**: E013 Pin Fly maker EV +₹1,018/trade vs +₹2,149 taker (aggregate ratio **27.3% < 60%**). Basket fill-rate gate passed (57.5% ≥ 50%). **Decision: taker entry retained; passive execution relegated to exits and Phase 6 measurement.**
*Scope correction (2026-10-02):* the e011 arm of this TCA (+₹2,538/trade taker, +₹959 maker, 174/293 filled) is **void with its book** and is struck from the record. The verdict below rests on the e013 arm, where both books agreed in direction anyway.

#### 5.1 The Friction Trap (Why Retail Loses 25%+ to Intermediaries)
In a 4-leg Iron Condor or 2-leg spread:
* Crossing the spread (market order / aggressive taker): Paying $\approx 1.5$ to $2.0$ points per leg $\implies 6.0$ to $8.0$ index points ($₹390$ to $₹520$ per lot) lost on entry and exit combined.
* Taxes (STT 0.1% on sell side post-Oct-2024, GST 18%, Exchange fees): $\approx ₹120$ per lot.
* Total initial deficit: **$\approx ₹500$ to ₹640$ per lot before the trade even moves.**

#### 5.2 The Maker Execution Engine
Build `core/execution/maker.py`:
1. **Passive Limit Placement:**
   * Calculate Mid-Price: $\text{Price}_{\text{mid}} = \frac{\text{Bid} + \text{Ask}}{2}$.
   * Place limit orders at $\text{Bid} + 1\ \text{tick}$ (for buy) or $\text{Ask} - 1\ \text{tick}$ (for sell).
2. **Queue & Fill Simulator (for Backtesting):**
   * An order is assumed filled *only* if subsequent trade prints occur at prices strictly through the limit price, OR if total volume traded at that price exceeds $3\times$ our order size.
3. **Adverse Selection Penalty:**
   * Any fill that occurs immediately before an adverse 5-minute move of $> 0.20\%$ is logged as adverse selection and penalized in the backtest.

#### 5.3 E014 TCA Results: Maker vs Taker (Pre-Registered, [PREREG](file:///d:/Code/dhanopt/experiments/e014_maker_tca/PREREG.md))
The surviving book was re-replayed under identical timing in three arms — TAKER (reproduces published e013 accounting exactly, verified per-session), MAKER (all-or-none passive basket, NO TRADE if any leg misses its 30-min entry window), HYBRID (passive entry, taker chase after window). Option mids are Black-Scholes on the 5-min spot store with session IV (half-spread 1.5 pts = the frozen taker slippage; no volume tape on options, so fills require strictly-through prints — pessimistic on fill probability).

| Arm | E013 Pin Fly Net EV | E013 Total Net | E013 Fill Rate |
|---|---:|---:|---:|
| **TAKER** | **+₹2,148.81** | **+₹4,14,721** | 193/193 |
| **MAKER (AON)** | +₹1,018.29 | +₹1,13,031 (**27.3%** of taker) | 111/193 |
| **HYBRID** | +₹666.58 | +₹1,28,651 | 193/193 |

~~E011 VRP arm: taker +₹2,537.79 / +₹7,43,572; maker +₹959.12 / +₹1,66,887 (22.4%).~~ **VOID — struck with the e011 conviction.**

*Decomposition of the −₹1,130/trade maker collapse (E013):*
1. **Session-level fill selection is NOT the cause:** taker EV on exactly the maker-filled sessions is +₹2,161 vs +₹2,149 overall (+₹12 delta). Calm days fill more often; the surviving subset is not worse.
2. **Adverse selection is real but secondary:** 71.8% of passive fills were flagged (move ≥ 0.20% against the leg within 5 min) and re-priced at the taker alternative — the queue gives back ~₹2.33L of the ~₹4.0L gross improvement it captures across both books.
3. **Missed sessions are the killer:** 82 of 193 Pin Fly sessions never traded (~₹1.76L forgone taker EV). These are theta-harvesting books: their edge lives on fast days, and on fast days option mids sweep through passive limits instantly (flagged adverse) or never touch them.

*Verdict:* The option premium moves more than the full modeled spread within one 5-minute bar far too often for a passive bid/ask∓1 tick to get paid to wait. **This is a spread-crossing strategy by construction.** The only defensible passive leg is the **exit** (54.7% of exit legs filled passively where urgency is lowest); entry remains taker. Useful corollary for the surviving book: e013's frozen 1.5 pts/leg taker slippage assumption is *not* optimistic — the maker alternative is strictly worse, so its net-PnL figure stands as an upper bound under execution risk, not a fiction.

#### 5.4 Phase 5 Execution Checklist & Code Deliverables
- [x] Passive limit placement, bar-based queue & fill simulator (strict-through OR touch + 3× volume), adverse-selection penalty ([core/execution/maker.py](file:///d:/Code/dhanopt/core/execution/maker.py); 12 unit tests in [tests/test_maker_execution.py](file:///d:/Code/dhanopt/tests/test_maker_execution.py)).
- [x] Non-invasive passive-execution seam in the replay engine (`entry_bar`, `strike_override`, `entry_fill_*`, `exit_fill_*` on `simulate_session`). *The e011 engine it was wired into is void; the seam itself is engine-agnostic and is what Phase 6 needs.*
- [x] Pre-registered three-gate protocol frozen before the run, with two pre-run mechanical amendments documented (put-leg sign correctness in the adverse flag; reprice pinned to taker-at-posting) ([experiments/e014_maker_tca/PREREG.md](file:///d:/Code/dhanopt/experiments/e014_maker_tca/PREREG.md)).
- [x] Three-arm TCA replay with per-leg fill logs ([experiments/e014_maker_tca/tca.py](file:///d:/Code/dhanopt/experiments/e014_maker_tca/tca.py)); artifacts: `trades.csv`, `maker_fills.csv` (3,467 leg fills), `metrics.json`.
- [x] Fidelity integration test: the TAKER arm reproduces published e013 per-session PnL exactly.
- [x] Findings & post-mortem ([experiments/e014_maker_tca/README.md](file:///d:/Code/dhanopt/experiments/e014_maker_tca/README.md)).
- [ ] Phase 6 scope update: shadow-test the **hybrid exit-only** maker configuration (taker entry, passive exit) — the only maker variant that survived analysis.

#### 5.5 Post-Phase-5 Analyses — STATUS: VOID

**A. E015 book composition (E011 × E013) — VOID ❌** ([experiments/e015_book_combo/](file:///d:/Code/dhanopt/experiments/e015_book_combo/))
One leg of this book is void, so the combined book is void. Struck in full: the +₹11,58,293, the 4.14 Sharpe, the 16.0% joint DD, the EV per trade-day. **One number survives as a capital fact, not a PnL claim:** under a conservative naked-straddle margin bound, 10 of 44 historical overlap days would have breached the ₹1,82,000 usable margin on a combined ₹2L account. *If a single book is ever deployed, that arithmetic does not apply; if two are, it is a hard constraint to check before stacking.*

**B. Spread-width sensitivity — half void.**
The reconstruction method survives; the e011 column does not.
* Breakeven per-leg spread: **e011 13.0 pts (VOID)**; **e013 10.7 pts (stands)** — the 1.5-pt assumption sits deep inside the safe zone.
* At 3.0 pts/leg (2× baseline), e013 remains **+₹3.47L** (EV +₹1,799, PF 6.75, Sharpe 4.68), max DD under the ₹16k ceiling until ~4.9 pts/leg.
* ~~e011 at 3.0 pts/leg: +₹6.47L, Sharpe 2.49~~ — **struck.**

**C. E016 — VRP-gated Iron Fly (wings on the e011 straddle): VOID ❌** ([experiments/e016_vrp_iron_fly/](file:///d:/Code/dhanopt/experiments/e016_vrp_iron_fly/))
Every gate failed — max DD −₹2,03,033 (101.5%), EV −₹535.63/trade, total −₹1,56,941, WR 61% → 29% — but the input signal was a contract-identity artifact, so **the measurement is struck, not merely negative.** Its one transferable idea survives as a structural observation, and it recurs independently in e018: *wide wings cap the tail, they do not cap the drawdown.* Any future defined-risk version of a volatility book must expect a lower win rate and a worse recovery, and must be gated on expectancy, not on worst-case loss.

**D. E017 — Regime sizing + risk budget: VOID ❌** ([experiments/e017_regime_sizing/](file:///d:/Code/dhanopt/experiments/e017_regime_sizing/))
The sizing arithmetic was valid *on the frozen e011 book* and the mechanism is real and reusable: **the drawdown floor is the flat per-order fee treadmill, not convexity.** ₹83,166 of flat fees over the sample cannot be scaled away by sizing — DD(f) is U-shaped with a minimum at f≈0.52, and below that it gets *worse*. Only *skipping* a session moves the number, because a skipped session pays no fees. But every conclusion is attached to a void book: ~~"no fixed fraction of 1 lot reaches the 8% ceiling"~~ and ~~"e011 needs ₹6,40,930 of capital"~~ are statements about a bug. **What transfers:** any future option book at ₹2L must clear the same flat-fee arithmetic before a sizing study is worth running, and e018 hit the identical wall from a shorter holding period (₹861/trade against 75 pts of credit; breakeven half-spread **0.51 pts/leg**). *The credit-to-fee ratio, not the position size, is the binding constraint.*

---

### Phase 6: Shadow Execution & Production Gatekeeper
*Objective:* Validate strategy execution in real time without capital risk using the live WebSocket/REST capture infrastructure.
*Revised scope (2026-10-02):* with one candidate book, Phase 6 has exactly two jobs — observe **fills** for e013, and measure **drift** for the models the void/legacy engines produced. It is not waiting on new research.

#### 6.1 Shadow-Trading Protocol (Zero Capital)
1. **Collector Activation ([e009](file:///d:/Code/dhanopt/experiments/e009_wall_capture)):**
   * Ensure `capture_chains.py` is actively logging 60-second full OPTIDX snapshots via Windows Task Scheduler.
   * *Capital concurrency check:* the 10-of-44 overlap breach in §5.5 A only binds if a second book is ever added. For the single e013 candidate, verify its iron-fly RMS margin against ₹1,82,000 usable before the first order.
2. **Virtual Ledger:**
   * Signals generate virtual paper orders timestamped to the millisecond.
   * Marks are recorded from the next available 60-second snapshot (`top_bid_price` / `top_ask_price`).
   * **Contract identity is re-derived per signal row** from the trade date's own partition (invariant §5.6). The leak that voided e011 was a *shifted frame naming yesterday's contract*; a shadow runner that does not re-derive identity is where that would come back.
3. **Pre-Live Acceptance Gate (Gate 0 Protocol):**
   A strategy graduates to live execution with 1 lot only if it meets all three conditions:
   * **Minimum OOS Sample:** $\ge 60$ live-monitored shadow trading sessions.
   * **Realized Drift:** Live execution slippage $\le 1.25\times$ the modeled slippage in backtest.
   * **Zero Breaches:** Maximum daily drawdown limit (₹2,500) never breached.
   * *(added 2026-10-02)* **Contract identity:** 0 mismatches between the instrument signalled and the instrument quoted, over the same 60 sessions.

---

## 4. Execution Schedule & Milestones

| Timeline | Phase | Deliverable | Exit Gate |
|---|---|---|---|
| **Day 1 (Immediate)** | **Phase 1** [DONE] | Execute Overnight Fund pledge via broker portal. | Margin confirmed active in terminal; collateral yield accrual begins. **The only positive cash flow in the program — do this first.** |
| **Day 1 (Immediate)** | **e009** [DONE, NOT REGISTERED] | Register the `capture_chains.py` scheduled task. | Task runs; per-minute chain evidence accumulating. Nothing downstream of Phase 6 can start until this does. |
| **Weeks 1–2** | **Phase 2** [VOID ❌] | ~~Build `e011_vrp_delta_hedge`: RV vs IV + 5-min delta-neutral simulator.~~ | **Voided 2026-10-02 — contract-identity defect. +₹7.43L, Sharpe 2.85 and every sensitivity table built on it are struck.** |
| **Weeks 1–2 (retest)** | **Phase 2b** [DEAD ❌] | `e018_vrp_weekly`: contract-identity-correct signal, weekly 3–7 DTE condor held to expiry. | FAIL gates 2/3/5: EV −₹435, PF 0.82, DD 48.4%, breakeven 0.51 pts/leg. Gate 4 (contract identity) 0 violations — the fix works, the edge does not. |
| **Same window** | **Phase 2c** [DEAD ❌] | `e019_momentum` / `e020_diluted_momentum`: free NSE cash store, 12-1 momentum, top-20 and top-decile. | Friction-decay premise falsified (daily beat monthly 3.8×). Excess Sharpe **−0.81** (e019) and **+0.04** (e020) — the e020 return is beta. Control reproduced e019 exactly. |
| **Weeks 3–4** | **Phase 3** [KILLED ❌] | Build `e012_skew_ratio`: Parameterize 2021–2026 skew and test 1×2 ratio structures. | Decisively failed all 3 kill bars (PF 0.13, −₹98.8k). Ratio debit bleed confirmed. Labels are wall-free; verdict stands. |
| **Weeks 5–6** | **Phase 4** [DONE / CANDIDATE 🎯] | Build `e013_0dte_pin`: Replay 576 sessions in `e008` testing 12:30 PM Iron Fly vs Breakout. | Net +₹4.14L, EV +₹2,148/trade, PF 9.41, WR 83.9%, Max DD ₹11.9k (5.97%). **Clean under both convictions** — the only surviving strategy claim. Awaiting e009 live chain fills. |
| **Weeks 7–8** | **Phase 5** [DONE / GATE FAILED ❌] | Build `core/execution/maker.py` + e014 three-arm TCA. | Maker fails Gate 2 on the surviving book (EV +₹1,018 vs +₹2,149; 27.3% < 60%). Taker entry retained; 1.5 pts/leg slippage validated as non-optimistic. Passive exits → Phase 6 shadow. *E011 arm void.* |
| **Post-Phase 5** | **Analyses E015–E017** [VOID ❌] | Book combination, spread-width sweep, wings test, regime sizing. | **All struck**: one void leg voids the combination; the wings and sizing studies were computed on a mispriced signal. The transferable findings (wings cap the tail not the drawdown; flat fees are the sizing floor; breakeven half-spread 0.51 pts/leg) are recorded in §5.5. |
| **Month 3+** | **Phase 6** | Run Shadow-Trading Engine alongside the active e009 collector. | 60 consecutive sessions, zero identity mismatches, no risk breach, before 1-lot live deployment of e013. |
| **After that** | **Nothing open** | — | The negative space is mapped (§1.1). A new idea must name which of the five loss modes in [RETROSPECTIVE.md §6](file:///d:/Code/dhanopt/RETROSPECTIVE.md) it escapes. |

---

## 5. Non-Negotiable Engineering Invariants (The Rulebook)

1. **Information Time Horizon ($t-1$ Rule):** Any signal generated on bar $t$ must execute at bar $t+1$ Open. Same-bar execution is banned.
2. **No Data Snooping:** Hyperparameters (e.g. VRP threshold, rebalancing trigger) must be frozen *before* walk-forward evaluation. No sweep optimization. A kill bar that fails, fails. It is never moved after the result is seen — and when a *prior* bar is revealed to have been set on a wrong premise (e019's 60-rebalance bar, unreachable against its own warm-up), the correction is disclosed in the successor's PREREG, not applied silently.
3. **All Metrics Net of Zerodha Friction:** Never evaluate gross PnL. Every reported rupee must net:
   * Brokerage: ₹20/order leg.
   * STT: 0.1% on option sell value (post-Oct-2024 SEBI mandate).
   * Exchange turnover (0.0505%) + SEBI turnover (₹10/Cr) + Stamp duty (0.003%) + GST (18%).
   * Slippage: Minimum 1.5 points per option leg, 0.5 points per futures hedge.
   * **Flat per-order fees are not a detail.** They are the sizing floor. Any book whose expectancy is smaller than `orders × ₹20 + taxes` is not a book (§5.5 D; e018's 0.51-pt breakeven half-spread).
4. **Lot Size Compliance:** Every backtest must query `experiments/common/lots.py` to use the regulatory lot size active on `trade_date` (75, 50, 25, 75, or current 65).
5. **Fail-Closed Architecture:** If options chain data, volatility estimators, or quote freshness are missing, the system outputs `NO TRADE`. It never interpolates synthetic winning defaults.
6. **Contract Identity (v2, 2026-10-02 — the invariant that voided e011):** The instrument priced on day $t$ **is** the instrument that exists on day $t$. A `shift(1)` is a claim about *when*, not *what*, and a shifted frame can hand you yesterday's expiry, strike or tenor.
   * Any signal row must be able to name its contract from the **trade date's own partition** — the front expiry is read out of day $t$'s data, the straddle out of day $t-1$'s.
   * Identity is re-derived and asserted **per trade**, not once at load. Any mismatch fails the run.
   * **Corollary — publish the signal's distribution before its PnL.** A mean IV of 0.476 with a max of 1.93 is a bug report, not a result. Implied volatility above 1.0, or a tenor that shortens rather than leads, is a hard stop.
7. **The Leak Registry is Constitutional:** No module produces a PnL number without a declared information set (`t-1` / `day-t` / `none`) and a live-replicability flag in [experiments/common/leak_registry.py](file:///d:/Code/dhanopt/experiments/common/leak_registry.py); `day-t ⇒ not live` is enforced by test. A PnL number without a registry row is itself a test failure. **A conviction is also a registry row** — e011's defect is written there so it cannot be inherited a third time.
8. **Benchmark First; Gate on Excess:** Every long-only equity book is reported against a **same-universe equal-weight benchmark** over the same days with the same costs, and the bar is on **excess Sharpe**, not on CAGR level. A long-only book in a bull market earns 21% CAGR at 1.15 Sharpe from beta alone; a momentum book that "returns 24.8%" while the universe returns 21.3% at 1.15 has returned nothing.
9. **Impossibility Audits and Failure Diagnostics:** Any structure with a closed-form maximum loss (condor, fly, spread) is checked against it **per trade** — a violation is a pricing bug, not a tail event. Any book held over a horizon is reported with the **death rate** of its holdings versus the universe, because names that stop trading are silently dropped by every naive forward-return study. Both are gates in e018/e020 and both are cheap.
10. **Controls Beat Diagnostics:** A follow-up engine **must re-run its predecessor's exact configuration and land on the same number to the decimal** before any of its new numbers are believed. e020 reproducing e019's −0.81 excess Sharpe is the standard. Fifty PnL metrics produce nothing; one control that reproduces a predecessor produces a decision.
11. **Suspicion Scales with Roundness:** Win rates above 85%, profit factors above 5, and drawdowns that are suspiciously shallow are treated as presumptively broken until the information-set audit clears them. Real books have ugly tails.
