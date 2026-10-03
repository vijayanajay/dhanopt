# PREREG — e028: The Expiry-Encoding Bug, and What It Does to the Surviving Candidate

**Frozen 2026-10-03, before any code in this directory exists.**

---

## 1. Why this experiment exists

A brainstorm asked a question no gate in this repo had asked: *the 64 sessions
e026 validated — how were they selected?*

`e026_realmark_audit/audit_realmark.py` resolves the front expiry to a
`datetime.date` and then filters the chain with `df["expiry"] == str(fe)`. The
`expiry` column on disk has **two encodings**: `04-Feb-2021` in the legacy NSE
format and `2025-01-02` in the post-July-2024 UDiff format. `str(date)` is
always ISO. So on every partition written in the legacy format the filter
matches **zero rows**, `leg_close` returns `None` for all four legs, and
`debit_real` is `None` — which §5.5's fail-closed rule correctly interprets as
`NO TRADE` and silently drops the session.

Measured before any code was written (throwaway diagnostic, since deleted):

| Partition | Raw `expiry` | `str(parse_date(...))` | Equal? |
|---|---|---|---|
| `fo_20210104` | `04-Feb-2021` | `2021-02-04` | **False** |
| `fo_20230103` | `02-Feb-2023` | `2023-02-03` | **False** |
| `fo_20240701` | `04-Jul-2024` | `2024-07-04` | **False** |
| `fo_20250102` | `2025-01-02` | `2025-01-02` | True |
| `fo_20260925` | `2026-09-29` | `2026-09-29` | True |

**356 of 576 wall sessions return an empty front chain.** Every session before
2024 returns one, for a formatting reason rather than a market one.

`e018` does not have this defect: it parses into a real `exp_dt` column and
compares dates. `e026` and `e027` both do, in their own copies of the loader.

**The specimen.** e026's `load_front_chain`. The disease: a *typed* value
compared against a *string*. The typo class: silent. The host: the
fail-closed rule, which cannot tell "this session had no data" from "this
lookup was wrong", so it obeyed §5.5 perfectly and hid the bug inside a
correct behaviour.

**Why it matters more than a bug.** Three published claims rest on the sample
this bug produced:

1. e026's verdict `SURVIVES REAL MARKS`, +₹61,843, EV +₹966, PF 16.67.
2. e027's slippage ladder and its **2.64 pts/leg breakeven**, on which
   `actionplan.md` §4 gates the entire Phase 6 go/no-go.
3. `RETROSPECTIVE.md` §5.11's three load-bearing facts — *"no pre-July-2024
   session has a valid mark at all"*, *"the valid-mark share rises monotonically
   38.7% → 56.4% → 70.0% by year (era selection, not a random sample)"*, and
   *"91% of the PnL comes from 2025"*.

Claim 3 deserves emphasis. Those three facts are cited in the retrospective as
reasons to believe the number **less**. They are true statements about the
output of a string comparison. The suspicion was correct; the evidence for it
was not what it appeared to be.

---

## 2. Hypothesis

**H1.** The 64-session sample is a *formatting* artifact, not a market sample.
Correcting the lookup to compare parsed dates recovers every session's mark, and
the recovered sample spans 2021–2026.

**H2.** The recovered sample contains sessions the published book never saw, and
they are systematically worse. If the published edge is era-concentrated
rather than era-masked, the correction moves EV down.

Both may be true at once, and the experiment is designed so that either can be
the answer without contaminating the other. **This experiment is not a patch.
It is a hypothesis test, in the form e018 and e026 established.** A fix tuned to
reproduce +₹61,843 on the full sample would be a worse fix.

---

## 3. Design — freeze everything, move one thing

The variable under test is **how the chain is looked up**. Nothing else moves.

| Component | Status |
|---|---|
| e013's selection walk (expansion ratio ≤ 0.65, bars 0–39) | **frozen** — imported from e026, which already reproduced e013 to the paisa |
| Entry bar 40, exit bar 71, wing width 150, strike step 50 | **frozen** |
| Lot eras (`common/lots.py`) | **frozen** |
| Friction model (`e013_friction`, verbatim) | **frozen** |
| Real bhavcopy close marks, front expiry re-derived per trade | **frozen** |
| Expiry-day exits excluded (e018's stale-last-trade defect) | **frozen** |
| **The chain lookup** | **THE ONLY VARIABLE** |

### Arms

| Arm | Loader | Purpose |
|---|---|---|
| **A — control** | `load_front_chain_string_eq`, e026's loader verbatim | must reproduce e026's +₹61,843 on n=64, and e027's 2.64 pts/leg breakeven, to the paisa |
| **B — corrected** | `load_front_chain`, expiry parsed to a `date` and compared as a date | the finding |
| C — slippage ladder | both arms, 0.05 → 3.0 pts/leg | e027's ladder re-derived on both samples |
| D — era cut | both arms, net by calendar year | tests H2 directly, and re-tests §5.11 |

**Gate 0 is the one that matters.** If Arm A does not land on e026's number to
the rupee, the experiment is void and nothing in it may be believed — the same
disposition e018 and e020 adopted.

Arm A is why the defective loader is *kept* in the codebase, renamed
`load_front_chain_string_eq` and labelled with its conviction. A control that
cannot be run is not a control.

---

## 4. Gates — frozen before the first run

| # | Gate | Bar | Consequence of failure |
|---|---|---|---|
| 0 | Control reproduces predecessor | Arm A = **+₹61,842.51**, n=64, to the paisa; Arm C = breakeven **2.64** pts/leg | **Experiment void.** Nothing reported. |
| 1 | Contract identity | 0 mismatches: front expiry re-derived per trade from the trade date's own partition | Void |
| 2 | Arithmetic impossibility | 0 violations of the closed-form iron-fly bound on trustworthy marks | Void |
| 3 | **Coverage** | ≥ 95% of selected sessions yield a usable real mark | **Verdict is `INCONCLUSIVE`.** The sample is still format-selected and no edge number may be quoted. |
| 4 | **Edge at a realistic fill** | Arm B EV ≥ **+₹400** at 2.0 pts/leg over the full sample | **Candidate is DEAD at a realistic fill.** Strike the number; Phase 6 does not start. |
| 5 | **Era robustness** | No calendar year supplies > **60%** of net PnL | **Candidate is UNSTABLE.** Survives, but not as a book to deploy; record the concentration and require a live re-test before capital. |
| 6 | Round-trip identity | `parse_date(s)` round-trips and no lookup silently returns empty on a partition that exists | Void — this is the invariant going forward |

Gates 3–5 are deliberately *not* the gates e026 used. e026's Gate 2 was
"real-mark coverage ≥ 50%", and the defective lookup scored **54.9%** against
it — a pass, by 4.9 points, on a number that was measuring a bug. A bar that a
bug can pass is not a bar.

**Gate 4 is the decision gate.** The plan is currently written around +₹327 EV at
a 2.0 pts/leg fill. If Arm B lands below +₹400 on the full sample, the correct
action is to stop, not to search for a better threshold.

**Gate 5 encodes §5.11 as a test rather than a caveat.** The retrospective
already says a book whose PnL comes from one year is not a tested book. This
makes it executable.

---

## 5. What this experiment may not do

- It may not move the slippage assumption. The ladder is reported at several
  points; the verdict is read at 0.75 (what the engine charges) and 2.0
  (realistic), both frozen here.
- It may not re-select. The expansion ratio, the wing width and the IV source
  are e013's. e026's Arm D showed selection on e011's **void** IV disagrees
  with selection on the corrected IV on 82 of 193 sessions; that is a separate
  experiment and must not be folded in here. If it is, it is labelled.
- It may not report a number without its control arm.
- It may not be re-run with a different bar.

---

## 6. One-sidedness

There is no intraday option price on disk, so the 12:35 entry credit remains
Black-Scholes in every arm, exactly as in e026. **This correction can only make
the book look better or worse than published — it cannot flatter it.** It moves
no signal, no timing, no cost model.

---

## 7. Deliverables

- [ ] PREREG frozen (this file, before any code).
- [ ] The loader fixed at the shared root (`core/feeds/bhavcopy.py`), not in a
      experiment, so a fourth consumer cannot inherit it.
- [ ] The defective loader retained, renamed, and labelled with its conviction.
- [ ] `audit_encoding.py` with both arms.
- [ ] `test_e028.py`: round-trip identity, non-empty coverage, control
      reproduction, identity, impossibility.
- [ ] A registry row in `experiments/common/leak_registry.py`.
- [ ] `actionplan.md` and `RETROSPECTIVE.md` amended with whatever the verdict
      is — including the amendment to §5.11's three facts if they are artifacts.

---

## 8. Amendments (added after the first run, and why)

Both are logged here rather than quietly edited into §4, because a gate bar that
moves after the data is in is the exact thing this repository exists to catch.
Neither moves a bar; one names a denominator, one adds a gate.

### Amendment 1 — gate 3's denominator

The bar was written as "≥95% of the **selected** sessions yield a real 4-leg
mark". Read literally that is unreachable and wrong: 193 sessions were selected,
but 64 of them are selected *to exit on their own expiry day*, and an expiry-day
exit has no mark by construction — e013 closes the fly on the expiry print, not
on a later close. The literal figure is **66.84%**, and it is reported in the
verdict rather than hidden.

The denominator that measures what the gate is for — the input's coverage — is
the **markable** sessions: 193 − 64 = **129**. Coverage against those is
**100.00%** (129/129). Both numbers ship.

This is not a moved bar, it is a bar that named the wrong population on the one
topic this whole experiment is about. It is still the last substantive risk in
the repository: *the one input nobody was checking could be checked, and when
someone finally checked it, four years of it was empty.*

### Amendment 2 — gate 7 added after the run

`audit_encoding.py` came back clean on gates 0–6. That deserved suspicion rather
than a write-up, so one more check was added: a stale-early mark prints **low**,
and a pin fly entered on a low mark books a *cheap* fly — the error runs in the
book's favour, which no gate above could see.

Gate 7, non-voiding, evidence only: no leg may close more than 4 ticks below
intrinsic measured against the **same-expiry** NIFTY futures close. (Front-month
futures is wrong here: it is a different expiry, and it manufactured 162 false
breaches on the first attempt.) **52 of 772 legs** breach, on legs carrying
10–78M contracts — stale final prints on deeply liquid contracts.

Flooring every breaching leg at intrinsic (`intrinsic_audit.py`) costs
**₹3,578** at 0.75 pts/leg and **₹3,578** more at 2.0. Not load-bearing: gate 4
already fails without it. But it is the direction that matters — the only
correction in this experiment that made the book *worse* than both the published
number and the un-corrected corrected-number, and it was found last.

### What was not amended

Gate 4 (EV ≥ +₹400/trade at 2.0 pts/leg) and gate 5 (no year >60% of PnL) are
untouched and both **fail**. The verdict is read at the frozen bars.
