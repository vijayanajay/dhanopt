# E029 — Pre-Registration: Does Any Slice of e013 Survive Its Own Early Era?

**Frozen 2026-10-03, before any code exists in this directory.**
Amendments in §9, if any, logged and disclosed.

---

## 1. Why this experiment exists

e028 fixed the expiry encoder and killed the book: **−₹29,082** at a realistic
2.0 pts/leg fill on the corrected **n=129** sample, breakeven **1.51 pts/leg**,
**93.0%** of PnL from 2025.

The corrected sample is the first one that has anything to say about the early
era. e026's "64 verified sessions" were the sessions the encoding bug did not
hide — all of them post-July-2024. So for four years the repo had **no measured
PnL at all** for 2021–2023, and every statement about that era (including
`RETROSPECTIVE.md` §5.11's "no pre-July-2024 session has a valid mark") was an
artifact. Now it does:

| Era | n | Net PnL | mean/session |
|---|---:|---:|---:|
| 2021 | 19 | −₹7,487 | −₹394 |
| 2022 | 21 | −₹1,589 | −₹76 |
| 2023 | 18 | −₹6,173 | −₹343 |
| **early-era total** | **58** | **−₹15,249** | **−₹263** |

**The question is legitimate and worth an afternoon:** the early era is a
*losing* era. Is that because the signal does not work, or because it works only
in some identifiable slice that the full book dilutes? If a slice exists, there
is a book to rebuild. If not, e013 is dead in a way that generalises.

---

## 2. The trap this experiment is built around, stated first

The obvious way to run this — filter on 2021–2023, then score on the full
six-year sample — is **in-sample**, and §5.2 bans it. The early era loses
₹15,249 over 58 sessions. Almost *any* aggressive filter turns a small losing
sample positive. Select on 2021–2023 and score on 2021–2023 and the answer is
guaranteed before the data is touched.

So:

> **Selection reads 2021–2023. The verdict reads 2024–2026. They never overlap.**

Arm 1 (in-sample) is computed and reported, and is **explicitly not a verdict**.
Arm 2 (held out) is the verdict. The distance between them is the finding, and
if that distance is large the honest reading is *the filter was fitted*, not
*the slice works*.

---

## 3. Design — freeze everything, move one thing

### 3.1 The universe

e028's corrected trade list, unchanged: `experiments/e028_expiry_encoding_audit/artifacts/audit_trades.csv`,
restricted to `mark_valid == True` → **n=129**. Nothing is re-selected, re-marked,
re-priced or re-frictioned. Lot eras come from the file. Marks are real
bhavcopy closes. Entry credit remains Black-Scholes (no intraday option price on
disk), exactly as in e026/e028, so **this can only move the number against the
book**.

### 3.2 The two eras (frozen)

| Arm reads | Years | n | Role |
|---|---|---:|---|
| Selection | 2021–2023 | 58 | choose ONE filter |
| Verdict | 2024–2026 | 71 | score it, once |

The split is chronological, not random, because the question is explicitly
*"does it work now"*. The verdict era is never seen during selection.

### 3.3 The five filters (frozen before any PnL is computed)

Structural, not swept. Each is one rule over fields known **at or before the
12:35 entry** — `expansion` (the 12:30 expansion ratio), `dte`, `credit_pts`.
No field computed after entry may appear in a filter; e029 asserts this.

| # | Filter | Rationale |
|---|---|---|
| F1 | `expansion ≤ 0.50` | tighten e013's 0.65 bar by ~1.4σ; the "even quieter mornings" hypothesis |
| F2 | `expansion ≤ 0.40` | the same, further; near the 25th percentile |
| F3 | `dte == 2` | answers the standing "this is not a 0DTE book" finding — 92/129 sessions are dte 2 |
| F4 | `dte == 2 AND expansion ≤ 0.50` | the conjunction of the two |
| F5 | `credit_pts ≥` median of the **selection** era | "take the richer flies" — a structural credit filter, median taken from selection data only |

**Five filters, not five hundred.** A sweep over `expansion` thresholds would
manufacture a winner from noise, and rule 4 (§5.4) exists for exactly that. The
set is small enough that the multiple-comparison burden is survivable, and it is
small enough to be written down.

### 3.4 The selection rule (frozen)

> Among the five, keep those with **selection-era EV > 0** and **selection-era
> n ≥ 20**. From those, take the **highest selection-era EV**. Ties within ₹50
> break to the **smaller n** (prefer the simpler filter).

Exactly **one** filter crosses into the verdict era. Not the best of five — the
one this rule names, chosen before any 2024–2026 number exists.

If **no** filter clears the bar, the experiment ends here with `NO SLICE` and
arm 2 is reported only as the unfiltered control. **A null result is a result.**

### 3.5 The honest null (frozen)

Any filter that keeps a *subset* of sessions will look better than the full book
partly because it is smaller and partly because the full book is dragged down by
the losing early era. So arm 2 is scored against a null:

> **500 random filters of the same session count, drawn uniformly without regard
> to PnL.** The verdict arm must beat the **95th percentile** of that null, not
> merely exceed zero.

This is the difference between "positive" and "positive because it's smaller".
A slice that clears zero but not the null has not been shown to exist.

---

## 4. Gates — frozen before the first run

| # | Gate | Bar |
|---|---|---|
| 0 | **Control** | The unfiltered corrected book reproduces e028 exactly: **+₹45,568** at 0.75 pts/leg and **−₹29,082** at 2.0 pts/leg on n=129, to ₹1. |
| 1 | **Selection is real** | At least one of the five clears selection-era EV > 0 with n ≥ 20. Otherwise verdict is `NO SLICE`. |
| 2 | **Verdict EV** | The chosen filter's **2024–2026 EV at 2.0 pts/leg > 0**. |
| 3 | **Verdict beats the null** | That EV is above the **95th percentile** of the 500 same-size random filters. |
| 4 | **Verdict sample** | ≥ 30 held-out sessions. Below that the verdict is `UNRESOLVABLE (n too small)`, never a pass. |
| 5 | **Verdict confidence** | Bootstrap over the held-out sessions: **P(EV > 0) ≥ 0.95**. |
| 6 | **No hindsight in the filter** | Every field used by the chosen filter is present in e013's own pre-entry data. Asserted against the known-at-entry field list. |

**Gates 2 and 3 must both pass.** Gate 2 alone is the claim every backtest makes.
Gate 3 is what makes it a claim about the signal rather than about the subset.

### Verdict strings (frozen)

| Outcome | Verdict |
|---|---|
| gate 1 fails | `NO SLICE — the early era loses under every structural filter` |
| gate 1 passes, gate 4 fails | `UNRESOLVABLE ON SAMPLE SIZE — n held out below 30` |
| gates 2 and 3 pass | `SLICE SURVIVES OUT-OF-SAMPLE` |
| gate 2 passes, gate 3 fails | `DEAD — positive, but indistinguishable from an arbitrary subset` |
| gate 2 fails | `DEAD — the slice does not generalise` |

---

## 5. One-sidedness

No intraday option price on disk, so the 12:35 entry credit stays
Black-Scholes in every arm, exactly as in e026 and e028. **This experiment can
only move the number against the book, never for it.** It moves no signal, no
timing, no cost model — it removes sessions.

---

## 6. What this experiment may not do

- It may not move the slippage assumption. The ladder is reported at several
  points; gates 2 and 3 are read at **2.0 pts/leg**, frozen here.
- It may not sweep. Five filters, §3.3, chosen before any PnL was computed.
- It may not score more than one filter out of sample. One.
- It may not re-select, re-mark, or re-price. Arm 0 is e028's book verbatim.
- It may not report the in-sample number without arm 2 beside it.
- It may not be re-run with a different bar.

---

## 7. Deliverables

- [ ] PREREG frozen (this file, before any code).
- [ ] `eras.py` — the five filters, the selection rule, the null, the gates.
- [ ] `test_e029.py` — control reproduction, no-hindsight assertion, and a test
      that the selection rule picks exactly one filter.
- [ ] `README.md` recording the verdict, the in-sample/out-of-sample gap, and
      what it supersedes.
- [ ] A registry row in `experiments/common/leak_registry.py`.
- [ ] `actionplan.md` and `RETROSPECTIVE.md` amended with whatever the verdict is.

---

## 8. What would make this experiment a failure beyond a null result

- **Arm 1 positive and arm 2 not.** That is the expected shape of an overfit
  filter, and it is reported as `DEAD`, not softened.
- **The chosen filter is F5 (the credit median).** A credit filter is the one
  most likely to be an artefact of the selection era's own distribution.
- **The held-out n lands below 30.** Reported `UNRESOLVABLE`, never rounded up
  into a pass.

---

## 9. Amendments (added after the first run, and why)

*(none yet)*