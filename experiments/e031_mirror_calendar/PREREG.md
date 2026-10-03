# e031 — The Mirror Calendar: Buy the Front, Sell the Back

**PREREG-frozen: 2026-10-03, BEFORE any code in this directory.**
Machine-checked by `test_e031.py::test_prereg_bars_match_the_code`.

## Where this came from

e030 killed Phase 7.3 by measuring the calendar §7.3 proposed — *sell* the front
straddle, *buy* the back — and found **0 of 1,415 sessions** produce a positive
credit. The median was **−175.15 index points**, and the 90th percentile was
still negative. The structure is a debit on every session in six years because
Indian index options carry an **upward-sloping premium term structure**: a
longer-dated straddle always costs more.

That result points at its own mirror. If `back − front` is always positive, then
**buying the front and selling the back** receives that difference as credit —
**every session, unconditionally.**

The PREREG for e030 recorded this as a lead and explicitly declined to test it:

> *Recorded because the next person to look at calendar spreads should know the
> sign is the other way, and because a lead that is not pre-registered should not
> be quietly promoted into a result.*

This is that pre-registration. **The lead is now under test.**

## Why this is not free money — and what actually decides it

Collecting ~175 points up front is *not* profit. You are paying for something.

Write `F₀, B₀` for the front and back straddle prices at entry and `F₁, B₁` for
them at the front expiry. Then, because both straddles sit on the **same strike**:

    entry cash  = B₀ − F₀ = credit                     (you receive this)
    exit cash   = F₁ − B₁
    PnL         = credit + F₁ − B₁ = (B₀ − F₀) + F₁ − B₁

But a straddle's price is `|S − K| + TV`, and both legs share `K`, so the
directional terms **cancel exactly**:

    F₁ = |S₁ − K| + TV₁ᵉₓᵖ
    B₁ = |S₁ − K| + TV₁ᵇᵃᶜᵏ
    F₁ − B₁ = TV₁ᵉˣᵖ − TV₁ᵇᵃᶜᵏ  = −(the back leg's residual time value at
                                    front expiry), call it −TV₁

    ∴  **PnL = credit − TV₁**

Two consequences, both frozen as gates before this code exists:

1. **The PnL has no directional exposure.** Spot does not enter the expression.
   How far spot travels from the strike between entry and front expiry is
   irrelevant. This is a *pure theta-basis* bet, not a market-timing bet.
2. **`PnL ≤ credit` on every session**, with equality only if the back leg's
   residual time value is exactly zero — which cannot happen while the back
   expiry has life left. **This is the arithmetic-impossibility bound** (§5.9),
   and violating it is a pricing bug, not a tail event.

So the trade is: *does the credit you collected exceed the time value the back
leg still has when the front expires?* The entry credit clears friction by ~31×,
which is the trivial part. **The residual time value is the entire question.**

## Honest statements of risk

- **This structure short straddles.** At exit you are closing a short *back*
  straddle. The closed form bounds the loss (`PnL > −F₀` while spot is near the
  strike, and the worst case is when spot pins — exactly when the back leg holds
  the *most* time value), so it is effectively defined-risk — but it is **not**
  proven defined-risk here, and the measured minimum loss is reported, not
  assumed.
- **Holding to front expiry, not to a target.** No stop, no early exit, no
  signal. Any of those would be a separate experiment with its own PREREG.
- **No implied vol is computed**, same as e030. Premises are built from closes.
- **Bhavcopy closes are not executable prices.** Friction includes the modelled
  slippage buffer, so every figure is a floor.

## Method

1. **Sample.** Every session in `data/historical/` (1,415 partitions).
2. **Signal: none.** The structure is unconditional. Decided on **t-1's chain**,
   executed at **day-t's EOD close**, matching e018's mark-path convention.
   Information set `t-1`, live-replicable `True`.
3. **Expiry resolution** from *each* session's own partition via
   `core.feeds.bhavcopy.front_expiry` on the typed `expiry_date` column.
   Entry session resolves front/next; the **exit session is the front expiry
   date itself**, and it must resolve its own partition. Never a string compare
   (e028).
4. **ATM strike `K`** from the entry session's tightest straddle bracket — the
   same rule as e030, so gate 0 can compare the two directly.
5. **Legs:** `close` for all four entry prices and both exit prices at the **same
   strike K**. **A missing leg excludes the session, never interpolated.**
6. **Friction:** `core/friction/zerodha.calculate_friction` — imported, never
   copied. Charged once at entry and once at exit (4 legs, 8 orders).
7. **Coverage published before any result** (§5.14), broken out per year.

## Amendment to gate 2 — recorded at smoke-test time, before the full run

**Discovered on a three-session smoke test, before the first full walk and
before any PnL was computed.** 299 of 1,415 sessions (**21.1%**) have
`front_expiry == trade_date`: on an expiry day there is no future front leg, so
the calendar cannot be entered at all. Eligible coverage therefore caps at
**78.9%**, which fails the ≥90% bar as originally written.

**The original bar was measuring the wrong thing.** It was written to catch a
*data* failure — an encoding, a missing partition, a loader that resolves
nothing — and this is neither. The measurement is complete; the trade is merely
undefined on that day. Failing the gate here would report a verdict of
"AUDIT VOID" that says nothing about the data.

So the bar is restated to what it always meant: **≥90% of sessions *where the
trade is definable*, per year.** The ineligibility rate is reported separately,
per year, alongside coverage, so a reader can still see both numbers.

This is a correction to the gate's scope, made **before the result was known**
and recorded here rather than applied silently. It is exactly the kind of edit
that, if made *after* seeing a bad number, would be the failure mode §5.14
exists to prevent — hence the note rather than a quiet rewrite. The other five
gates are unchanged.

**Eligibility as measured (coverage-only, no PnL):** 1,116 of 1,415 eligible;
the front-expiry share is 21.0–21.4% in every year 2021–2026, i.e. a stable
structural property of the weekly expiry calendar, not a data artifact.

## Gates — frozen now, not moved after the numbers are seen

| # | Gate | Bar |
|---|---|---|
| **0** | **Control vs e030** | Entry credit reproduces e030's `credit` (sign-flipped) **to the paisa**, on **every session both experiments resolved** (1,085 of 1,415 — scope note below). Different experiment, same loader — if these disagree, one of them is wrong. |
| **1** | **Contract identity** | 0 mismatches. Front ≠ next at entry; the front-expiry session exists in the store; exit legs re-derived from *that* partition at the same strike. |
| **2** | **Coverage, published first** | **Amended — see the note below, dated before the full run.** ≥ 90% of *eligible* sessions resolve all six prices, **per year**. Below that, stop and report coverage only. |
| **3** | **Arithmetic-impossibility audit** | `PnL ≤ credit` on **every** session (1e-6 tolerance), and `TV₁ ≥ 0`. A violation is a pricing bug. |
| **4** | **Spot-independence** | \|Spearman ρ(\|S₁−K\|, gross PnL)\| < 0.05. The closed form says spot must not enter; if it does, an exit leg is being fetched from the wrong contract. |
| **5** | **Edge survives friction** | Median **net** PnL > 0, **and** net > 0 at 2× the modelled slippage. |

**Scope note on gate 0 — recorded 2026-10-03 after the full run, as a
clarification only. The bar is unchanged.** The row originally read "to the
paisa on 1,415 sessions", but this experiment resolves 1,085: 299 sessions are
structurally ineligible because on an expiry day there is no future front leg
(the eligibility amendment above, frozen before the run). The control can only
compare sessions **both** experiments resolved, so 1,415 was never an attainable
overlap — it was a stale session count carried over from e030, whose coverage is
100%. **Nothing about the bar changed:** still `1e-9`, still to the paisa, still
the same two independent loaders. What changed is that the row now names the
denominator the gate actually uses, and `test_e031.py` asserts `n == resolved
sessions` so the two cannot drift apart again. Recording this rather than
editing silently is §5.2's rule; a reader should know which sentences in a
frozen document were corrected and when.

### Reading it

- **Gate 3 or 4 fail → AUDIT VOID.** The arithmetic or the contract is wrong;
  no number below may be quoted.
- **Gate 5 fails → the lead is DEAD.** The credit is real but the back leg's
  residual time value eats it. That is a complete, useful answer: the sign was
  the other way, and the other way still does not clear costs.
- **Gate 5 passes → ELIGIBLE, not validated.** An unconditional structure with a
  positive median and no signal is a *baseline*. It earns the right to a signal
  experiment, never a deployment.

## Kill consequence

This is the last open lead e030 left behind. If it dies, the phase-7 arithmetic
story is closed in both directions: the §7.3 structure is impossible, and its
mirror does not clear friction. Nothing about Phase 7 changes — it remains
data-blocked either way.

## Artifacts

`artifacts/verdict.json` — gates, coverage per year, PnL distribution, the
residual-time-value distribution, and the measured minimum/maximum PnL.
`artifacts/session_pnl.csv` — one row per resolved session.
