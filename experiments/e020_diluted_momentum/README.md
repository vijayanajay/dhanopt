# E020 — Diluted Cross-Sectional Momentum: Long the Top Decile, Liquidity-Capped

**Contract & Pre-Registration:** [PREREG.md](PREREG.md) — frozen 2026-10-02 before any code and before any run.
**Question:** Does the momentum effect that [E019](../e019_momentum/README.md) proved real, but could not trade, survive dilution to the top decile?

---

## 1. Verdict — ❌ FAIL (2 of 7), on the two gates that mattered

| # | Gate | Bar | Observed | Status |
|---|---|---|---|---|
| 1 | Capacity | ≥ 45 monthly rebalances | **54** | ✅ PASS |
| 2 | Breadth | ≥ 100 names on ≥90% of days | median **135**, min 104, **100%** of days | ✅ PASS |
| 3 | Edge | CAGR > 0 and Sharpe ≥ 0.8 | CAGR **24.8%**, Sharpe **1.19** | ✅ PASS |
| 4 | Risk | max DD ≤ 35% | **−32.7%** | ✅ PASS |
| 5 | **No illusion (PRIMARY)** | Sharpe beats same-universe equal-weight by ≥ 0.15 | **+0.04** (1.19 vs 1.15) | ❌ FAIL |
| 6 | **Death rate** | top-bucket death ≤ 1.5× universe | **1.87×** (0.81% vs 0.43%) | ❌ FAIL |
| 7 | Friction | positive at 2.0× cost | CAGR **+22.2%** | ✅ PASS |

**The control passed exactly.** This engine re-ran E019's top-20 monthly configuration and
reproduced **excess Sharpe −0.81**, the published figure to the decimal. An engine that
cannot reproduce its predecessor is not measuring momentum; this one can, so the rest of the
numbers are trustworthy.

| Configuration | CAGR | Sharpe | Max DD | Excess Sharpe vs EW |
|---|---:|---:|---:|---:|
| Top-20 (E019, control) | 3.1% | 0.34 | −55.4% | **−0.81** |
| **Top decile, ~135 names (E020)** | **24.8%** | **1.19** | **−32.7%** | **+0.04** |
| Equal-weight benchmark | 21.3% | 1.15 | −24.2% | — |
| Long-short *diagnostic* (net, ungated) | 3.7% | 0.58 | −14.0% | — |

## 2. Three findings, in order of how much they matter

**1. Dilution was the whole problem — and it fixes almost everything except alpha.**
Going from top-20 to top-decile moved net CAGR from **3.1% → 24.8%** and cut drawdown from
**−55% → −33%**. E019's conclusion that "momentum is real but not tradeable at this
concentration" was correct, and this is the fix it pointed at.

**2. But 100% of it is beta.** The diluted book beats the equal-weight universe — the exact
same names, same costs, same days — by **0.04 Sharpe**. That is not an edge, it is noise. The
book is a slightly better-constructed way to own the market, and gate 5 exists precisely so
that "24.8% CAGR!" cannot be mistaken for skill. A reader who saw only the CAGR column would
call this a success; it is not one.

**3. The anomaly is real, and it is not a long-only trade.** The pre-declared long-top-decile
/ short-bottom-decile diagnostic earns **3.7% net, Sharpe 0.58** — a genuine, measurable
momentum spread. Note how far that is from the **11.1% it first printed**: my first version
of that diagnostic subtracted `cost/CAPITAL*0`, i.e. reported it gross. Costing it properly
cut it by two-thirds. Friction is not what killed E019's momentum book — but on a
market-neutral book with 100% turnover each rebalance, it is most of what is left.

## 3. Gate 6: dilution halved the death rate but did not fix it

| | Universe | Momentum bucket | Ratio |
|---|---:|---:|---:|
| Top-20 (E019) | 0.44% | 1.51% | **3.4×** |
| **Top decile (E020)** | 0.43% | 0.81% | **1.87×** |

Concentration was indeed the cause — dilution cut the excess death rate by 48%. But momentum
names still stop trading **1.87× more often** than the universe, above the 1.5× bar, and the
universe rate is essentially unchanged (0.44% → 0.43%). Some of what E019 attributed to
"extreme momentum micro-caps" is actually just momentum in general: selecting winners
selects fragile balance sheets. No weighting scheme fixes this — it is a property of the
signal, not of the portfolio.

## 4. Notes, corrections, and what was honest

* **Bar 1 was set before the run from E019's measurement, not after seeing 54.** E019 failed
  a 60-rebalance bar that its own 252+21-session warm-up made unreachable. That bar was
  disclosed as wrong in E019's README; E020 sets 45 and discloses in §7 of the PREREG that
  it is set to what the design can deliver. It is not a bar that was slipped after the fact.
* **The ADV cap did not bind, and is reported as such.** Median headroom was far above 1× on
  every position: at ₹2L across ~135 names, each position is ~₹1,480 against a 1%-of-ADV
  ceiling of ~₹500,000. The cap is implemented and its non-binding-ness is a *number in the
  verdict JSON*, not a claim that it protected anything.
* **Two bugs caught mid-run, both by pre-declared sanity bars:** the long-short diagnostic
  reported gross-of-cost (11.1% → 3.7% once fixed), and `pct_change()` forward-fill from
  E019 was carried forward correctly this time.
* **One regime.** The benchmark's 21.3% CAGR is a 2022–2026 midcap bull number, not a
  through-cycle estimate. The *relative* verdict — momentum adds 0.04 Sharpe over simply
  owning the universe — is the finding that survives that caveat; the absolute CAGRs should
  not be carried forward.

## 5. What survives

* **The control-reproduces-predecessor pattern.** Running E019's exact configuration inside
  E020 and getting −0.81 to the decimal is the strongest single piece of evidence in this
  repo that a backtest engine measures what it claims. It should be standard practice.
* **Dilution as the lever.** Top-20 → top-decile is a repeatable +21.7pp of CAGR and a 23pp
  drawdown improvement from one parameter. Any concentrated equity factor book in this repo
  should default to a fraction of the universe, not a count.
* **The death-rate measurement** (gate 6) is a reusable diagnostic that no standard backtest
  reports, and it caught a property of the signal rather than of the portfolio.
* **The anti-beta gate (5)** did its job again: it turned a book that looks like a 24.8%
  winner into a measured +0.04-Sharpe beta expression.

## 6. What a future attempt would need

Not a better momentum specification. The signal is measured, the dilution is measured, and
the answer is that a long-only Indian midcap momentum book **is the index**. The live cells
are (a) market-neutral momentum, where 3.7% net Sharpe 0.58 exists and needs a borrow
arrangement this repo cannot model honestly, and (b) a genuinely orthogonal signal — the
beta decomposition says further equity-price work on the same cross-section is unlikely to
pay.

## 7. Artifacts

* `artifacts/verdict.json` — seven gates, control, death rates, long-short diagnostic.
* `artifacts/diluted_monthly_daily.csv` — daily equity curve, 1,123 sessions.
* Reuses [e019/engine.py](../e019_momentum/engine.py) — no new data was fetched.