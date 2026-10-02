# E019 — Systematic Cash Momentum: Nifty ETF + Midcap Cross-Section, Daily-Rebalanced

**Pre-Registration Protocol — frozen 2026-10-02 before any download and before any backtest.**

Kailash's Option 2, taken on its own terms: a daily-rebalanced momentum engine on free
EOD data, tested where "free EOD data has genuine predictive power without friction decay."
The prior work in this repo ([E018](../e018_vrp_weekly/README.md), e001–e017) is entirely
options and every strategy family is dead. This is a different asset class, a different
data source, and a different cost structure — nothing here inherits a prior experiment's
numbers, which is exactly why it is worth testing.

---

## 1. Hypothesis (one paragraph, falsifiable)

- **Claim:** Time-series/cross-sectional momentum on liquid NSE cash equities survives
  realistic Indian retail-equity friction (STT 0.1% delivery both sides, exchange + SEBI
  + stamp + GST, brokerage, and slippage) at **monthly** rebalance, and does **not**
  survive at **daily** rebalance. The friction-decay boundary is the thing being measured.
- **Mechanism (why should this edge exist?):** Cross-sectional momentum in Indian
  midcaps is one of the most robust anomalies in the published literature (it is also the
  most shorted and the most crowded). It earns because intermediate-term winners keep
  winning for behavioral/attention reasons, and because NSE midcap breadth is dominated
  by a retail base that underreacts to firm news. A monthly rebalance harvests weeks of
  drift for a few round trips of cost; a daily rebalance pays the same round trip for one
  day of drift, and the anomaly's payoff-to-turnover ratio is far too low to survive it.
- **Why it might be an artifact:** survivorship (a universe built from *today's* index
  members back-fills delisted names and is the single most common way momentum backtests
  lie); the ETF leg is pure beta with no cross-section and could be a disguised
  time-series-timing claim; and 5.7 years contains one enormous bull market, so a
  long-only book can look skillful on beta alone.
- **Honest prior:** **medium for the monthly leg, low for the daily leg.** The anomaly is
  real and heavily replicated internationally; the Indian midcap variant specifically has
  out-of-sample support. Against that: the sample is one regime, the universe is small and
  illiquid, and no momentum book in this repo has ever been tested.

## 2. Information set (the leak question, answered first)

- **What does the decision see?** `t-1` — signals are computed from closes up to and
  including day t-1, and all orders are filled at day **t+1's** close (the next available
  observable print after the signal is complete). No same-bar fills.
- **Fill rule:** signal computed after the t-1 close; rebalance executes at the t close.
  A momentum rank formed on t-1's closes cannot be filled at t-1's close.
- **Leak-registry entry to add:** `experiments/e019_momentum/engine.py`, `info="t-1"`,
  `live=True`.
- **Survivorship control (declared as a design constraint, not a validation step):** the
  universe is built from the **union of all symbols that appear in the cash bhavcopy on
  any day in the sample**, filtered only by *point-in-time* liquidity (median turnover over
  the trailing 252 sessions ending t-1, computed from data that existed then). No
  "current Nifty Midcap 150 members" list is used anywhere, because a static membership
  list applied backwards is exactly how momentum backtests manufacture returns. Symbols
  that stop trading simply stop qualifying.
- **If day-t anything:** it is a research instrument, not a strategy. Say so here and stop
  pretending.

## 3. Data class (match the data's clock to the signal's clock)

- **Source + freshness:** NSE free daily cash-market bhavcopy (`BhavCopy_NSE_CM_*.csv.zip`),
  `https://archives.nseindia.com/content/cm/`. Verified reachable (HTTP 200) and verified
  to carry `TckrSymb, FinInstrmTp, OpnPric, HghPric, LwPric, ClsPric, PrvsClsgPric,
  TtlTradgVol, TtlTrfVal` per symbol per day — close, previous close, volume and turnover
  value for the entire listed universe. Stamped at the 15:30 close, so a t-1 file is fully
  settled before t's open. This is the *same* publisher and the *same* EOD convention as
  the FO partitions already in `data/historical/`, so it is one data class, not two.
- **Completeness ceiling:** the CM bhavcopy carries every listed NSE security, so the
  universe is the exchange's, not a vendor's. It does **not** carry delisted names, and it
  carries no fundamentals, no index membership history, and no corporate-action-adjusted
  close. **Prices are raw, not adjusted** — splits and bonuses therefore show up as
  artificial price gaps. Mitigation declared now: momentum is computed on a
  return series that is screened for absurd single-day moves (>50% absolute, which is
  either a split or a bad print) and such rows are dropped from BOTH the signal and the
  trade, never silently carried.
- **Observability-vs-fill check:** 100% by construction. A daily EOD close is observable
  for every listed name, and the fill is the next day's close. There is no fill window to
  miss and no data class that can see the signal but not the fill — the e008 failure mode
  is structurally impossible here.
- **Marks validation plan:** the marks *are* the bhavcopy closes. Two independent checks,
  both pre-declared: (1) `PrvsClsgPric` in day t's file must equal `ClsPric` in day t-1's
  file for the same symbol — any disagreement is a data-integrity failure that voids the
  run; (2) every traded symbol must have non-zero `TtlTrfVal` on both the entry and exit
  day, reported as a coverage number.

## 4. Kill criteria (numeric, one-sided, written now)

Any one failing kills the experiment. Fail-only. Estimated from what is already known about
NSE cash markets and this repo's cost model, not from the run.

| # | Bar | Value | Why this number |
|---|-----|-------|-----------------|
| 1 | Universe | ≥ 100 symbols pass the point-in-time liquidity filter on ≥ 90% of rebalance dates | Below this, equal-weighting 10 midcaps is a concentrated bet, not a cross-section, and the Sharpe is a single-stock story. |
| 2 | Capacity | ≥ 60 rebalances per leg over the sample | Monthly over ~5.7y is ~68; daily is ~1,400. Both legs clear 60 if the data is complete. |
| 3 | Edge (monthly leg — the primary) | Net CAGR **> 15%** and net Sharpe **≥ 0.8** and net max DD **≤ 30%** | 15% CAGR is roughly the index's own long-run drift; beating it net is the claim. Sharpe 0.8 is the conventional "usable after costs" bar and is *lower* than any bar used elsewhere in this repo, deliberately, because cash friction is honest and small. |
| 4 | Edge (daily leg — the secondary) | Reported, **not gated** | The daily leg exists to MEASURE the friction-decay boundary, not to pass. It is pre-declared as descriptive: if daily nets less than monthly, that is the expected result and is a finding, not a failure. It is gated only on capacity (#2). |
| 5 | Friction resilience (monthly) | Net positive at **2.0×** modeled total cost | 2× is the standard robustness multiplier; 23× was this sandbox's options bar. |
| 6 | No illusion | Monthly leg's net Sharpe must exceed the **equal-weight buy-and-hold of its own universe** by ≥ 0.2 | This is the anti-beta gate and the most important one. A long-only book in a bull market can show 20% CAGR and 1.5 Sharpe purely from market exposure; the only way to know the signal earned anything is to beat the same-universe, same-cost, no-signal benchmark. |

**Verdict protocol:** README written verdict-first with this table. Gate 6 is treated as
the primary criterion — a strategy that beats nothing is not a strategy.

## 5. Sanity bars (run on every result, pre-declared here)

- Suspicion scales with roundness: Sharpe > 2 on a monthly-rebalanced ₹2L book earns a
  specific audit before belief.
- Friction and slippage measured, not assumed: state the full per-side cost stack and the
  breakeven holding period in trading days.
- Corporate-action screen: >50% absolute daily move = suspected split, dropped and counted.
- n < 10 rebalances means unjudgeable — report it as unjudgeable.
- The benchmark comparison (gate 6) is computed with the **same cost model** as the
  strategy, so the comparison is like-for-like.

## 6. Cost & machinery (the lazy-senior check)

- **Does this need to be built at all?** Rungs 2–4 all hold: there is no cash-equity price
  store in this repo (`data/` holds only FO bhavcopy + 5-min index candles), no
  cross-sectional ranking machinery, and no equity cost model. The one thing that exists
  and is worth reusing is the *shape* of the machinery: `experiments/common/leak_registry.py`
  (declare the information set), the pre-registration discipline, and the parquet-partition
  layout that `core/feeds/bhavcopy.py` already uses.
- **Reuse inventory:** partition layout + download-then-cache pattern from
  `core/feeds/bhavcopy.py`; verdict-script pattern from
  [e018/run_e018.py](../e018_vrp_weekly/run_e018.py); the leak registry.
- **Incremental cost:** ~1 day. The download is ~1,415 daily files of ~150 KB (about
  200 MB total); the engine itself is a cross-sectional rank plus a cost model, both of
  which are short. **No new dependency** — `requests` is already used by the repo's
  existing fetcher.
- **Self-terminating?** Yes. Six frozen criteria decided by a verdict script, with gate 6
  as the primary and the daily leg explicitly non-gated.

## 7. Amendments (append-only, dated)

- 2026-10-02: frozen before any download and before any backtest. No amendments.

## 8. Verdict (filled after the run; never before)

- **Result:** `<PASS | FAIL on criterion N>` with the numbers against each bar.
- **What died / what survived:** `<name what a future attempt would need>`
