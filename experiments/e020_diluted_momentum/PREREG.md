# E020 — Diluted Cross-Sectional Momentum: Long the Top Decile, Liquidity-Capped

**Pre-Registration Protocol — frozen 2026-10-02, before any code and before any run.**

Directly downstream of [E019](../e019_momentum/README.md), which failed and left a specific
unresolved question. E019 measured:

* momentum IS predictive in the cross-section (top decile +3.24% vs bottom +0.58% per 21
  days, a +2.66% spread, pooled over 71,080 name-periods);
* a top-20 book captured almost none of it — net CAGR 3.1% vs 21.3% for the equal-weight
  universe, excess Sharpe **−0.81**, drawdown −55%;
* the two mechanisms were concentration (top-20 is the top 1.3% of ~1,550 liquid names, not
  the top decile) and **death**: top-20 holdings stopped printing 1.51% of the time within
  21 days versus 0.44% for the universe.

So the signal is real and the *portfolio* was the mistake. E020 tests the diluted book that
E019's own mechanism analysis points to.

---

## 1. Hypothesis (one paragraph, falsifiable)

- **Claim:** Long an equal-weighted top **decile** of the point-in-time liquid universe
  (~150 names), rebalanced monthly, captures enough of the decile spread to beat a
  same-universe equal-weight book on risk-adjusted return, with a drawdown in the same
  region as that benchmark rather than the −55% of the concentrated book.
- **Mechanism (why should this edge exist?):** Intermediate-term winners keep winning
  because Indian midcap breadth is retail-dominated and underreacts to firm news. Dilution
  does not weaken that mechanism — it removes the two ways concentration destroyed it:
  idiosyncratic blow-ups from single-name tail risk, and the 3.4× excess death rate of
  extreme-momentum micro/small caps, whose forced exits a real holder cannot time.
- **Why it might be an artifact:** (a) the whole cross-section is long-only, so the
  "momentum" book may simply be a beta expression that the equal-weight benchmark also
  captures — gate 5 exists precisely to catch that; (b) the decile spread in E019 was
  measured on names still printing 21 days later, and top-decile names also die, just less
  often — gate 6 measures that directly rather than assuming it; (c) one regime.
- **Honest prior:** **medium.** Better than E019's, because the mechanism argument is
  specific and the diagnostic evidence is strong. But E019's benchmark beat every momentum
  variant tried, and Indian midcap momentum has a well-earned reputation for crashing in
  reversal regimes — which this sample barely contains.

## 2. Information set (the leak question, answered first)

- **What does the decision see?** `t-1`. Momentum is ranked from closes through t-1;
  the liquidity filter uses a trailing 252-session median ending t-1.
- **Fill rule:** signal after the t-1 close; basket traded at the **t close**; earns the
  t+1 return. A rank formed on t-1's closes cannot be filled at t-1's closes.
- **Leak-registry entry to add:** `experiments/e020_diluted/engine.py`, `info="t-1"`,
  `live=True`.
- **Survivorship control:** unchanged from E019 and re-verified — the universe is the union
  of every symbol that trades in the bhavcopy on any day of the sample, filtered by
  point-in-time liquidity only. **No index-membership list is applied backwards.** A name
  that stops trading stops qualifying, and names that die inside a holding period stay in
  the basket earning 0%, which is what a real holder experiences and which E019 showed is
  materially punitive (1.51% of top-20 names).
- **If day-t anything:** it is a research instrument, not a strategy. Say so and stop.

## 3. Data class

- **Source:** the existing E019 store — 1,420 sessions × 6,475 symbols of free NSE daily
  cash bhavcopy, corporate-action back-adjusted (453 events, 397 symbols). No new fetch.
- **Freshness:** daily EOD stamped 15:30; a t-1 file is fully settled before t's open.
- **Completeness ceiling:** raw (not vendor-adjusted) prices — handled by the E019
  back-adjuster. No fundamentals, no index history, no borrow data.
- **Marks validation:** marks are the bhavcopy closes, already validated in E019
  (`PrvsClsgPric` chain, non-zero turnover coverage).
- **NEW ceiling declared here — the liquidity cap is decorative at this size:** a 1%-of-ADV
  position limit on ~150 names at ₹2L implies ~₹1,333 per position against a ₹5-crore ADV
  floor, i.e. roughly **40× headroom**. The cap is implemented and its binding-ness is
  *reported*, but no claim will be made that it saved anything at this capital. If it never
  binds, that is the expected and honest outcome, and it is reported as such rather than
  dressed up as a risk control.

## 4. Kill criteria (numeric, one-sided, written now)

Bars estimated from E019's frozen results and the store already on disk — not from the run
about to happen.

| # | Bar | Value | Why this number |
|---|-----|-------|-----------------|
| 1 | Capacity | **≥ 45** monthly rebalances | E019 measured the liquid window precisely: 12-1 momentum needs a 252+21-session warm-up, leaving 1,146 sessions ≈ **54** rebalances over 4.46 years. E019 failed gate 2 at 54 against a 60 bar that its own warm-up made unreachable — this bar is set to what the design can actually deliver, and stated as such rather than moved after the fact. |
| 2 | Breadth | **≥ 100** names held on **≥ 90%** of rebalance dates | The entire hypothesis is dilution. A book that averages 100+ names is the test; anything less is E019's concentrated book wearing a different name. |
| 3 | Edge | Net CAGR **> 0** and net Sharpe **≥ 0.8** | Deliberately modest next to E019's 15% CAGR bar: the benchmark is a bull-market number, and the *relative* test is gate 5. |
| 4 | Risk | Max DD **≤ 35%** | The benchmark's is −24% and E019's top-20 book's was −55%. A diluted book that cannot get inside 35% has not fixed the concentration problem. |
| 5 | **No illusion (PRIMARY)** | Net Sharpe exceeds the **same-universe equal-weight book by ≥ 0.15** | Same gate E019 failed (−0.81). A long-only decile book must beat the index it is drawn from, net of identical costs, or the signal earned nothing. |
| 6 | Death rate | Top-decile 21-day death rate **≤ 1.5×** the universe rate | Tests E019's measured mechanism directly. Universe rate is 0.44% (measured); the bar is ≤ 0.66%. If concentrated momentum still kills its holdings 1.5× more often, dilution has not addressed the real problem. |
| 7 | Friction | Net CAGR positive at **2.0×** cost | Same robustness multiplier as E019. |

**Diagnostic, pre-declared and explicitly NOT gated:** a **long-top-decile /
short-bottom-decile** book. Indian retail cannot short equities at scale, so this is not a
tradeable strategy and will not be scored as one — but it is the cleanest measurement of the
anomaly itself, because it strips market beta. If the long-short spread is fat while the
long-only book loses to its benchmark, the finding is "real anomaly, unusable as a long-only
retail book" — a genuinely different and more useful conclusion than "no edge".

## 5. Sanity bars (run on every result, pre-declared here)

- Suspicion scales with roundness: Sharpe > 2 on a monthly ₹2L book earns an audit.
- Drawdown is reported against the benchmark's, not against zero.
- Zero-cost and 2×-cost variants reported alongside baseline, as in E019.
- The liquidity cap's binding-ness is reported as a number (headroom factor), not asserted.
- E019's exact configuration (top-20, monthly) is re-run inside E020 as a **control**, to
  confirm this engine reproduces −0.81 excess Sharpe. An engine that cannot reproduce its
  predecessor's number is not measuring momentum.

## 6. Cost & machinery (the lazy-senior check)

- **Does this need to be built at all?** Rungs 2 and 3 hold. The store, the liquidity
  filter, the momentum rank, the cost model and the benchmark all exist from E019. The only
  new code is: top-N-by-fraction instead of top-N-by-count, and the ADV cap.
- **Reuse inventory:** everything in [e019/engine.py](../e019_momentum/engine.py).
- **Incremental cost:** ~2 hours including the run.
- **Self-terminating?** Yes. Seven frozen criteria + one control + one diagnostic.

## 7. Amendments (append-only, dated)

- 2026-10-02: frozen before any code and before any run. Bar 1 is set from E019's measured
  warm-up (54 achievable rebalances), disclosed here so it cannot be mistaken for a bar
  chosen after seeing a 54. No further amendments.

## 8. Verdict (filled after the run; never before)

- **Result:** `<PASS | FAIL on criterion N>` with the numbers against each bar.
- **What died / what survived:** `<name what a future attempt would need>`