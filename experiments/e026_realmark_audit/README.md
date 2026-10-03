# E026 — Real-Price Re-Audit of the e013 Pin Harvest

> **⚠ STRUCK FIGURES — this document's control `₹4,14,721` is e013's Black-Scholes number, and its own `₹61,843` was struck in turn by e028.** The 64 verified sessions were format-selected by an expiry-encoding defect (356 of 576 sessions returned an empty chain). Corrected on n=129: **−₹29,082 at 2.0 pts/leg**. What survives here is the *method* and no part of the sample.


**Contract first:** [PREREG.md](PREREG.md) — frozen 2026-10-03, before any code
existed in this directory. Kill bars, the one-sidedness disclosure, and two
post-run mechanical amendments are all recorded there.

> ## ⚠️ SUPERSEDED BY [E028](../e028_expiry_encoding_audit/README.md)
>
> **The method below is sound. The sample is half the book.** e026's chain loader
> compared `expiry` to `str(front_expiry)` — a `datetime.date` against a raw
> string. The bhavcopy store holds `04-Feb-YYYY` for 2021–2024 and ISO for
> 2025+, so **356 of 576** sessions returned an empty chain and §5.5's
> fail-closed rule dropped each as `NO TRADE`. "64 verified sessions" was **64
> sessions the bug happened not to hide.**
>
> Re-run with the loader fixed: **129** sessions, **+₹45,568** at the engine's
> own 0.75-pt slippage, **−₹29,082 at a realistic 2.0 pts/leg**, EV **+₹353**
> (below this experiment's own +₹600 kill bar), PF 2.83, DD 26.2%, breakeven
> **1.51 pts/leg**, **93.0%** of PnL from 2025. **The verdict below is struck:
> the book does not survive real marks, and `test_e026.py` now pins the failing
> gate rather than the passing one.** Read E028.

**VERDICT: ~~`SURVIVES REAL MARKS`~~ `DOES NOT SURVIVE REAL MARKS` (e028).**
e013's **+₹4,14,721 is not tradeable as stated.** ~~Marked to prices that
actually existed, the surviving sample is +₹61,843. The edge is real; the size
was a modelling artifact.~~ **Marked to prices that actually loaded, and over the
sessions that were actually there, the book is dead at a realistic fill.**

```
.venv\Scripts\python.exe -m experiments.e026_realmark_audit.audit_realmark
.venv\Scripts\python.exe -m unittest experiments.e026_realmark_audit.test_e026
```

---

## 1. What was done

The signal was **frozen**. e013's expansion-ratio filter, entry bar, exit bar,
wing width, friction model and lot eras are all reproduced verbatim, and the
selection walk was deliberately **re-implemented rather than imported** so the
control is a genuine reproduction rather than a tautology against a shared
helper.

Only the **exit mark** moved: from Black-Scholes on a stale IV, to the real
bhavcopy `close` of all four legs, at the front expiry re-derived from each
trade date's own partition.

Everything else is identical. So any difference in the result is attributable
to the mark, because nothing else was touched.

---

## 2. Gates — all six, recorded

| # | Gate | Bar | Observed | |
|---|---|---|---|---|
| 0 | Control reproduces predecessor | within ₹1 of +₹4,14,721, n=193, PF 9.41 | **+₹4,14,721.04**, n=193, PF 9.41 | ✅ |
| 1 | Contract identity of exit mark | 0 mismatches, re-derived per trade | **0** | ✅ |
| 5 | Arithmetic impossibility | 0 violations on trustworthy marks | **0** | ✅ |
| 2 | Real-mark coverage | ≥ 50% of sessions | **54.9%** | ✅ |
| 3 | Edge survives real marks | Arm B EV ≥ +₹600 | **+₹966** | ✅ |
| 4 | PF survives real marks | Arm B PF ≥ 1.50 | **16.67** | ✅ |

Gate 0 is the one that matters. The engine lands on e013's published number to
**the paisa**. Everything downstream of it is therefore measuring e013, not a
reconstruction of it.

---

## 3. The arms

| Arm | Mark | n | Net | EV | PF | WR | MaxDD |
|---|---|---:|---:|---:|---:|---:|---:|
| **A — control (published convention)** | Black-Scholes | 193 | **+₹4,14,721** | +₹2,149 | 9.41 | 83.9% | ₹11,940 |
| **B — real marks, valid sample** | bhavcopy closes | **64** | **+₹61,843** | **+₹966** | **16.67** | 82.8% | **₹1,441** |
| C — real marks, expiry-day exits | bhavcopy closes | 42 | +₹1,51,956 | +₹3,618 | 16.77 | 83.3% | ₹2,917 |
| D — credit on the corrected IV | Black-Scholes | 193 | +₹3,48,094 | +₹1,804 | 6.71 | 81.4% | ₹10,853 |

**Arm C is reported and never believed.** e018 measured expiry-day `close` as a
stale last trade, and this run found the artifact independently: on **2026-01-20**
the K=25000 PE closed at **0.20 on its expiry day while expiring at 0.00**. Pooling
those marks would have imported a known defect into the verdict. Arm C's inflated
number is the clearest possible demonstration of why.

### Gap decomposition — identical sessions only (n = 106)

| | Net |
|---|---:|
| Black-Scholes @ 15:15 (as published) | ₹2,95,740 |
| Black-Scholes @ 15:30 (timing isolated) | ₹2,74,005 |
| **Real closes @ 15:30** | **₹2,13,798** |

**₹21,735 is a 15-minute timing mismatch. ₹60,207 — 74% of the gap — is
modelling.** Per-session gap: mean ₹773, std ₹2,618, 7 sign flips. The
distribution is published because a mean difference is not a result (§5.6).

---

## 4. Two findings that outlast the verdict

### 4.1 e013 is not a 0DTE book

| modelled dte | sessions | share of published PnL |
|---|---:|---:|
| 1 (true 0DTE) | 61 | 24% |
| 2 | 94 | — |
| 3 | 5 | — |
| 4 | 31 | — |
| 5 | 2 | — |

**132 of 193 sessions (68%) are on contracts with more than one day of life, and
they carry 76% of the PnL.** The "0DTE pin dynamics" label describes the intent,
not the trade set. This is the same species as both prior convictions: a
convention asserted in prose that the artifact does not support.

It matters mechanically, because e013 marks its exit at `t = 0.0001` — "these
options expire 15 seconds after 15:15". That is defensible for the 61 expiry-day
sessions and indefensible for the other 132, where it silently gifts the book
most of its remaining time value.

### 4.2 Arm D — the void IV is not what breaks it

Re-pricing the credit on e018's contract-correct IV gives **+₹3,48,094** against
the published +₹4,14,721. The level survives the void engine. But recall from
the pre-registration: **51 sessions fire only under the void IV and 31 only
under the corrected one.** The *selection* is a third unstable; the *size* is not.

This is the one place where the void's legacy does real damage — not through its
level, but through which sessions it chooses.

---

## 5. What this changes

**The restatement.** e013's surviving candidate must be carried at
**+₹61,843 on 64 verified sessions**, EV +₹966, PF 16.67, max DD ₹1,441 — not
+₹4,14,721 on 193. Against a ₹2,00,000 bankroll that is **~₹10,850/yr (~5.4%), 11.2 trades/yr,
max DD ₹1,441 (0.72%)** — and materially *safer* than the published figure
claimed, because the mark audit removed most of the fictitious variance along
with the fictitious profit. This is **net of the frozen friction model but on
EOD closing prices, which are not executable prices.**

Every sizing table, model or pitch that references +₹4,14,721 is now wrong.
`actionplan.md` §1, §Phase 4 and the scoreboard all carry it and need restating.

**The Phase 6 consequence.** Gate 0 of the production gate asks for 60 shadow
sessions. That bar was sized against a 193-trade book. What survives is 64
verified sessions on a narrower question — so either the bar is re-sized against
the *validated* arm, or it is met and still means something weaker than intended.

**The prior is not dead.** PF 16.67 is well past the roundness bar (§5.11), and
this audit's own direction-of-travel test asserts a real mark should make a book
look *worse*. A drop in PF is the expected outcome; a rise would be the
suspicious one. The remaining question is whether ₹966/trade survives costs
that this audit never modelled.

---

## 6. What this cannot do (§8 of the PREREG)

1. **It cannot validate fills.** Real *closing* prices are not real *executable*
   prices. Fill feasibility remains the e009 live capture's job.
2. **It cannot verify the entry credit.** There is no intraday option price on
   disk, so the 12:35 credit stays Black-Scholes in **every** arm. The audit is
   **one-sided** and can only make e013 look worse. The error's direction is
   bounded by Arm D; it is not removed.
3. **It cannot make e013 live-replicable.** The signal is still day-t. Nothing
   here changes the production gate's requirements.
4. **It does not test the pin mechanism.** What survives is whatever the
   expansion-ratio filter selects on real marks. If it holds, the *filter* has
   value — a narrower claim than "dealer pinning works".

---

## 7. Artifacts

| File | What |
|---|---|
| `PREREG.md` | Frozen contract, gates, one-sidedness disclosure, amendments |
| `audit_realmark.py` | The five arms, six gates, identity + impossibility audits |
| `test_e026.py` | 20 tests: control to the paisa, identity, impossibility, and the four traps this audit walked into |
| `artifacts/verdict.json` | Every gate value and arm result |
| `artifacts/audit_trades.csv` | 193 rows, every mark computed side by side |

Registered in [../common/leak_registry.py](../common/leak_registry.py) as
`day-t / live False` — declared **not** live-replicable, because the real mark
is a day-t EOD close, i.e. a price observed after the 15:15 decision.