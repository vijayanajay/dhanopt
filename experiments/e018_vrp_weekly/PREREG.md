# E018 — Contract-Identity VRP: Weekly 3–7 DTE Hold-to-Expiry Iron Condor

**Pre-Registration Protocol — frozen 2026-10-02 before any code and before any run.**

This experiment exists because [E011](../e011_vrp_delta_hedge/) was convicted of a
**contract-identity bug** (audited 2026-10-02, pre-run, on frozen artifacts). E011 read
the ATM straddle of the expiry nearest to **t-1** and then priced the **t** trade with
that expiry's IV *and that expiry's tenor*. The contract tradable on day t is the
expiry nearest to **t**. Whenever t-1 was itself an expiry day these are different
contracts, and the published signal was a bisection artifact (mean IV 0.476, max 1.929;
67 of 293 sessions with IV >= 0.60, 35 above 1.00; mean tenor credited 0.95 days
against a real 4.71). E011's +7,43,572 is void; E015/E016/E017 inherit the defect and
are void-pending.

E018 rebuilds the signal on the contract that actually exists on the trade date, and
tests it on the structure Kailash proposed: a weekly 3-7 DTE defined-risk book held to
expiry.

---

## 1. Hypothesis (one paragraph, falsifiable)

- **Claim:** The variance risk premium is real, but E011 measured it on the wrong
  instrument. Re-deriving IV from the ATM straddle of the expiry nearest to the trade
  date, and harvesting it with a wide defined-risk iron condor held 3-7 DTE to expiry,
  produces positive net expectancy that survives friction and a slippage stress.
- **Mechanism (why should this edge exist?):** Index option buyers pay an insurance
  premium, so E[IV] > E[RV] by construction. A defined-risk condor sold when the
  VRP is in the top of its own trailing distribution harvests that premium as theta
  over a week, with the loss bounded by the wings — no delta hedging, no hedge churn,
  no naked gamma. The wide-wing structure is the point: E016 showed wings bleed a
  *continuously rebalanced* book because the wings surrender premium the hedging
  needs. A held-to-expiry condor does no hedging, so that objection does not transfer.
- **Why it might be an artifact:** the exact bug that faked E011. Second candidate:
  the 80th-percentile hurdle is a rolling quantile of the signal itself, so a regime
  shift manufactures "expensive" days. Third: the condor earns on volatility *falling*,
  and the EOD bhavcopy mark may be a stale last-trade price on illiquid wing strikes.
- **Honest prior:** **low-medium.** E011's only honest sub-population (the 135 sessions
  whose contract identity was already correct) ran at 80.7% win rate — but that
  population was *selected by* the bug, so it is not independent evidence. The VRP is
  textbook and the family has one prior attempt whose instrumentation was broken.
  Nothing in this repo has ever held an options position overnight to expiry
  ([brd.md](../../brd.md) §"Multi-day holding is prohibited"), so there is no
  prior art here at all.

## 2. Information set (the leak question, answered first)

- **What does the decision at bar t actually see?** `t-1`
- **Fill rule:** signal computed from the t-1 EOD bhavcopy, order placed on day t,
  filled at **day-t EOD close** (bhavcopy close of the tradable expiry), held to the
  **expiry-date EOD close**. No same-bar fills. A signal known at t-1 close cannot be
  filled at t-1 close.
- **Leak-registry entry to add:** `experiments/e018_vrp_weekly/replay_weekly.py`,
  `info="t-1"`, `live=True`, note recording the contract-identity invariant.
- **Contract-identity invariant (the whole point of this experiment):** the expiry used
  to price the entry must satisfy `expiry == min{e : e >= trade_date}` over the
  **trade date's own** bhavcopy partition, and the IV used to invert the signal must
  come from the **same expiry** observed in the **t-1** partition. A build that cannot
  find the ATM straddle for that exact expiry on that exact day emits `NO TRADE`. This
  is enforced by a test, not by convention.
- **If day-t anything:** it is a research instrument, not a strategy. Say so here and
  stop pretending.

## 3. Data class (match the data's clock to the signal's clock)

- **Source + freshness:** NSE FO bhavcopy EOD partitions, `data/historical/`, 1,415
  sessions 2021-01-04..2026-09. Each carries open/high/low/close/settle_price/
  contracts/open_interest for every symbol, instrument, expiry and strike. A bhavcopy
  row is stamped at the 15:30 close, so a t-1 partition is fully settled before t's open.
- **Completeness ceiling:** spot coverage is the chain's own strike ladder (~82-105
  strikes around ATM, verified across 2021/2024/2026 samples); the ATM straddle and
  +/-400-pt wings are present on every sampled day. **EOD close is a last-trade price**,
  not a quote: on illiquid wing strikes it can be stale, which flatters a mark-to-market
  mid-book exit. Wing slippage stress (§4, criterion 5) exists to price that risk, and
  the breakeven multiple is reported before any net number is believed.
- **Observability-vs-fill check:** 100% by construction. Entry and exit are both EOD
  bhavcopy closes of the same contract; there is no intraday fill window to miss. This
  is the structural advantage of a hold-to-expiry book over E011's intraday replay.
- **Marks validation plan:** the marks *are* the bhavcopy closes — the source
  [e005 marks_sweep.py](../e005_theta_condor/marks_sweep.py) certified across 246
  sessions (16 exact to the paisa, worst diff +23.5 pts on a ~161-pt credit, inside the
  breakeven). E018 adds an independent check it does not inherit: for each traded
  strike, assert the bhavcopy `contracts` (volume) is non-zero on entry and exit, and
  report the share of trades whose wing legs traded on both days. Zero-volume marks are
  counted and reported, never silently priced.

## 4. Kill criteria (numeric, one-sided, written now)

Any one of these failing kills the experiment. Fail-only. Estimated from data already
in the repo (the corrected-DTE audit, the E016/E017 cost model, `config.TOTAL_CAPITAL`),
not from the run about to happen.

| # | Bar | Value | Why this number |
|---|-----|-------|-----------------|
| 1 | Capacity | >= 30 trades over the 5.7y sample | 293 published signal sessions existed at a p80 hurdle; the corrected DTE filter (3-7 DTE) keeps a minority of those, and the p80 hurdle on the corrected series will fire on a different set. Below 30 the book cannot pay ₹20/order flat fees on 4 legs x 2 sides. |
| 2 | Edge | Net EV/trade >= +₹400 **and** PF >= 1.5, n >= 30 | ₹400 is roughly the per-trade friction of a 4-leg entry+exit (~₹150-250) plus a margin for the 8 hedges/day E011 showed a held book does *not* need. PF 1.5 is E010's bar — the last bar in this repo written for a genuinely new structure. |
| 3 | Drawdown | max DD <= 15% of ₹2,00,000 (₹30,000) | Defined-risk wings bound the per-trade loss, so 15% is reachable where the naked E011 book's 8% was not. Looser than the 8% institutional bar *because the structure changed*, and stated here so it cannot be moved later. |
| 4 | Contract identity | 100% of trades priced on the expiry nearest to the trade date; 0 trades on a mismatched expiry | This is the E011 bug. A single violation voids the experiment by construction. |
| 5 | Friction resilience | Net PnL > 0 at 2.0x modeled slippage, and positive-net breakeven half-spread reported | E011 passed 2.5x; a 4-leg weekly book pays 8 leg-orders per round trip, so 2.0x is the comparable bar. The breakeven half-spread is reported as a number, not a verdict. |
| 6 | No roundness | WR <= 85% | House rule from [PRE_REGISTRATION_TEMPLATE.md](../PRE_REGISTRATION_TEMPLATE.md) §5. A credit book above 85% is presumptively broken until the information-set audit clears it. |

**Verdict protocol:** README written verdict-first with this table; a fail is a result
and gets the same documentation as a pass. Criterion 4 is a hard veto, not a score.

## 5. Sanity bars (run on every result, pre-declared here)

- Any WR > 85% on a credit book is **presumptively broken** until the information-set
  audit clears it.
- Suspicion scales with roundness: PF > 10, "worst day positive", smooth equity.
- Friction and slippage measured, not assumed: state the per-leg cost model and the
  breakeven multiple before reading net PnL.
- Lot-era table from NSE circulars via `experiments/common/lots.py` (75/50/25/75/65),
  not memory. Rupees are not comparable across eras.
- n < 10 means unjudgeable — report it as unjudgeable, do not average your way to a story.

## 6. Cost & machinery (the lazy-senior check)

- **Does this need to be built at all?** Rungs 2 and 3 hold. The signal derivation
  (Garman-Klass RV, bhavcopy chain extraction, straddle-IV inversion) already exists in
  [e011/volatility.py](../e011_vrp_delta_hedge/volatility.py) and the pricing helpers in
  [core/pricing.py](../../core/pricing.py). Only the **contract-identity fix** and the
  **hold-to-expiry mark path** are new. No new dependency, no new fetch, no new
  simulator.
- **Reuse inventory:** `core/feeds/bhavcopy.py` (partition paths, `parse_date`),
  `core/pricing.py` (BS), `core/friction/zerodha.py` (post-Oct-2024 fee schedule),
  `experiments/common/lots.py` (era-correct lots), `core/collateral.py` (margin gate).
- **Incremental cost:** ~1 day. The corrected IV dataset re-reads partitions already on
  disk (1,415 files, no network). The replay marks EOD-to-EOD — **no intraday store
  needed**, which is why this is cheap despite being a new holding regime.
- **Self-terminating?** Yes. Six frozen criteria, one of them a hard veto, decided by a
  verdict script with no human in the loop.

## 7. Amendments (append-only, dated)

- 2026-10-02: frozen before any code, before any run. No amendments.

## 8. Verdict (filled after the run; never before)

- **Result:** `<PASS | FAIL on criterion N>` with the numbers against each bar.
- **What died / what survived:** `<the data class dies, not necessarily the hypothesis>`
