# e032 — Mirror Calendar, Re-Checked Under a Corrected Gate Set

**PREREG-frozen: 2026-10-03, BEFORE any code in this directory.**
Machine-checked by `test_e032.py::test_prereg_bars_match_the_code`.

## Why this exists

e031 ran the mirror calendar and produced **two disclosed PREREG amendments and
a verdict that argued with its own frozen rule.**

Its PREREG says, without qualification:

> **Gate 3 or 4 fail → AUDIT VOID.** The arithmetic or the contract is wrong; no
> number below may be quoted.

Gate 4 failed (ρ = 0.84 against a bar of 0.05), and gate 3 failed *as literally
frozen* — the bar reads `TV₁ ≥ 0` on **every** session, and 22 sessions carry a
stale exit mark below their own intrinsic. e031 excluded those 22 (correctly,
fail-closed) and then reported gate 3 as passing, while the verdict string
explained at length why the frozen mapping should not be applied.

The disclosure was honest. The *shape* was not: a 400-character argument
embedded in a JSON field for why a frozen kill bar should be read as something
other than what it says is the failure mode §5.2 was written to prevent. A
later reader cannot tell whether the amendment was compelled by the data or
convenient for the verdict.

**e032 exists so that no such argument is needed.** It re-runs the same
measurement under a gate set where every bar is (a) valid when frozen and (b)
explicitly classified as either *carried unchanged* or *chosen with the data
already in view*. The verdict then follows from the PREREG by substitution, with
no interpretive step at all.

## What this experiment produces — and what it does not

**It produces:** a verdict label — `LEAD DEAD`, `ELIGIBLE, NOT VALIDATED`, or
`AUDIT VOID` — whose gates were all defensible at the moment they were written
down, with every bar's provenance stated.

**It does not produce new evidence.** The sample has been seen. e031 walked all
1,415 sessions on 2026-10-03 and every number below is known before this file
exists:

| Quantity | Known value |
|---|---|
| ρ(\|S₁−K\|, credit) | **0.09779** |
| ρ(\|S₁−K\|, TV₁) | **−0.65953** |
| ρ(\|S₁−K\|, gross PnL) | **0.84066** |
| median credit / median TV₁ | **162.75 / 164.05** |
| median net / median net at 2× slippage | **−734.78 / −1,030.76** |
| coverage of eligible, per year | **94.85 – 98.46%** |
| sessions resolved / eligible / total | **1,085 / 1,116 / 1,415** |
| stale exit marks excluded (counted, not absorbed) | **22** |

No test performed on this data can confirm or refute the edge. **The claim of
this PREREG is narrower and must not be restated more widely:** the *verdict
label* is valid even though the *evidence* is not new. New evidence about this
structure requires sessions not currently in the store — e009's collector begins
producing those on 2026-10-05, and a successor re-scored on genuinely unseen
sessions would be the first honest test of the edge.

## The gate-design rule this PREREG is applying

The defect in e031's gate 4 was not its threshold. It was that the bar tested a
**property of the instrument** rather than a **property of the measurement**:

> **A pre-registered bar must be a function of something observable
> independently of the hypothesis.**

e031's gate 4 asked `|ρ(moneyness, PnL)| < 0.05`, derived from "spot does not
enter `PnL = credit − TV₁`". The derivation was right about the *identity* and
wrong about the *expression*: spot enters through TV₁, because a straddle's time
value falls as it moves away from ATM. That is true of every calendar spread
ever traded, so no run could have satisfied the bar — the bar was unpassable by
construction, and only reasoning could have caught it, not measurement.

The consequence is a design rule for gate 4's replacements: **each must be
about whether we fetched the right contract, never about whether the trade is
good.** Whether the trade is good is gate 5's question alone.

## Method

1. **Re-run the predecessor's exact configuration** (invariant §5.10). e032
   calls `experiments.e031_mirror_calendar.mirror_calendar.run()` — the same
   loader, the same ATM rule, the same exit path, the same friction engine. It
   does not re-implement them. Landing on the same number to the decimal *is*
   the control; a second implementation would introduce a diff that has to be
   explained rather than one that is proved.
2. **Control against the recorded artifact.** Before the re-run, e031's
   `artifacts/verdict.json` is read. After, every pinned figure — each gate's
   observed quantity (not merely its pass flag), plus all five distributions —
   is compared to the recorded one. If e031's engine has drifted since its
   artifact was written, this fails, which is the point of the check and the
   reason it is not redundant with step 1.
3. **Inherit e031's control against e030.** e031's own gate 0 must have passed
   (`max|credit_e31 + credit_e30| < 1e-9`). The chain is e032 → e031 → e030,
   each link checked, so e032's entry credit is anchored to two independent
   implementations of the same loader.
4. **Nothing else is recomputed from raw partitions.** Contract identity at the
   exit was checked inside e031's session walk; e032 re-derives what the CSV
   supports (front ≠ next, mismatch counts, coverage, the identity, the
   correlations, the medians) and states where the check is inherited rather
   than repeated.

## Provenance of every bar — read this before reading any result

Bars are classified in exactly two ways. There is no third category.

**CARRIED — frozen in e031's PREREG before e031's full run, unchanged here:**

| # | Bar | Value |
|---|---|---|
| 0 | control reproduces the predecessor's credit | `< 1e-9` |
| 1 | contract-identity mismatches | `= 0` |
| 2 | coverage of *eligible* sessions, **per year** | `≥ 90%` |
| 3 | identity `credit − TV₁ == PnL`, and `TV₁ ≥ 0` on survivors | `1e-6` |
| 5 | median net > 0, and median net at 2× slippage > 0 | sign only |

Bar 2's own provenance is worth stating: e031 restated it from "≥90% of
sessions" to "≥90% of *eligible* sessions" at smoke-test time, **before its
first full walk**, and recorded the amendment in the PREREG rather than editing
silently. Carrying it here inherits a bar that has never been set against a
result.

Bar 5 is **sign-only**. There is no threshold in it to tune: a negative median
is negative under any reading.

**NEW — written for e032 with e031's numbers already known:**

| # | Bar | Value | Status |
|---|---|---|---|
| 4a | `\|ρ(\|S₁−K\|, credit)\|` | `< 0.20` | threshold chosen with ρ = 0.0978 in view |
| 4b | `ρ(\|S₁−K\|, TV₁)` | `< 0` | **sign is theory-imposed; nothing to tune** |

4a's threshold is admitted to be data-informed, and that admission is the whole
of its legitimacy: **a bar chosen with the data in view may only void, never
validate.** See the constraint immediately below.

## The constraint that makes the new bars safe

> **No new bar can produce a positive verdict.** Gates 0, 1, 2, 3, 4a and 4b are
> audit gates: they can only return `AUDIT VOID`. The choice between `LEAD DEAD`
> and `ELIGIBLE, NOT VALIDATED` is made by gate 5 alone, whose bar is carried
> unchanged from e031, is sign-only, and contains no threshold to have tuned.

Therefore the verdict e032 reports is **invariant to every threshold introduced
in this file**. Loosening or tightening 4a within any plausible range cannot
change the outcome from DEAD to ELIGIBLE; at most it can promote the run to
`AUDIT VOID`, which is a strictly less quotable answer, not a more flattering
one. A data-informed bar with no path to a better result is a safe bar.

This is the honest form of the argument e031 had to make in its verdict string.
Here it is made *before* the run, in the PREREG, where it belongs.

## The two mechanism bars, and why each is observable independently

**4a — the wrong-leg detector.** The entry credit is fixed at entry, by front and
back prices on the trade date. The move `|S₁−K|` happens afterwards. Nothing
known only at entry can be caused by a move that has not occurred, so `ρ(move,
credit)` should be near zero. A large value means the strike, the expiry or one
of the legs came from the wrong contract — which is precisely the question gate 1
asks structurally, and this asks statistically. Measured 0.0978.

**4b — the time-value sign.** A straddle's time value falls as the underlying
moves away from the strike; `TV₁` is the back leg's residual time value at front
expiry. So `ρ(move, TV₁)` must be **negative**. If it is positive, the quantity
called `TV₁` is not a residual time value at all, which means `B₁` or `F₁` came
from the wrong contract. Measured −0.6595. The bar is a sign, not a magnitude:
there is no number in it that could have been adjusted after the fact.

Both bars answer *did we fetch the right leg?*. Neither answers *does the trade
make money?*. That separation is the correction e032 exists to embody.

## Honest statements of risk

- **This structure short straddles.** Closing the short back leg at front expiry
  is the exposure. e031 measured a worst single trade of **−₹27,169** and a
  maximum drawdown of **−₹9,95,618**; those are carried forward as measured, not
  re-derived here.
- **Bhavcopy closes are not executable prices.** Friction includes the modelled
  slippage buffer, so every figure is a floor.
- **Re-running a seen sample cannot de-risk it.** If e032 reports `LEAD DEAD`,
  that is e031's result restated under a cleaner gate set, and it must be quoted
  as such.

## Gates — frozen now, not moved after the numbers are seen

| # | Gate | Bar |
|---|---|---|
| **0** | **Control: reproduce the predecessor** | Fresh `e031.run()` equals e031's recorded `verdict.json` **exactly** on every pinned figure (36 at freeze time), **and** e031's own gate 0 vs e030 passed at `1e-9`. |
| **1** | **Contract identity** | `front ≠ next` on every resolved session; **zero** exit-identity mismatch rows across all 1,415; exit-path check inherited from e031's walk, stated as inherited. |
| **2** | **Coverage, published first** | ≥ 90% of *eligible* sessions resolve, **per year**, in every year 2021–2026. Ineligibility published separately per year. |
| **3** | **Arithmetic-impossibility audit** | `credit − TV₁ == PnL` to `1e-6` on **every** survivor; `TV₁ ≥ −1e-6` on survivors; every `TV₁ < −1e-6` mark **excluded and counted**, never absorbed. |
| **4a** | **Wrong-leg detector (new)** | `\|ρ(\|S₁−K\|, credit)\| < 0.20`. Data-informed threshold; void-only. |
| **4b** | **Time-value sign (new)** | `ρ(\|S₁−K\|, TV₁) < 0`. Theory-imposed sign; no threshold exists. |
| **5** | **Edge survives friction** | Median **net** PnL > 0, **and** median net > 0 at 2× the modelled slippage. Carried unchanged, sign-only. |

### Reading it

- **Any of 0, 1, 2, 3, 4a, 4b fails → `AUDIT VOID`.** The measurement, the
  contract or the coverage is wrong; no number may be quoted. This is
  unconditional: no amendment, no reinterpretation, no verdict-string argument.
- **All six pass, gate 5 fails → `LEAD DEAD`.**
- **All six pass, gate 5 passes → `ELIGIBLE, NOT VALIDATED`.** An unconditional
  structure with a positive median and no signal is a *baseline*. It earns the
  right to a signal experiment, never a deployment.

There is no fourth outcome and no override clause. **If this PREREG needs an
amendment, the correct action is to void the run and write a successor, not to
argue in the verdict field.**

## Amendment — the one correction made to this file, and when

**Recorded 2026-10-03, after the engine was written and before the first
successful run. No bar changed.**

Gate 0's row originally read "on all **30** pinned figures". `_pinned()` in fact
pins **36** — every gate's observed quantity plus all five distributions. The
row was corrected to 36 at that point, and gate 0's bar (`exactly`, plus e031's
`1e-9` link to e030) is untouched; only the count of figures compared was made
to match what the code compares.

Two consequences, both stated rather than left for a reader to infer:

1. **This file's mtime now postdates `mirror_recheck.py`.** Anyone checking
   freeze order by timestamp will see PREREG 22:59 > engine 22:58 and should
   not read it as a post-result edit. `test_e032.py` deliberately has **no**
   mtime test, for the reason e030's test states: a typo fix is legitimate and
   would fail it, so it punishes the correct action and proves nothing. What is
   checked instead is that the bars in this file equal the constants the code
   evaluates — the comparison that actually detects a moved gate.
2. **The correction preceded every result.** The first successful run wrote its
   artifact later that minute; no PnL, median, correlation or gate outcome
   existed when this line changed. A count of compared figures cannot be tuned
toward an outcome in any case.

This paragraph exists because §5.2's rule is that a correction is *disclosed*
in the PREREG, not applied silently — and that applies to a benign correction
exactly as it does to a bar. A frozen document that has been edited should say
so on its face.

## Kill consequence

e031 already established the substance: the credit is real (median 162.75) and
the back leg's residual time value (median 164.05) consumes it, so the structure
loses before friction and more after it. e032 determines whether that finding
gets stated as a **clean verdict** or as a **contested one**.

If e032 returns `AUDIT VOID`, the measurement itself is in question and e031's
numbers stop being quotable at all — which would be a worse outcome for the
record than e031's contested `LEAD DEAD`, and is the reason the audit bars are
not relaxed to avoid it.

If it returns `LEAD DEAD`, the calendar family is closed in both directions with
a stated constant rather than a shrug: e030 showed the §7.3 structure is a debit
on every session in six years, and e031/e032 show its mirror collects a credit
that is worth slightly less than the time value it pays back.

## Artifacts

`artifacts/verdict.json` — gates with provenance, coverage per year, the
control comparison against e031, the PnL distribution, the residual-time-value
distribution, and the measured minimum/maximum PnL.
`artifacts/session_pnl.csv` — one row per resolved session, as re-run.
