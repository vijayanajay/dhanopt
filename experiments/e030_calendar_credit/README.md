# e030 — Calendar-Spread Credit-to-Fee Pre-Check

**Contract first:** [PREREG.md](PREREG.md) — frozen 2026-10-03, **before any
code in this directory.**

## Verdict

> **PHASE 7.3 STRUCK.** The calendar spread's gross credit does not clear its
> own transaction costs, so no signal or surface fit can rescue it.

This experiment computed **no PnL**. It measured the premium difference that
would have to pay the bill. On the numbers below, that structure never pays it
— not rarely, not in a bad regime. **Never.**

## The finding

| Measure | Value |
|---|---:|
| Sessions considered / resolved | 1,415 / **1,415 (100.00%)** |
| Coverage, **per year** | 100.0% in every year 2021–2026 |
| Sessions with **positive** credit | **0 of 1,415 (0.0%)** |
| Median credit | **−175.15 pts** (−₹9,779) |
| Mean credit | −196.52 pts |
| p10 / p90 credit | −304.68 / **−116.58 pts** |
| Median round-trip friction | ₹558.78 (10.59 pts-equivalent) |
| Fraction clearing friction | **0.0%** |

`credit_pts = (front_CE + front_PE) − (next_CE + next_PE)`, i.e. sell the front
straddle, buy the back. **The p90 is still −116 points.** There is no tail, no
regime and no percentile that makes this tradeable, because the *median* is
wrong-signed by a factor of 16 against a ₹559 cost.

## Gates

| # | Gate | Bar | Observed | |
|---|---|---|---|---|
| 0 | Friction engine control | ₹160 brokerage + ₹390 slippage on 4 legs @ lot 65 | ₹160.00 / ₹390.00 | ✅ |
| 1 | Contract identity | 0 sessions where front == next | 0 of 1,415 | ✅ |
| 2 | Input coverage, published first | ≥ 90%, per year | **100.0% every year** | ✅ |
| 3 | **Credit clears costs** | median credit > 0 **and** > 50% of sessions clear | median **−175.15**, **0.0%** | ❌ |
| 4 | Cover at a realistic hit rate | median credit ≥ 3× median friction | **−17.5×** | ❌ |

Gates 0–2 passing is what makes 3–4 mean something: this is not a data failure
disguised as a negative. The input is complete, typed, and identity-checked.

## Why it is not "unlucky"

The mechanism is structural, not statistical. Indian index options carry an
**upward-sloping term structure in premium**: a one-week option holds more time
value than an ATM one-week contract expiring today. Selling the near and buying
the far therefore *pays you* ~175 points to open a position, before any signal,
before any exit, before ₹559 of costs. The §7.3 trigger (`IV_front − IV_next >
P90`) was designed to catch an *inverted* term structure. In six years of daily
data there is nothing to catch.

This is exactly the mechanism §5.5 D and §2.2 wrote down before this experiment
existed — *the credit-to-fee ratio, not the position size, is the binding
constraint* — applied here as a **pre-registration gate instead of a
post-mortem**. An hour of arithmetic replaced a month of surface-fitting code.

## Honest limitation

The §7.3 trigger is defined on **implied vol**; this measures **premium**. They
are not identical, and the distinction matters: front IV *can* exceed back IV on
a day when front *premium* is still lower, because front has less time value. So
a vol-based trigger could in principle fire on sessions where entering the trade
costs ~₹10,000 up front.

That does not rescue §7.3 — it makes it worse. A trigger that fires only when
the structure opens at a ₹10,000 debit needs a very large move to pay. But the
honest statement is: **this experiment does not measure the IV trigger, and does
not claim to.**

## A lead, deliberately not tested

The same data says the **tradeable direction is the mirror image**: buy the
front, sell the back, and the ~175-point premium difference arrives as credit.
That is the classic roll-yield calendar, and it is the *opposite* of what §7.3
proposes.

It is **not** a recommendation and **not** tested here. Selling the back month
means shorting the contract with materially more vega and time value — a
different risk profile with its own tail, and its own PnL experiment with its own
PREREG. Recorded because the next person to look at calendar spreads should know
the sign is the other way, and because a lead that is not pre-registered should
not be quietly promoted into a result.

## What this cost and what it bought

One experiment, **no PnL, 1,415 sessions, 12 tests**. In exchange the last
unblocked item on the Phase 7 roadmap is struck on arithmetic, and the program's
remaining scope is stated honestly: **Phase 1 collateral yield is the only
certified-positive flow, and every Phase 7 test is data-blocked.**

## Files

| File | |
|---|---|
| `PREREG.md` | Gates, frozen before code; bars cross-checked against the code by test |
| `calendar_credit.py` | Imports `core.feeds.bhavcopy.front_expiry` and `core.friction.zerodha.calculate_friction` — **never copies them** |
| `test_e030.py` | 12 tests: freeze check, friction control, sign convention, fail-closed legs, and the finding itself |
| `artifacts/verdict.json` | Every gate, coverage per year, credit distribution, friction breakdown |
| `artifacts/session_credit.csv` | One row per session: strike, spot, lot, credit, friction, cover |
