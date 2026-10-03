# PREREG — e027: Realized Slippage on the Restated e013 Pin Fly

**Frozen 2026-10-03, before any code in this directory exists.**

---

## 1. Why this experiment exists

e026 restated the pin harvest from +₹4,14,721 to **+₹61,843** on real option
prices. It did not touch slippage. The restated book still charges the repo's
modelled **1.5 points per option leg**, a figure inherited from e011-era
assumption and never measured.

The arithmetic in `actionplan.md` §5.5 B now reads:

```
restated EV          +₹966 / trade
modelled friction   -₹595
headroom             ₹371 / trade
  ÷ (8 leg-fills × lot 65 = ₹520 per point)  =  0.71 pts/leg of tolerance
```

**The book's entire margin of safety is 0.71 index points per leg.** Either the
real spread is comfortably below 1.5 pts — in which case the book is materially
better than restated — or it is above, in which case the only surviving
candidate in twenty-six experiments is dead. This experiment decides which, for
the cost of an afternoon, with data already on disk.

---

## 2. The measurement problem, stated honestly

**There is no bid/ask in this repo.** Confirmed by audit: e008's archive carries
one `open` print per strike and no quote; e009's collector has never run. So the
realized spread cannot be read directly. It must be **estimated from daily OHLC**,
which is a weaker instrument, and the estimate has a known bias.

Primary estimator: **Corwin & Schultz (2012)**, the standard two-day high–low
effective-spread estimator. It uses `H` and `L` over two consecutive sessions to
separate trading range from spread, specifically because a one-day high–low
range cannot tell a wide spread from a genuine intraday move — and on 0–5 DTE
NIFTY options a genuine intraday move dominates the range by an order of
magnitude.

**Its known limitation, declared up front:** Corwin–Schultz estimates the
*effective* spread, which includes price impact from consuming the book. On
strikes printing millions of contracts daily the true quoted spread is far
tighter than the effective one. **So CS is an upper bound, not an estimate.**

Therefore two bounds are reported, and the verdict must hold or fail against
both:

| Bound | Definition | Role |
|---|---|---|
| **Tight** | 1 tick = 0.05 index points per leg | structural floor; a strike cannot quote tighter than one tick |
| **Wide** | Corwin–Schultz effective spread per leg | upper bound, impact-inclusive |

The tick size is **derived from the data** (the modal granularity of observed
closes), not asserted.

**A second, independent cross-check** is required and is not optional: e026's
arithmetic-impossibility audit already proved the real 4-leg mark on these
sessions. The measured spread must be consistent in magnitude with the residual
between the Black-Scholes mark and the real close. If the two disagree by more
than 2×, the estimator is not to be believed.

---

## 3. Information set

`t-1` and `none`. This experiment produces **no strategy signal and no forward
PnL claim** — it characterises the cost of trading a signal that already exists.
It inherits e013's day-t signal and e026's `day-t / live False` declaration; it
does not make anything live-replicable.

---

## 4. Arms

| Arm | Slippage per leg | Purpose |
|---|---|---|
| **A — CONTROL** | e026's modelled 1.5 pts | Reproduces **+₹61,842.51 on n=64**. If this drifts, no verdict. |
| **B — TIGHT** | 1 tick per leg | The optimistic bound. |
| **C — WIDE** | Corwin–Schultz per leg, measured on that session's own four legs | The realistic upper bound. |

The control is the load-bearing gate, exactly as in e026. Arms B and C are run
on **identical sessions and identical marks** as Arm A — only the slippage term
changes — so every difference is attributable to slippage alone.

---

## 5. Kill criteria (numeric, fail-only, frozen before the run)

| # | Gate | Bar | Judges |
|---|---|---|---|
| **0** | Control reproduces e026 | Arm A within ₹1 of +₹61,842.51, n=64 | the audit |
| **1** | Data coverage | ≥ 90% of Arm B's leg-days carry both sessions' OHLC | the audit |
| **2** | Estimator sanity | derived tick > 0; median CS spread for ATM legs within (1 tick, 20 pts) | the audit |
| **3** | Consistency cross-check | CS magnitude within 2× of the e026 BS-vs-real residual | the audit |
| **4** | **THE KILL BAR — book survives** | **Arm C net PnL > 0** at the measured (upper-bound) spread | **e013** |

**Verdict rule.** Gates 0–3 must pass for arms B/C to speak. If they pass:

- **Arm C > 0** → `SURVIVES MEASURED SLIPPAGE`. e013's restated figure is
  conservative and the real expectancy is *higher* than +₹966.
- **Arm C ≤ 0 and Arm B > 0** → `SURVIVES ONLY AT THE TICK FLOOR`. The book
  lives or dies on a sub-point distinction that no available data can settle.
  Verdict: **unresolvable on current data**, and that is the honest finding.
- **Arm C ≤ 0** → `DEAD ON EXECUTION`. The only surviving candidate in
  twenty-six experiments is closed. Do not re-optimise the threshold.

**A gate that fails, fails. It is not moved after the result is seen.**

---

## 6. Sanity bars

- **The direction of the surprise is not evidence.** If measured slippage is
  *tighter* than modelled, that is not a discovery to celebrate; it is a
  reminder that a flat 1.5-pt assumption was never measured. §5.11.
- **Volume conditioning is mandatory.** The ±150 wings and the ATM straddle do
  not trade alike. The verdict is on the aggregate; the table shows the
  decomposition so a reader can see which leg kills it.
- **Both bounds are reported.** A single number from a single estimator is not
  a verdict.
- **No same-row self-comparison.** Arms A/B/C are marked on identical sessions
  before any statistic is taken.

---

## 7. Cost & machinery

- **New code:** one module, one test file. Reuses e026's trade list, lot eras
  and the bhavcopy loader.
- **New data:** none. `data/historical/` carries `open/high/low/close/contracts`
  for every traded leg on both the trade date and the prior session.
- **Runtime:** ~2 minutes.
- **Self-terminating:** yes. Gate 0 failing reads nothing further.

---

## 8. What this experiment cannot do

1. **It cannot measure a quoted spread.** It estimates one. CS is
   impact-inclusive and therefore biased wide; the tick floor is a structural
   floor and not a quote. The truth is between them, and this experiment's job
   is to bound it, not to pin it.
2. **It cannot validate fills.** These are *closing* prices. A book that clears
   at the EOD close may still be untradeable at 12:35. Only e009 can settle that.
3. **It cannot fix the credit mark.** e026's one-sidedness stands: the 12:35
   entry credit is still Black-Scholes.

## 9. Amendments

- 2026-10-03: initial pre-registration. No code, no artifacts here.

- 2026-10-03 (run 1) — **Gate 0 caught a sign error in the slippage-swap.** The
  first arm landed on +₹24,048 instead of +₹61,843. Cause: e013's modelled
  slippage is `6.0 * lot_size` index points over 8 leg-fills — **0.75 pts/leg**,
  not the 1.5 pts/leg this document assumed when it was written. The swap must
  add back what the engine actually charged, not what the plan says it charges.
  Recorded as gate 0b, which is **expected to fail** — the disagreement between
  `actionplan.md` §5.3 and the engine is itself a finding.

- 2026-10-03 (run 2) — **Corwin-Schultz reported a spread of ~0 on every leg.**
  Cause: `gamma` was set equal to `beta`. `gamma` must be the close-to-close
  variance; setting it to the high–low variance forces the relative spread to
  ~0 by construction and reports every leg as perfectly liquid. Fixed. This bug
  was only caught because gate 2 compares against **absolute** points, not a
  ratio — a sanity bar in advance, doing its job.

- 2026-10-03 (run 3) — **Corwin-Schultz failed gate 2 and was not rescued.**
  Median estimated spread is 1.71× the instrument's own price; 69% of leg-days
  return nothing. The PREREG declared CS an upper bound *and* warned it is
  biased wide; on this data class it is not merely biased but meaningless,
  because 0–5 DTE NIFTY ranges run 96–202% of price and revert intraday.

  **This amendment changes no kill bar on the book.** Gate 4's bar ("Arm C net
  PnL > 0") cannot be evaluated because Arm C is unmeasurable, and the
  pre-registered rule for an unevaluable bar was to report `UNRESOLVABLE`
  rather than default either way. What replaced it is a **breakeven ladder**,
  which is not a gate but a measurement: it states the exact slippage at which
  the book dies (**2.64 pts/leg**) and lets a reader apply their own belief
  about where the truth lies. The ladder reports the full range, including
  rungs below and above breakeven, so nothing is hidden by the choice of a
  single number.

  **The danger being guarded against, stated plainly:** an unmeasurable upper
  bound is not a passing grade. Reading "the wide bound could not be computed"
  as "therefore the book is fine" is the same species of error as the three
  convictions this repo has already booked — a conclusion drawn from an
  instrument that was never validated. The verdict is `UNRESOLVABLE` and it is
  recorded in the leak registry as such.

## 10. Verdict

- *Empty by design.*