# Quantitative Action Plan: Institutional-Grade Nifty Options Engine
**Architectural Blueprint & Execution Roadmap (Kailash Nadh Perspective)**  
*Target Environment:* Windows (pwsh) / Linux (bash) | Python 3.11+ | Single Source of Truth  
*Base Capital:* ₹2,00,000 (Account Bankroll) | Current Regulatory Era: **65 Lot Size** (NSE FAOP70616)  
*Status:* Active Master Plan (Replaces Discredited BRD v2.1 Directional Models)

---

## 1. Executive Summary & Foundational Reality

Every options strategy previously celebrated in this sandbox ([e001](file:///d:/Code/dhanopt/experiments/e001_leakfree_replay) to [e006](file:///d:/Code/dhanopt/experiments/e006_compound_sim)) collapsed under rigorous audit:
1. **The Day-t Look-Ahead Leak:** Strategies relied on max-OI walls computed from **15:30 EOD option chains**, an information leak of 6 hours. When tested against real opening OI ([e007](file:///d:/Code/dhanopt/experiments/e007_open_oi)), edge collapsed from +₹940,697 to **−₹309 (4 trades, PF 0.96)**.
2. **Directional Spreads Bleed:** Naive momentum continuation ([e004](file:///d:/Code/dhanopt/experiments/e004_intraday_replay)) lost −₹314k (bull) and −₹147k (bear) under realistic intraday paths.
3. **ML Without Monetary Edge:** ML models ([e010](file:///d:/Code/dhanopt/experiments/e010_ml_gate)) achieved real statistical discrimination (Brier 0.295 < 0.318), yet lost −₹121k because the underlying spread structure possessed negative expectancy after Zerodha friction and bid-ask drag.

### What the "Top 1%" Do Differently
Institutional prop desks (Graviton, NK Securities, Quadeye, Tower, Jane Street) do not gamble on 5-minute directional momentum or static 1.4× stop-loss Iron Condors. They monetize three structural phenomena:
1. **The Variance Risk Premium (VRP):** Implied Volatility (IV) is systematically higher than Realized Volatility (RV) over multi-year horizons due to risk aversion and institutional hedging demand. They harvest this through **delta-neutral straddles/strangles dynamically hedged with futures**, not static premium stop-losses.
2. **Volatility Surface & Skew Asymmetry:** Exploiting dislocations between Put Skew (elevated by retail crashophobia) and Call Skew via ratio structures and relative value.
3. **0DTE Gamma Inventory & Pinning:** Exploiting market maker delta-hedging flows near expiry (Tuesday/Thursday) to capture mean-reversion around structural strikes or ride liquidity stop-runs.

This action plan defines the exact steps to build, test, and validate these institutional edges using **only the data currently resident on disk or accessible via existing endpoints**, eliminating all guesswork and unstated assumptions.

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
│   └── calibrated_params.json          # (Frozen; fail-closed calibration rules)
├── experiments/
│   ├── e008_wall_flip/artifacts/
│   │   ├── walls_576.tar.gz            # 576 sessions of 5-min option chains (OI, quotes) for dte <= 1
│   │   └── walls/<date>.json           # Minute-level chain dumps
│   └── common/
│       ├── lots.py                     # Historical lot sizes: 75 -> 50 -> 25 -> 75 -> 65
│       └── leak_registry.py            # Information-set tracking (t-1 vs day-t)
```

---

## 3. The Master Execution Phases

```mermaid
flowchart TD
    P1[Phase 1: Capital & Collateral Optimization] --> P2[Phase 2: True VRP Engine & Delta-Neutral Replay]
    P2 --> P3[Phase 3: Volatility Skew & Ratio Architecture]
    P3 --> P4[Phase 4: 0DTE Expiry Microstructure & Pin Dynamics]
    P4 --> P5[Phase 5: Execution Microstructure & Limit Order TCA]
    P5 --> P6[Phase 6: Shadow Paper-Trade & Production Gatekeeper]
```

---

### Phase 1: Zero-Risk Baseline — Capital & Collateral Yield [COMPLETED ✅]
*Objective:* Guarantee an immediate, market-independent baseline yield on the ₹2,00,000 bankroll before taking any derivatives risk. Stop earning 3.0% in bank savings.
*Status:* **COMPLETED.** Engine implemented in [core/collateral.py](file:///d:/Code/dhanopt/core/collateral.py); verified in [tests/test_collateral.py](file:///d:/Code/dhanopt/tests/test_collateral.py).

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
- [x] Integrate `CollateralManager` into Phase 2 VRP replay (`experiments/e011_vrp_delta_hedge/replay_vrp.py`) enforcing fail-closed capital limits.
- [ ] User Action: Transfer idle funds to broker account & purchase direct growth overnight fund units.
- [ ] User Action: Initiate broker margin pledge flow via depository (CDSL/NSDL).
- [x] Reference complete operational manual in [COLLATERAL_PLAYBOOK.md](file:///d:/Code/dhanopt/COLLATERAL_PLAYBOOK.md).

---

### Phase 2: True Variance Risk Premium (VRP) & Dynamic Delta-Hedging [COMPLETED ✅]
*Objective:* Harvest the structural spread between Implied Volatility ($IV$) and Realized Volatility ($RV$) without taking directional market risk.
*Status:* **COMPLETED.** Engine built in [experiments/e011_vrp_delta_hedge/](file:///d:/Code/dhanopt/experiments/e011_vrp_delta_hedge/).
*Results:* **Net +₹7,43,572.25**, **Sharpe 2.85**, **Profit Factor 3.99**, **Win Rate 61.1%** across 293 trades (5.7 yrs).
*Kill Criteria Status:*
  * Kill 1 (Sharpe $\ge 1.5$): **PASS (2.85)**.
  * Kill 2 (Max DD $\le 8.0\%$ / ₹16k): **FAIL (₹51,274 / 25.6%)** — Naked straddle whipsaw friction during choppy regime shifts motivates Phase 4 defined wings (Iron Fly).
  * Kill 3 (Slippage Cliff $\ge 2.5\times$): **PASS (Survives past $5.0\times$ slippage with +₹2.90L net)**.
  * Kill 2 remediation attempt (E016 Iron Fly wings): **KILLED ❌** — wings *multiplied* drawdown to −₹2.03L (101.5%) and flipped expectancy negative; naked architecture retained pending a regime-sizing pre-registration (§5.5 C).
  * Kill 2 remediation attempt (E017 regime sizing + risk budget): **KILLED ❌** — half size on elevated-RV/loss-clusters moves DD only 25.6% → 25.4%; **no fixed fraction of 1 lot reaches the 8% ceiling** (min −₹40.5k at f≈0.52 — the DD floor is the ₹20/order friction treadmill). Only skip-rules move it (k=3 cluster stop: 17.4% DD at +₹14.5k vs base, still > 8%). Detail: §5.5 D.

#### 2.1 The Core Quantitative Edge
* **Why previous condors failed:** Static stop-losses (e.g. 1.4× credit SL) guarantee buying at the peak of implied volatility during intraday whipsaws. Real prop desks do not stop out of volatility; they **delta-hedge**.
* **The Mathematical Relationship:**
  The expected PnL of a delta-hedged option position is governed by:
  $$\mathbb{E}[\text{PnL}] \approx \frac{1}{2} \int_0^T S_t^2 \Gamma_t \left( \sigma_{\text{implied}}^2 - \sigma_{\text{realized}}^2 \right) dt - \text{Friction}$$
  Where $\Gamma_t$ is the portfolio gamma and $S_t$ is the underlying spot price. If $\sigma_{\text{implied}} > \sigma_{\text{realized}}$, net PnL is mathematically positive if delta is neutralized.

#### 2.2 Volatility Forecasting & VRP Filter
Using the historical 5-minute spot store (`data/intraday/interval=5/`):
1. **Realized Volatility ($RV$) Estimators:**
   Compute Parkinson and Garman-Klass intraday volatility over trailing 5, 10, and 20 sessions:
   $$\sigma_{GK}^2 = \frac{1}{n} \sum_{i=1}^n \left[ 0.5 \left(\ln \frac{H_i}{L_i}\right)^2 - (2\ln 2 - 1) \left(\ln \frac{C_i}{O_i}\right)^2 \right]$$
2. **Implied Volatility ($IV_{\text{ATM}}$):**
   Invert Black-Scholes from the $t-1$ EOD ATM straddle price from `data/historical/`.
3. **The VRP Entry Signal:**
   $$\text{VRP}_t = IV_{\text{ATM}, t-1} - \sigma_{GK, 10d}(t-1)$$
   Only enter short volatility when $\text{VRP}_t \ge \text{Percentile}_{80}(\text{trailing } 60\text{ days})$ and $\text{VRP}_t > 0$.

#### 2.3 Intraday Delta-Neutral Replay Architecture
Build `experiments/e011_vrp_delta_hedge/`:
* **Entry:** At 09:20 IST on Day $t$, sell 1 lot of ATM Call + 1 lot of ATM Put (ATM Straddle) for the nearest expiry.
* **Delta Neutralization Mechanism:**
  Track portfolio delta $\Delta_{\text{net}} = \Delta_{\text{CE}} + \Delta_{\text{PE}} + \Delta_{\text{Futures}}$ at every 5-minute bar.
  * *Threshold Rebalancing:* When $|\Delta_{\text{net}}| \ge 0.15$ (i.e. $\approx 10$ Nifty points of directional exposure for 65 lot size), execute a synthetic Nifty Futures hedge at bar $t+1$ Open to reset $\Delta_{\text{net}} \to 0$. Same-bar execution is strictly prohibited.
  * *Exit:* 15:15 IST square-off across all option and hedge positions.
* **Friction Inclusion:**
  * Option legs: ₹20/order brokerage + 0.1% STT on sell turnover + 1.5 pts slippage.
  * Futures hedge: ₹20/order brokerage + 0.02% STT on sell turnover + 0.5 pts slippage.
  * Regulatory fees: Exchange turnover (0.0505%), SEBI turnover (₹10/Cr), Stamp duty (0.003%), GST (18%).

#### 2.4 Pre-Registered Kill Criteria for Phase 2
| Metric | Threshold Bar | Observed | Status |
|---|---|---:|---|
| Annualized Sharpe Ratio | $\text{Sharpe} \ge 1.5$ (net of all friction) | **2.85** | ✅ **PASS (Strong)** |
| Maximum Peak-to-Trough DD | $\le 8.0\%$ of ₹2,00,000 (₹16,000) | **₹51,274 (25.6%)** | ❌ **FAIL** |
| Slippage Cliff | Retains positive expectancy at $\ge 2.5\times$ modeled slippage | **+₹5,73,824 (2.5×)** | ✅ **PASS (Resilient)** |

#### 2.5 Detailed Empirical Performance Summary (2021–2026, 5.7 Years)
```
Total Trading Sessions:     1,410 days (2021-01 to 2026-09)
Signals Triggered:          293 sessions (51.4 trades / year)
Win Rate:                   61.09% (179 wins / 114 losses)
Total Gross PnL:            +₹10,10,876.98 (pre-friction mark-to-market)
Total Zerodha Friction:     ₹2,67,304.73 (avg ₹912.30 / trade across 293 sessions)
Total Net PnL:              +₹7,43,572.25
Sum of Net Winning Trades:  +₹9,91,937.00
Sum of Net Losing Trades:   -₹2,48,364.75
Average Net / Trade:        +₹2,537.79
Annual Net Run-Rate:        +₹1,30,451 / year (~65.2% on ₹2L capital)
Profit Factor:              3.99 (Net Winning Trades ₹9,91,937 / Net Losing Trades ₹2,48,365)
Annualized Sharpe Ratio:    2.85
Max Peak-to-Trough DD:      -₹51,274.41 (-25.64% of ₹2L bankroll)
```

#### 2.6 Sensitivity Matrix: Volatility Estimator Window Comparison
Testing across 5-day, 10-day, and 20-day rolling windows for both Garman-Klass ($\sigma_{GK}$) and Parkinson ($\sigma_P$) estimators confirms that the edge is mathematically robust and not an artifact of window overfitting:

| Volatility Estimator | Window | Trades | Total Net PnL (₹) | Profit Factor | Win Rate | Sharpe Ratio | Max Drawdown (₹) |
|---|:---:|---:|---:|:---:|:---:|:---:|---:|
| **Garman-Klass ($\sigma_{GK}$)** | 5-day | 283 | **+7,54,625.23** | **4.15** | 61.5% | **2.92** | -44,582.63 |
| **Garman-Klass ($\sigma_{GK}$)** | 10-day (Base) | 293 | **+7,43,572.25** | 3.99 | 61.1% | 2.86 | -51,274.41 |
| **Garman-Klass ($\sigma_{GK}$)** | 20-day | 280 | **+7,45,409.45** | 3.94 | 60.0% | 2.85 | -57,259.73 |
| **Parkinson ($\sigma_P$)** | 5-day | 286 | **+7,59,833.10** | **4.26** | 61.9% | **2.94** | -48,129.20 |
| **Parkinson ($\sigma_P$)** | 10-day | 287 | **+7,29,487.13** | 3.89 | 61.0% | 2.79 | -61,934.30 |
| **Parkinson ($\sigma_P$)** | 20-day | 280 | **+7,63,515.33** | 4.15 | 61.8% | 2.94 | -62,686.81 |

#### 2.7 Sensitivity Matrix: Delta Rebalancing Threshold Sweep
Sweeping the delta rebalance trigger $|\Delta_{\text{net}}| \ge \text{Threshold}$ illuminates the tradeoff between delta risk and execution friction:

| Rebalance Threshold | Avg Hedges / Day | Avg Friction / Trade (₹) | Total Net PnL (₹) | Profit Factor | Win Rate | Sharpe | Max Drawdown (₹) |
|:---:|:---:|---:|---:|:---:|:---:|:---:|---:|
| **0.10** (Tight) | 13.0 | ₹1,086.90 | +6,84,478.45 | 3.54 | 59.0% | 2.64 | -67,545.41 |
| **0.15** (Baseline) | 8.0 | ₹912.30 | +7,43,572.25 | 3.99 | 61.1% | 2.86 | -51,274.41 |
| **0.20** (Optimal) | 5.8 | ₹827.30 | **+7,62,982.94** | **4.22** | **63.5%** | **2.96** | **-40,915.88** |
| **0.25** (Loose) | 4.4 | ₹767.20 | +7,63,708.78 | 4.11 | 63.5% | 2.95 | -41,823.53 |

*Insight:* Tight rebalancing (0.10) over-trades, incurring ₹1,087 in friction and whipsawing on noise. A slightly wider threshold (0.20) lets micro-fluctuations mean-revert without paying bid-ask spread and STT on futures, cutting drawdown by ₹10,358.

#### 2.8 Slippage Cliff Stress Test ([slippage_cliff.py](file:///d:/Code/dhanopt/experiments/e011_vrp_delta_hedge/slippage_cliff.py))
Subjecting the baseline strategy to extreme slippage multipliers:

| Slippage Multiplier | Effective Option Slippage | Effective Futures Slippage | Total Net PnL (₹) | Profit Factor | Sharpe Ratio | Max Drawdown (₹) |
|:---:|:---:|:---:|---:|:---:|:---:|---:|
| **1.0× (Baseline)** | 1.5 pts / leg | 0.5 pts / leg | **+7,43,572.25** | **3.99** | **2.85** | -51,274.41 |
| **1.5×** | 2.25 pts / leg | 0.75 pts / leg | **+6,86,989.37** | 3.52 | 2.64 | -65,271.77 |
| **2.0×** | 3.00 pts / leg | 1.00 pts / leg | **+6,30,406.49** | 3.12 | 2.42 | -89,878.56 |
| **2.5× (Kill Bar)** | 3.75 pts / leg | 1.25 pts / leg | **+5,73,823.62** | 2.77 | 2.21 | -121,384.84 |
| **3.0×** | 4.50 pts / leg | 1.50 pts / leg | **+5,17,240.74** | 2.46 | 1.99 | -152,983.94 |
| **4.0×** | 6.00 pts / leg | 2.00 pts / leg | **+4,04,074.99** | 1.98 | 1.56 | -216,182.12 |
| **5.0× (Severe)** | 7.50 pts / leg | 2.50 pts / leg | **+2,90,909.24** | 1.61 | 1.12 | -281,559.61 |

*Verdict:* Survives well past $5.0\times$ slippage (+₹2.91L net), easily clearing Kill Criterion 3.

#### 2.9 Kailash Nadh Post-Mortem: Why Kill Criterion 2 Failed & The Architectural Solution
1. **The Edge is Real:** Unlike directional momentum spreads ([e004](file:///d:/Code/dhanopt/experiments/e004_intraday_replay), which lost −₹314k) or naive ML gating ([e010](file:///d:/Code/dhanopt/experiments/e010_ml_gate), which lost −₹121k), the Variance Risk Premium is mathematically sound. Even after paying ₹2,67,305 in Zerodha friction (avg ₹912.30/trade across 293 sessions), the strategy netted +₹7,43,572.
2. **The Whipsaw Mechanism:** On choppy, high-volatility trend days (e.g. 2022-01-21, 2021-07-09), threshold delta-hedging executed 22 to 36 futures orders in a single session. The strategy incurred over ₹2,000 in friction and got chopped repeatedly as spot reversed, causing single-day losses of −₹7,000 to −₹9,000.
3. **The ₹2L Capital Reality:** On a ₹2,00,000 bankroll, a consecutive cluster of choppy sessions produced a ₹51,274 drawdown (25.64%), breaching the strict institutional 8.0% (₹16,000) ceiling.
4. **The Direct Architectural Solution:** Naked straddles carry uncapped tail risk on choppy trend days. In **Phase 4 (0DTE Pin Harvest Iron Fly)**, adding defined-risk wings clamped maximum peak-to-trough drawdown to **₹11,940 (5.97% < 8.0%)**, solving the drawdown problem while retaining a 9.41 Profit Factor.

#### 2.10 Phase 2 Execution Checklist & Code Deliverables
- [x] Implemented Garman-Klass ($\sigma_{GK}$), Parkinson ($\sigma_P$), and Black-Scholes IV inversion engine with strictly shifted $t-1$ metrics ([experiments/e011_vrp_delta_hedge/volatility.py](file:///d:/Code/dhanopt/experiments/e011_vrp_delta_hedge/volatility.py)).
- [x] Implemented dynamic delta-hedging replay engine with strict $t+1$ bar Open execution, era-correct regulatory lots (75 $\to$ 50 $\to$ 25 $\to$ 75 $\to$ 65), Phase 1 collateral gate integration, and post-Oct 2024 Zerodha fee schedules ([experiments/e011_vrp_delta_hedge/replay_vrp.py](file:///d:/Code/dhanopt/experiments/e011_vrp_delta_hedge/replay_vrp.py)).
- [x] Parameterized sensitivity matrix sweeps across 6 volatility estimator configurations and 4 delta rebalance thresholds ([experiments/e011_vrp_delta_hedge/sensitivity.py](file:///d:/Code/dhanopt/experiments/e011_vrp_delta_hedge/sensitivity.py)).
- [x] Implemented slippage cliff stress tester validating resilience past $5.0\times$ slippage ([experiments/e011_vrp_delta_hedge/slippage_cliff.py](file:///d:/Code/dhanopt/experiments/e011_vrp_delta_hedge/slippage_cliff.py)).
- [x] Comprehensive unit test suite covering BS straddle inversion, Put-Call parity, $t+1$ hedge fill rule, strict $t-1$ shift, GK/Parkinson math, threshold behavior, Phase 1 collateral gate enforcement, and pre-registered kill criteria ([experiments/e011_vrp_delta_hedge/test_e011.py](file:///d:/Code/dhanopt/experiments/e011_vrp_delta_hedge/test_e011.py) — 8 passing tests in 2.27s).
- [x] Registered in [experiments/common/leak_registry.py](file:///d:/Code/dhanopt/experiments/common/leak_registry.py) under the $t-1$ information frontier.
- [x] Generated and preserved all 6 empirical artifacts: `volatility_daily.parquet`, `vrp_daily.csv`, `metrics.json`, `slippage_cliff.json`, `sensitivity_volatility.json`, `sensitivity_threshold.json`.

---

### Phase 3: Volatility Skew & Asymmetric Ratio Architecture [COMPLETED / KILLED ❌]
*Objective:* Monetize the structural overpricing of OTM puts (crashophobia) through self-financing ratio spreads rather than directional buying/selling.
*Status:* **COMPLETED & KILLED.** Engine built in [experiments/e012_skew_ratio/](file:///d:/Code/dhanopt/experiments/e012_skew_ratio/).
*Results:* **Net −₹98,801.92**, **Profit Factor 0.13**, **Win Rate 14.78%**, **15 consecutive losses** across 115 trades (2021–2026).
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
|---|---|---:|---|
| Profit Factor | $PF \ge 1.80$ over 2021–2026 walk-forward | **0.13** | ❌ **FAIL** |
| Win Rate | $\ge 70\%$ on valid signal sessions ($\le 3$ consec losses) | **14.8% (15 max losses)** | ❌ **FAIL** |
| Total Trades | $\ge 25$ occurrences per year | **20.2 / yr** | ❌ **FAIL** |

---

### Phase 4: 0DTE Expiry Microstructure & Pin Dynamics [COMPLETED / VALIDATED CANDIDATE 🎯]
*Objective:* Exploit market maker delta inventory and structural hedging behavior during 0DTE sessions (Tuesday/Thursday).
*Status:* **COMPLETED.** Engine built in [experiments/e013_0dte_pin/](file:///d:/Code/dhanopt/experiments/e013_0dte_pin/).
*Results:*
  * **Pin Harvest (Iron Butterfly, $\text{Ratio} \le 0.65$):** **Net +₹4,14,721.03**, **Net EV +₹2,148.81 / trade** (crushes the +₹600 bar by 3.5×!), **Win Rate 83.94%**, **Profit Factor 9.41**, **Max DD ₹11,940 (5.97% < 8.0%)**, **Sharpe 5.52** across 193 sessions (33.9 trades/yr).
  * **Gamma Breakout ($\text{Ratio} \ge 1.20$):** **Net −₹46,269.29**, **Net EV −₹564.26**, **Profit Factor 0.58**, **Win Rate 31.7%** (direction dead).
*Kill Criteria Status:*
  * Kill 1 (Net EV $\ge +₹600$): **PASS (Pin Iron Fly: +₹2,148.81 / trade)**.
  * Kill 2 (Fill Feasibility $\ge 80\%$): **DATA CEILING on e008 artifacts (0.0% observable due to ATM omission in `fetch_walls.py`)** $\implies$ Validates that live execution requires [e009](file:///d:/Code/dhanopt/experiments/e009_wall_capture) full-chain live capture.

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
|---|---|---:|---|
| Post-12:30 Expectancy (Pin Fly) | Net EV $\ge +₹600$ per lot | **+₹2,148.81 / trade** | ✅ **PASS (Strong)** |
| Post-12:30 Expectancy (Breakout) | Net EV $\ge +₹600$ per lot | **−₹564.26 / trade** | ❌ **FAIL (Killed)** |
| Fill Feasibility (in e008 data) | $\ge 80\%$ legs observable | **0.0% (ATM omitted)** | ⚠ **REQUIRES E009 LIVE DATA** |

---

### Phase 5: Execution Microstructure & Limit Order TCA [COMPLETED / GATE FAILED ❌]
*Objective:* Eliminate the "Taker Penalty" that systematically destroys retail multi-leg options trading.
*Status:* **COMPLETED & GATE FAILED.** Engine built in [core/execution/maker.py](file:///d:/Code/dhanopt/core/execution/maker.py); TCA run in [experiments/e014_maker_tca/](file:///d:/Code/dhanopt/experiments/e014_maker_tca/).
*Results:* Passive-only (maker, all-or-none) execution **fails Gates 2 & 3 on both validated strategies**: E013 Pin Fly maker EV +₹1,018/trade vs +₹2,149 taker (aggregate ratio 27.3% < 60%); E011 VRP Straddle maker EV +₹959/trade vs +₹2,538 taker (ratio 22.4%). Basket fill-rate gate passed (57.5% / 59.4% ≥ 50%). **Decision: taker entry retained; passive execution relegated to exits and Phase 6 measurement.**

#### 5.1 The Friction Trap (Why Retail Loses 25%+ to Intermediaries)
In a 4-leg Iron Condor or 2-leg spread:
* Crossing the spread (market order / aggressive taker): Paying $\approx 1.5$ to $2.0$ points per leg $\implies 6.0$ to $8.0$ index points ($₹390$ to $₹520$ per lot) lost on entry and exit combined.
* Taxes (STT 0.1% on sell side post-Oct 2024, GST 18%, Exchange fees): $\approx ₹120$ per lot.
* Total initial deficit: **$\approx ₹500$ to $₹640$ per lot before the trade even moves.**

#### 5.2 The Maker Execution Engine
Build `core/execution/maker.py`:
1. **Passive Limit Placement:**
   * Calculate Mid-Price: $\text{Price}_{\text{mid}} = \frac{\text{Bid} + \text{Ask}}{2}$.
   * Place limit orders at $\text{Bid} + 1\text{ tick}$ (for buy) or $\text{Ask} - 1\text{ tick}$ (for sell).
2. **Queue & Fill Simulator (for Backtesting):**
   * An order is assumed filled *only* if subsequent trade prints occur at prices strictly through the limit price, OR if total volume traded at that price exceeds $3\times$ our order size.
3. **Adverse Selection Penalty:**
   * Any fill that occurs immediately before an adverse 5-minute move of $> 0.20\%$ is logged as adverse selection and penalized in the backtest.

#### 5.3 E014 TCA Results: Maker vs Taker (Pre-Registered, [PREREG](file:///d:/Code/dhanopt/experiments/e014_maker_tca/PREREG.md))
Both validated strategies were re-replayed under identical timing in three arms — TAKER (reproduces published E011/E013 accounting exactly, verified per-session), MAKER (all-or-none passive basket, NO TRADE if any leg misses its 30-min entry window), HYBRID (E013 only: passive entry, taker chase after window). Option mids are Black-Scholes on the 5-min spot store with session IV (half-spread 1.5 pts = the frozen taker slippage; no volume tape on options, so fills require strictly-through prints — pessimistic on fill probability).

| Arm | E013 Pin Fly Net EV | E013 Total Net | E011 VRP Net EV | E011 Total Net |
|---|---:|---:|---:|---:|
| **TAKER** | **+₹2,148.81** | **+₹4,14,721** | **+₹2,537.79** | **+₹7,43,572** |
| **MAKER (AON)** | +₹1,018.29 (111/193 filled) | +₹1,13,031 (27.3% of taker) | +₹959.12 (174/293 filled) | +₹1,66,887 (22.4% of taker) |
| **HYBRID** | +₹666.58 (193/193) | +₹1,28,651 | out of scope (hedge schedule depends on entry timing) | — |

*Decomposition of the −₹1,130/trade maker collapse (E013):*
1. **Session-level fill selection is NOT the cause:** taker EV on exactly the maker-filled sessions is +₹2,161 vs +₹2,149 overall (+₹12 delta). Calm days fill more often; the surviving subset is not worse.
2. **Adverse selection is real but secondary:** 71.8% of passive fills were flagged (move ≥ 0.20% against the leg within 5 min) and re-priced at the taker alternative — the queue gives back ~₹2.33L of the ~₹4.0L gross improvement it captures across both books.
3. **Missed sessions are the killer:** 82 of 193 Pin Fly sessions and 119 of 293 VRP sessions never traded (~₹1.76L and ~₹3.02L forgone taker EV). These are theta-harvesting books: their edge lives on fast days, and on fast days option mids sweep through passive limits instantly (flagged adverse) or never touch them.

*Verdict:* The option premium moves more than the full modeled spread within one 5-minute bar far too often for a passive bid/ask∓1 tick to get paid to wait. **These are spread-crossing strategies by construction.** The only defensible passive leg is the **exit** (54.7% of E013 exit legs filled passively where urgency is lowest); entry remains taker. A valuable corollary: E011/E013's frozen 1.5 pts/leg taker slippage assumption is *not* optimistic — the maker alternative is strictly worse, so published net-PnL figures stand as upper bounds under execution risk, not fictions.

#### 5.4 Phase 5 Execution Checklist & Code Deliverables
- [x] Passive limit placement, bar-based queue & fill simulator (strict-through OR touch + 3× volume), adverse-selection penalty ([core/execution/maker.py](file:///d:/Code/dhanopt/core/execution/maker.py); 12 unit tests in [tests/test_maker_execution.py](file:///d:/Code/dhanopt/tests/test_maker_execution.py)).
- [x] Non-invasive passive-execution seam in the E011 engine (`entry_bar`, `strike_override`, `entry_fill_*`, `exit_fill_*` on `simulate_session`; defaults reproduce published behavior — all 8 E011 tests still pass).
- [x] Pre-registered three-gate protocol frozen before the run, with two pre-run mechanical amendments documented (put-leg sign correctness in the adverse flag; reprice pinned to taker-at-posting) ([experiments/e014_maker_tca/PREREG.md](file:///d:/Code/dhanopt/experiments/e014_maker_tca/PREREG.md)).
- [x] Three-arm TCA replay across 293 VRP + 193 Pin Fly sessions with per-leg fill logs ([experiments/e014_maker_tca/tca.py](file:///d:/Code/dhanopt/experiments/e014_maker_tca/tca.py)); artifacts: `trades.csv` (1,165 session-arms), `maker_fills.csv` (3,467 leg fills), `metrics.json`.
- [x] Fidelity integration tests: TAKER arms reproduce published E013 per-session and E011 aggregate PnL exactly (7 tests in [experiments/e014_maker_tca/test_e014.py](file:///d:/Code/dhanopt/experiments/e014_maker_tca/test_e014.py)).
- [x] Findings & post-mortem ([experiments/e014_maker_tca/README.md](file:///d:/Code/dhanopt/experiments/e014_maker_tca/README.md)).
- [ ] Phase 6 scope update: shadow-test the **hybrid exit-only** maker configuration (taker entry, passive exit) — the only maker variant that survived analysis.

#### 5.5 Post-Phase-5 Production Analyses (E015 Book Composition + Spread-Width Sensitivity)

**A. Book composition — E011 × E013 on one ₹2L account** ([experiments/e015_book_combo/](file:///d:/Code/dhanopt/experiments/e015_book_combo/)):
* Session overlap: **44 days** vs 40.1 expected if independent; same-day PnL correlation **+0.18** — the two books are nearly independent selectors.
* Combined book (442 trade-days): **+₹11,58,293**, EV **+₹2,620.57/trade-day**, PF 4.93, Sharpe 4.14, **joint max DD −₹32,076 (16.0%)** vs E011-alone 25.6%. Diversification cuts the tail by ₹19.2k but does **not** reach the 8% ceiling — E011's choppy-regime cluster remains the binding constraint (fix = Phase 4 wings/regime scaling, not diversification).
* Capital: avg margin use 56.9% of usable on trade days (upper-bound model); **10 of 44 overlap days breach the ₹1,82,000 usable margin under the conservative naked-straddle bound** (all 65-lot era, Dec-2024→Sep-2026). Action: verify iron-fly RMS margin; on confirmed breaches prioritize E013 for the slot (Sharpe 5.52 vs 2.85, DD 5.97% vs 25.6%).

**B. Spread-width sensitivity — 1.0→3.0 pts/leg**:
Exact linear reconstruction over the frozen artifacts: `net(p) = gross − [friction_published + (p − 1.5) × 4 × lot]`.
* Breakeven per-leg spread: **E011 13.0 pts**, **E013 10.7 pts** — the 1.5-pt assumption sits deep inside the safe zone.
* At 3.0 pts/leg (2× baseline): E011 still **+₹6.47L** (EV +₹2,207, Sharpe 2.49); E013 **+₹3.47L** (EV +₹1,799, PF 6.75, Sharpe 4.68). E013's max DD stays under the ₹16k ceiling until ~4.9 pts/leg.
* Conclusion: neither book flips negative under 3× execution-quality degradation; the binding risks are session selection and tail regimes, not spread width.

**C. E016 — VRP-gated Iron Fly (wings on the E011 straddle): KILLED ❌** ([experiments/e016_vrp_iron_fly/](file:///d:/Code/dhanopt/experiments/e016_vrp_iron_fly/)):
* Frozen rule: symmetric wings at $W = \max(150, 1\sigma_{GK,10d} \sqrt{DTE/365}\, S)$ on the 50-pt grid, every other E011 rule untouched; plus a fixed-width diagnostic table (100–300 pts, not used for selection).
* Result: **all 3 gates fail** — max DD **−₹2,03,033 (101.5%)** vs the ≤8% bar, EV **−₹535.63/trade**, total **−₹1,56,941**. Win rate collapses 61% → 29%. Every width from 100 to 300 pts fails Gate 1 by ~10×; the naked straddle strictly dominates all winged variants on this signal.
* Mechanism (measured): E011's income is the option book (+₹9.02L of +₹10.11L gross); 1σ wings surrender ~89 pts/session (over half the straddle credit) while keeping the short-gamma sign. Per-session loss IS capped (₹7.5k < ₹9.2k naked) but the truncated upside cuts the win rate, so the fly bleeds less per bad day yet loses far more often — **wings cap the tail, not the drawdown**. Trend-day losses (2021-07-09, 2022-01-21, 2024-02-02) persist: spot between short strike and wing plus futures whipsaw. Contrast with E013: wings work there because the book is static 2h40m on compressed days with no hedge; E011 is 5h50m of dynamic hedging — holding dynamics, not wing width, decide the economics.
* Next remediation (pre-register separately): regime-based position sizing (half size in elevated-RV regimes / after loss clusters) or trend-confirmation session stops — the drawdown is cumulative friction + hedge whipsaw, not convexity tail.
* Engineering: BS helpers consolidated into [core/pricing.py](file:///d:/Code/dhanopt/core/pricing.py) (single source of truth; e011–e014 and tests refactored; all frozen numerics bit-for-bit identical).

**D. E017 — Regime-based position sizing + E011 risk budget: SIZING KILLED ❌; ceiling structurally unreachable at ₹2L/1 lot** ([experiments/e017_regime_sizing/](file:///d:/Code/dhanopt/experiments/e017_regime_sizing/)):
* Frozen rule: f = 0.5 when σ_GK,10d(t−1) > trailing-60-session 75th percentile OR the last two taken sessions both lost; else 1.0. Exact per-session fractional arithmetic on the frozen artifacts (`net(f) = f·net(1) − (1−f)·flat`, flat = ₹94.40 entry/exit + ₹23.60/hedge order — only ₹20/order fees are size-invariant; hedge counts are per-share-triggered, hence size-invariant; no re-simulation).
* Result: **Gates 2–3 pass (EV +₹2,023, total +₹5.93L = 79.7% of base), Gate 1 fails** — max DD −₹51,274 → **−₹50,859 (25.4%)** with 118 of 293 sessions halved. Regime-only −₹49,270; cluster-only **−₹52,912 (worse than base)** — half-sizing after 2 losses shaves the recovery wins (marginal wins flip to losses under flat-fee drag).
* Mechanism (measured): the max DD is a 21-month chop (86 sessions, 2022-11→2024-07) whose −₹45.4k net is **65% flat per-order fees** (905 hedge orders). DD(f) is U-shaped with minimum **−₹40,542 at f≈0.52**; below f≈0.6 sizing *deepens* DD (at f=0.25: −₹47.9k; f=0.06: −₹54.9k > full size) because the variable income shrinks but ₹83,166 of flat fees over the sample does not. **Breakeven fraction does not exist** — no f ∈ [0.05, 1] puts DD under ₹16k. Elevated-RV sessions are above-average winners (halving 79 of them cost ₹1.33L for ₹2k of DD relief).
* Only *skipping* beats the floor (a skipped session pays no fees): the pre-declared cluster-stop variants — after k consecutive losses, skip the next 2 sessions — give **k=2: DD −₹33,991 (17.0%) at −₹7.3k/yr; k=3: DD −₹34,728 (17.4%) at +₹2.5k/yr, Pareto-dominating the base book** (+₹14.5k PnL, Sharpe 2.98). Pre-declared descriptive variants, not tuned post-hoc; adoption as operating policy requires a new pre-registration and still fails the 8% bar.
* Risk-budget restatement: E011 at 1 lot needs **₹6,40,930** capital to fit an 8% DD budget (₹4,34,100 with the k=3 stop; ₹4,00,950 for the E015 combined book). On ₹2L the naked delta-hedged straddle's 8% ceiling is unreachable by wings (E016), fractional sizing, or cluster stops — remaining levers: fewer hedge orders (rebalance threshold), hybrid passive exits (E014), E015 pairing, or a larger capital base.

---

### Phase 6: Shadow Execution & Production Gatekeeper
*Objective:* Validate strategy execution in real time without capital risk using the live WebSocket/REST capture infrastructure.

#### 6.1 Shadow-Trading Protocol (Zero Capital)
1. **Collector Activation ([e009](file:///d:/Code/dhanopt/experiments/e009_wall_capture)):**
   * Ensure `capture_chains.py` is actively logging 60-second full OPTIDX snapshots via Windows Task Scheduler.
   * **Capital Concurrency Check (E015):** before any session where both books signal, confirm combined broker RMS margin ≤ usable ₹1.82L. Under the conservative bound, 10 of 44 historical overlap days breached — if confirmed live, E013 takes the slot (higher Sharpe, lower DD).
2. **Virtual Ledger:**
   * Signals generate virtual paper orders timestamped to the millisecond.
   * Marks are recorded from the next available 60-second snapshot (`top_bid_price` / `top_ask_price`).
3. **Pre-Live Acceptance Gate (Gate 0 Protocol):**
   A strategy graduates to live execution with 1 lot only if it meets all three conditions:
   * **Minimum OOS Sample:** $\ge 60$ live-monitored shadow trading sessions.
   * **Realized Drift:** Live execution slippage $\le 1.25\times$ the modeled slippage in backtest.
   * **Zero Breaches:** Maximum daily drawdown limit (₹2,500) never breached.

---

## 4. Execution Schedule & Milestones

| Timeline | Phase | Deliverable | Exit Gate |
|---|---|---|---|
| **Day 1 (Immediate)** | **Phase 1** [DONE] | Execute Overnight Fund pledge via broker portal. | Margin confirmed active in terminal; collateral yield accrual begins. |
| **Weeks 1–2** | **Phase 2** [DONE] | Build `e011_vrp_delta_hedge`: RV vs IV calculation + 5-min delta-neutral simulator. | Backtest report: Net +₹7.43L, Sharpe 2.85, PF 3.99; Max DD ₹51k motivates Phase 4 defined wings. |
| **Weeks 3–4** | **Phase 3** [KILLED ❌] | Build `e012_skew_ratio`: Parameterize 2021–2026 skew and test 1×2 ratio structures. | Decisively failed all 3 kill bars (PF 0.13, -₹98.8k). Ratio debit bleed confirmed. |
| **Weeks 5–6** | **Phase 4** [DONE / CANDIDATE 🎯] | Build `e013_0dte_pin`: Replay 576 sessions in `e008` testing 12:30 PM Iron Fly vs Breakout. | Net +₹4.14L, Net EV +₹2,148/trade, PF 9.41, WR 83.9%, Max DD ₹11.9k (5.97%). Candidate for e009 live chain fills. |
| **Weeks 7–8** | **Phase 5** [DONE / GATE FAILED ❌] | Build `core/execution/maker.py` + e014 three-arm TCA (TAKER / MAKER-AON / HYBRID) on both validated books. | Maker fails Gates 2–3 decisively (EV −53%/−62% vs taker; aggregate 27%/22% < 60%). Taker entry retained; 1.5 pts/leg slippage assumption validated as non-optimistic. Passive exits → Phase 6 shadow. |
| **Post-Phase 5** | **Analyses E015 + Spread Sweep** [DONE] | Book composition (E011 × E013) + spread-width sensitivity on the frozen books. | Combined DD 16.0% (still >8% — E011 tail binding); 10 overlap-day margin breaches under conservative bound; breakevens 13.0/10.7 pts/leg. Phase 6 must verify fly RMS margin before stacking both books. |
| **Post-Phase 5** | **E016 Wings Test** [KILLED ❌] | VRP-gated iron fly (adaptive 1σ wings, all other E011 rules frozen). | All 3 gates fail: DD −₹2.03L (101.5%), EV −₹536, total −₹1.57L. Wings cap the tail, not the drawdown. Remediation moves to regime sizing / session stops. |
| **Post-Phase 5** | **E017 Regime Sizing + Risk Budget** [KILLED ❌] | Half size on elevated-RV (trailing-60 75th pct) or after 2 losses; fixed-fraction + cluster-stop risk budget on the frozen book. | Sizing fails: DD 25.6% → 25.4%, EV +₹2,023 (intact). No fixed fraction reaches ₹16k (min −₹40.5k @ f≈0.52 — flat-fee floor). Only skip-rules move it: k=3 cluster stop → DD 17.4% at +₹14.5k vs base. 8% ceiling needs ₹4.3L+ capital or fewer orders. |
| **Month 3+** | **Phase 6** | Run Shadow-Trading Engine alongside active [e009](file:///d:/Code/dhanopt/experiments/e009_wall_capture) collector. | 60 consecutive sessions without risk breach before 1-lot live deployment. |

---

## 5. Non-Negotiable Engineering Invariants (The Rulebook)

1. **Information Time Horizon ($t-1$ Rule):** Any signal generated on bar $t$ must execute at bar $t+1$ Open. Same-bar execution is banned.
2. **No Data Snooping:** Hyperparameters (e.g. VRP threshold, rebalancing trigger) must be frozen *before* walk-forward evaluation. No sweep optimization.
3. **All Metrics Net of Zerodha Friction:** Never evaluate gross PnL. Every reported rupee must net:
   * Brokerage: ₹20/order leg.
   * STT: 0.1% on option sell value (post-Oct 2024 SEBI mandate).
   * Exchange turnover (0.0505%) + SEBI turnover (₹10/Cr) + Stamp duty (0.003%) + GST (18%).
   * Slippage: Minimum 1.5 points per option leg, 0.5 points per futures hedge.
4. **Lot Size Compliance:** Every backtest must query `experiments/common/lots.py` to use the regulatory lot size active on `trade_date` (75, 50, 25, 75, or current 65).
5. **Fail-Closed Architecture:** If options chain data, volatility estimators, or quote freshness are missing, the system outputs `NO TRADE`. It never interpolates synthetic winning defaults.
