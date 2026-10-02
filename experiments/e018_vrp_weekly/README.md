# E018 — Contract-Identity VRP: Weekly 3–7 DTE Hold-to-Expiry Iron Condor

**Contract & Pre-Registration:** [PREREG.md](PREREG.md) — frozen 2026-10-02 before any code and before any run.
**Question:** With the VRP signal re-derived on the contract that actually exists on the trade
date, does a wide defined-risk condor held 3–7 DTE to expiry have positive net expectancy?

---

## 1. Verdict — ❌ FAIL (3 of 6 gates)

| # | Gate | Bar | Observed | Status |
|---|---|---|---|---|
| 1 | Capacity | ≥ 30 trades | **141** (24.7/yr) | ✅ PASS |
| 2 | Edge | EV ≥ +₹400 and PF ≥ 1.5 | **EV −₹435, PF 0.82** | ❌ FAIL |
| 3 | Drawdown | ≤ 15% of ₹2L (₹30,000) | **−₹96,835 (48.4%)** | ❌ FAIL |
| 4 | Contract identity | 0 mismatches | **0 across 141 trades** | ✅ PASS |
| 5 | Friction resilience | net > 0 at 2.0× slippage | **−₹92,306; breakeven 0.51 pts** | ❌ FAIL |
| 6 | No roundness | WR ≤ 85% | **63.8%** | ✅ PASS |

```
Total net PnL   -61,306      Sharpe (0.38)      Avg friction  ₹861/trade
Win rate         63.8%       Profit factor 0.82  Max DD  -96,835 (48.4%)
Wins   n=90  mean +3,022
Losses n=51  mean -6,535
```

The honest reading: **the contract-identity bug is fixed, and the edge does not survive the fix.**
E011's +₹7.43L was an artifact. Kailash's Option 1 is tested here on its own terms and it does not pay.

## 2. What the fix actually did (the part that matters)

The corrected signal is measurably a different animal from E011's:

| | E011 (convicted) | E018 (contract-correct) |
|---|---:|---:|
| mean signal IV | 0.476 | **0.163** |
| max signal IV | 1.929 | **0.473** |
| sessions IV > 1.00 | 35 | **0** |
| sessions IV ≥ 0.60 | 68 | **0** |
| mean tenor credited | 0.95 days | **3.98 days** |
| roll-day enrichment in signal | **2.55×** | 1.00× (none — roll days no longer select) |

The enrichment row is the proof the diagnosis was right: E011's gate fired 2.55× more often
on days where its own inversion had broken. Correcting the instrument collapsed that
selection entirely. `test_no_degenerate_iv_in_the_dataset` and
`test_front_expiry_roll_is_not_yesterdays_contract` pin both facts shut.

## 3. Why it fails — the mechanism, measured

**A 3–7 DTE condor's credit is too thin to carry 8 leg-orders of round-trip friction.**

Mean entry credit is **75 pts** on a mean lot of 55 — about ₹4,100 gross. Friction is
**₹861/trade** (₹160 brokerage + STT + exchange + GST + 8 × 1.5 pts slippage = ₹660 in
slippage alone). The breakeven half-spread is **0.51 pts/leg**: the book needs a 0.51-pt
spread to merely cover costs, and real NSE weekly spreads on 3–7 DTE wings run several
points wide. Gate 5 fails not because the edge is fragile but because the edge is
*smaller than the transaction*.

This is the same wall E017 hit from the other side — but diagnosed correctly. E017 found
that ₹83,166 of flat per-order fees was a floor no position-size could cross. E018 finds the
same floor from a *shorter* holding period: E011's book was intraday and still paid ~₹912
of friction per trade, and E018 pays ₹861 while capturing a week's theta instead of a day's.

Second contributor: **the loss distribution is right-skewed against the credit.** 51 losing
trades average −₹6,535 against 90 winners averaging +₹3,022 — a 2.2:1 loss/win ratio that a
63.8% hit rate cannot overcome. Wide wings capped the tail (no trade lost beyond its
arithmetic maximum) but truncated recovery exactly as E016 found. The VRP here is not
absent, it is *mispriced relative to the cost of harvesting it*.

## 4. Two bugs found and fixed during the run

Both were caught by sanity bars declared in the PREREG, not by inspection:

1. **Stale expiry-day marks (−₹104,000 of phantom loss).** The bhavcopy `close` on expiry
   day is a last-trade price — measured at 0.30 on options that expire at 0.00 — and on
   **34 of 141** trades it implied an exit debit *larger than a condor's arithmetic
   maximum*, which is impossible. `settle_price` is no help: it is populated with the
   futures price, not the option's. Fix: at expiry, time value is exactly zero, so the
   mark is **intrinsic against the futures close**. Marking correctly moved the book from
   −₹165,194 to −₹61,306. Net changed; verdict did not.
   `test_exit_marks_respect_condor_arithmetic_max` now fails if this ever returns.

2. **Contract identity in the replay** (the mirror of E011's bug). The replay was
   initially shifting `target_expiry` with the rest of the signal, which would have named
   *yesterday's* contract. Which expiry is front on day t is a public-calendar fact
   knowable at t-1, so it is deliberately not shifted. `_identity_ok` re-derives it from
   the trade date's own partition on every trade — 0 violations, and that is gate 4.

Both are in the README because a run that only reports its P&L teaches nothing about why
the number is what it is.

## 5. What survived, and what a future attempt would need

**Survives (reusable, signal-independent):**
- **The contract-identity engine** ([volatility_fixed.py](volatility_fixed.py)) — clean IV
  distribution, roll-day enrichment eliminated, 1,410 sessions, 3 minutes to rebuild.
  This is the fix E011 needed and should not be thrown away with the strategy.
- **The hold-to-expiry mark path** — entry at day-t EOD close, settle at expiry-date EOD
  close, marked on real bhavcopy prices with no Black-Scholes reconstruction anywhere.
  Unlike E011, no P&L here depends on a model's opinion of a price.
- **The impossibility audit** — a condor's arithmetic maximum is a closed-form bound. Any
  backtest whose marks violate it has a pricing bug. Cheap, general, should be a house test.
- **The E011 conviction itself**, now written into the leak registry so it cannot be
  quietly inherited a third time.

**Dies:** the VRP as a *weekly defined-risk condor* on this signal. Not the VRP as a
phenomenon — the corrected signal shows a real, stable IV/RV spread (mean VRP 0.048,
p80 hurdle 0.075). It dies as a *tradeable* structure: 3–7 DTE weekly credit cannot pay
8 leg-orders of round-trip friction, and no position sizing fixes that (E017's floor, one
day shorter). A future attempt would need a structure with a higher credit-to-fee ratio —
longer holds (2–4 weeks, where credit is a larger multiple of the same flat fees), or
index futures/ETF vol products with per-contract costs rather than per-leg option costs.

## 6. Artifacts & Tests

* `artifacts/volatility_daily.parquet` — contract-identity-correct daily IV/RV/VRP frame.
* `artifacts/weekly_daily.csv` — 141 trades, leg marks, volumes, identity flag.
* `artifacts/verdict.json` — the six gates, slippage curve, breakeven spread.
* 17 tests in [test_e018.py](test_e018.py): contract identity (roll rejection, front-expiry
  selection, per-trade re-derivation), IV plausibility, t-1 no-lookahead, condor arithmetic
  bounds, era-correct lots, fail-closed leg handling, and the DTE band.
