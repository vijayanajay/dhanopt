# E019 — Systematic Cash Momentum: Nifty ETF + Midcap Cross-Section, Daily-Rebalanced

**Contract & Pre-Registration:** [PREREG.md](PREREG.md) — frozen 2026-10-02 before any download and before any backtest.
**Question:** Does momentum on free NSE EOD data survive realistic Indian delivery friction, and where is the friction-decay boundary?

---

## 1. Verdict — ❌ FAIL (3 of 6 gates), and the premise of Option 2 is falsified

| # | Gate | Bar | Observed | Status |
|---|---|---|---|---|
| 1 | Universe | ≥ 100 liquid names on ≥90% of dates | median **1,553**, min 1,200 | ✅ PASS |
| 2 | Capacity | ≥ 60 rebalances per leg | monthly **54**, daily 1,123 | ❌ FAIL |
| 3 | Edge (monthly, primary) | CAGR > 15%, Sharpe ≥ 0.8, DD ≤ 30% | CAGR **3.1%**, Sharpe **0.34**, DD **−55%** | ❌ FAIL |
| 4 | Edge (daily) | reported, not gated | CAGR **12.0%**, Sharpe **0.87**, DD **−52%** | ✅ PASS |
| 5 | Friction resilience (monthly) | positive at 2.0× cost | CAGR **+0.7%** | ✅ PASS |
| 6 | **No illusion (PRIMARY)** | Sharpe beats same-universe equal-weight by ≥ 0.2 | **−0.81** (0.34 vs 1.15) | ❌ FAIL |

| Leg | Net CAGR | Sharpe | Max DD | Costs paid |
|---|---:|---:|---:|---:|
| Cross-sectional, monthly | 3.14% | 0.34 | −55.4% | ₹28,812 |
| Cross-sectional, daily | 12.01% | 0.87 | −51.7% | ₹148,029 |
| **Equal-weight benchmark (no signal)** | **21.29%** | **1.15** | **−24.2%** | — |
| NIFTYBEES time-series | 7.56% | 0.63 | −16.9% | ₹6,261 |

## 2. The headline: Option 2's premise is wrong

Kailash's Option 2 was chosen because "free EOD data has genuine predictive power
**without friction decay**." The friction half of that is false, and the run measures it
directly:

* **Daily rebalancing beat monthly, 3.8×** (12.0% vs 3.1% CAGR) — the *opposite* of the
  friction-decay prediction.
* Monthly costs were **₹28,812 over 4.5 years on a ₹2L book** ≈ ₹6,400/yr ≈ 3% of capital.
  They cannot be the binding constraint.
* Daily paid **₹148,029** and still earned nearly 4× more. Turnover costs were real,
  measured, and irrelevant.

So the reason to leave options for cash equities is **not** that friction decays the edge.
If momentum worked here, it would have worked far better daily. The reason to leave is
different, and this run found it.

## 3. Why momentum loses: two measured mechanisms

**Momentum IS predictive at the decile level.** Pooled across 53 rebalances / 71,080
name-periods, rank vs next-21-day return:

| Bucket | Mean 21d return |
|---|---:|
| Bottom decile | +0.58% |
| Middle half | +1.41% |
| Top decile | **+3.24%** |

Top-minus-bottom is **+2.66% per 21 days**. A genuine, sizeable, free-data anomaly. It
simply does not survive being traded as a top-20 portfolio:

1. **The extreme tail is not the decile.** Top-20 is the top 1.3% of a ~1,550-name universe,
   not the top 10%. Extreme 12-month winners in Indian midcaps are small, illiquid and
   mean-reverting; the decile average hides that. The book paid a **−55% drawdown** against
   the benchmark's −24%.
2. **The winners die, and the diagnostic hides it.** Measured 21-day survival: all ranked
   names **0.44%** dead, **top-20 holdings 1.51%** dead — **3.4× worse**. Any study that
   computes forward returns only over names still printing drops exactly those losers,
   which is why the raw decile spread looks so good. The backtest keeps them in the basket
   at 0% return, which is what a real holder experiences.

**The honest conclusion:** momentum is real in the cross-section and *not tradeable* at
this concentration in this universe. The tradeable version — long top decile, ~150 names,
liquidity-capped — was not tested here and is the obvious next cell.

## 4. Bugs found and fixed (all pre-declared sanity bars)

1. **Corporate actions (453 events, 397 symbols).** The bhavcopy is unadjusted, so a 1:1
   bonus prints as a −50% day — a momentum screen reads it as a crash and drops the name at
   exactly the moment it might qualify. That is a bias *against* the large caps that lead
   the factor. Fixed by back-adjusting the history at clean split/bonus ratios (1:1, 1:2,
   1:3, 1:4) and leaving everything else alone. RELIANCE's phantom −49.8% becomes +0.98%.
2. **`pct_change()` forward-fills NaN by default.** On a sparse 6,475-symbol panel this
   invents 9.19M fake "returns" and makes every corporate-action test meaningless. Every
   call now passes `fill_method=None`.
3. **A positional-argument bug cost the first two runs.** `run_backtest`'s 6th positional
   parameter is `cost_mult`; passing `start, end` positionally became a **295× cost
   multiplier over a one-iteration window**, producing a clean-looking "CAGR −1.0". All call
   sites are keyword-only now.

The NSE archive also publishes under two URL schemes (legacy `historical/EQUITIES/...`
pre-Aug-2024, `content/cm/...` after); [download_cash.py](download_cash.py) probes both per
date, which is why the panel is continuous across 2021–2026.

## 5. What survives

* **The price store.** 1,420 sessions × 6,475 symbols, 215 MB, free, idempotent downloader,
  survivorship-safe by construction (union of all trading symbols, no index-membership list
  applied backwards). Reusable for any cross-sectional equity study.
* **Point-in-time liquidity** ([precompute_liquidity](engine.py)) — trailing-252 median
  turnover, computed once instead of 1,100 times.
* **Corporate-action back-adjustment**, which every momentum or mean-reversion study on raw
  Indian EOD data needs and almost nobody does.
* **The anti-beta gate (6).** It is the only reason this experiment produced a decision. A
  long-only book in a bull market earns 21% CAGR and 1.15 Sharpe from beta alone; without
  gate 6 the momentum legs would have looked like a modest success.
* **The friction-decay measurement itself** — a reusable negative: Indian cash-equity
  momentum turnover costs do not bind at 21-session rebalance.

## 6. Honest notes on the run

* **Gate 2 failed honestly.** The liquid window is 4.46 years, not 5.7, because 12-1
  momentum needs a full year of warm-up before the first tradeable signal. I pre-declared
  ≥ 60 monthly rebalances and got 54. The bar was not moved.
* The sample is one regime (2022–2026, dominated by a strong midcap bull run). The
  equal-weight benchmark's 21% CAGR is a bull-market number, not a through-cycle estimate;
  the *relative* verdict (momentum loses by 0.81 Sharpe) is the durable finding.
* Turnover is computed as half the L1 weight distance; names that stop trading are carried
  at 0% return rather than force-closed, which is conservative and is the mechanism in §3.2.

## 7. Artifacts

* `data/cash/` — 1,420 partitioned daily bhavcopy parquet files (215 MB, free).
* `artifacts/verdict.json` — the six gates, both legs, zero-cost and 2× cost variants, benchmark.
* `artifacts/cross_monthly_daily.csv`, `cross_daily_daily.csv` — daily equity curves.
* `test_e019.py` — no-lookahead, point-in-time universe, corporate-action, cost-model tests.