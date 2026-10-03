# PREREG — e026: Real-Price Re-Audit of the e013 Pin Harvest

**Frozen 2026-10-03, before any code in this directory exists.**

Filled from [../PRE_REGISTRATION_TEMPLATE.md](../PRE_REGISTRATION_TEMPLATE.md).
Status: **PREREGISTRATION ONLY — no engine, no numbers, by design.**

---

## 1. Why this experiment exists

e013 is the only surviving strategy claim in the repo: Pin Iron Fly, net
**+₹4,14,721**, PF **9.41**, max DD ₹11,940 (5.97%), across 193 sessions. It is
the single asset the entire Phase 6 production gate is pointed at.

Its arithmetic has never been audited. Two specific concerns:

1. **The marks are model output, not market data.** Every leg of every trade is
   priced by `core.pricing.bs_call` / `bs_put` on a single t-1 implied vol and
   a single `dte`. No real option price enters the PnL at all. e018 established
   on its own book that Black-Scholes reconstruction of marks is precisely
   where phantom money lives — it found a **₹104,000** phantom loss from a stale
   expiry-day close. That audit was applied to e018 and never to e013.

2. **e013's exit is marked at `t = 0.0001`** — effectively "these options expire
   15 seconds after 15:15". That is approximately right only for a contract
   expiring that afternoon. e013's traded sessions are **not** all 0DTE: the
   strategy's own label is 0DTE, its session set is not (see §2).

This is a **marking audit**, not a new strategy. The signal, the entry rule and
the trade list are FROZEN at e013's values. Only the exit mark changes. That
isolation is the whole design: any difference in the result is attributable to
the mark, because nothing else was touched.

---

## 2. Two facts established by inspection, before any PnL was computed

These are recorded here so the gates below can be read against them. Both were
obtained by re-implementing e013's selection and reproducing its published
output exactly (Gate 0 below is what makes that claim checkable).

**Fact 1 — e013 is not a 0DTE book.** Across its 193 traded sessions the
modelled `dte_t1` is:

| dte | sessions | published net PnL |
|---|---|---|
| 1 | 61 | ₹97,820 |
| 2 | 94 | — |
| 3 | 5 | — |
| 4 | 31 | — |
| 5 | 2 | — |

**132 of 193 sessions (68%) are on contracts with more than one day of life,
and they carry ₹3,16,901 — 76% of the published PnL.** The "0DTE" label
describes the intent, not the trade set. Consequence for this audit: the
`t = 0.0001` exit mark is approximately defensible on the 61 expiry-day
sessions and indefensible on the other 132.

**Fact 2 — e013 consumes a voided engine.** `pin_replay.py` imports
`load_or_compute_volatility` from `e011_vrp_delta_hedge`, the module convicted
of contract identity. The headline survives swapping in e018's corrected IV
(₹3,89,002, per-session correlation 0.993), so the *level* is not driven by the
bug — but **the selection set is**: 51 sessions fire only under the void IV and
31 only under the corrected one. Roughly a third of the trigger set is a
function of which IV engine is asked.

---

## 3. Information set

- **Decision inputs (bars 0–39, 09:15–12:30) and the 09:20/12:35/15:15 spot
  marks** are day-t, as in e013. Unchanged. Declared `day-t` / `live False`.
- **The exit mark under audit** is day-t's own EOD bhavcopy close — a price
  observed *after* the 15:15 decision. e026 therefore **does not improve
  e013's information set**; it measures what e013 would have earned had its
  15:15 exit been marked at prices that actually existed. Reporting a real-mark
  number as live-replicable would be a new leak of exactly the family this repo
  exists to prevent.
- **No Black-Scholes output is treated as market truth anywhere in this audit.**
  Where the model and the market disagree, the bhavcopy close wins and the
  disagreement is the finding.

### The asymmetry that must be stated, not buried

The **entry** credit at 12:35 IST is priced by the same Black-Scholes model,
because the repo contains **no intraday option price data of any kind** (§2.1 of
the action plan: e008's archive has no bid/ask, e009 has never run). The real
IV at 12:35 is simply not on disk.

This makes e026 a **one-sided** audit. It can only make e013 look *worse*.
The credit leg is unverified and cannot be verified from this data. The
direction of that error is bounded and reported in Gate 6, but it is not
removed.

---

## 4. Arms

| Arm | Signal / selection | Exit mark | Purpose |
|---|---|---|---|
| **A — CONTROL** | e013 verbatim | Black-Scholes, e011 IV | Reproduces published e013. **If this drifts, the audit is void — not the book.** |
| **B — REAL, VALID** | e013 verbatim | real bhavcopy 4-leg close, front expiry read from the trade date's own partition | The verdict. Restricted to sessions whose front expiry is **not** the trade date, where the close is a genuine last trade. |
| **C — REAL, INVALID** | e013 verbatim | same, but expiry-day exits | Reported **separately and never pooled into the verdict.** e018 measured expiry-day `close` as a stale last-trade price (0.30 on options expiring at 0.00). Pooling it would import a known artifact. |
| **D — CREDIT SENSITIVITY** | e013 verbatim, credit re-priced on e018's contract-correct IV | Black-Scholes | Bounds the un-auditable side (§3). Diagnostic, not a kill bar. |
| **E — GAP DECOMPOSITION** | — | BS@15:15 vs BS@15:30 vs real@15:30 on identical sessions | Separates a 15-minute timing mismatch from modelling error. Diagnostic. |

Arm B exists only because Arm C's marks are known-unreliable. Splitting them is
mandatory, not optional.

---

## 5. Kill criteria (numeric, fail-only, frozen before the run)

Gates 0, 1 and 5 judge **the audit**. Gates 2–4 judge **e013**. An audit whose
own gates fail produces no verdict about the book.

| # | Gate | Bar | Judges |
|---|---|---|---|
| **0** | **Control reproduces predecessor** | Arm A lands within ₹1 of the published **+₹4,14,721**, on **n = 193**, PF **9.41** | audit |
| **1** | **Contract identity of the exit mark** | 0 mismatches: the expiry marked is the expiry nearest the trade date, re-derived per trade from that date's own partition | audit |
| **5** | **Arithmetic impossibility** | 0 violations: an iron butterfly's gross PnL is bounded by `+credit` and `−(150 − credit)` per lot. Any breach is a pricing bug, not a tail. | audit |
| **2** | **Real-mark coverage** | ≥ 50% of Arm A's 193 sessions have a complete 4-leg real chain at the front expiry | audit |
| **3** | **Edge survives real marks** | Arm B net EV **≥ +₹600** per trade | e013 |
| **4** | **Profit factor survives real marks** | Arm B **PF ≥ 1.50** | e013 |

**Verdict rule, frozen in advance.** Gates 0, 1, 5 and 2 must pass for the
audit to speak at all. If they pass and **either 3 or 4 fails**, the verdict is
**VOID-PENDING-CORRECTION**: e013's published +₹4,14,721 is struck from the
record and must be restated at the Arm B figure before it may be used in any
sizing table, model or pitch. If 3 and 4 both pass, the verdict is
**SURVIVES REAL MARKS**, restated at the Arm B figure — the published number
still does not ship un-audited.

**A gate that fails, fails. It is not moved after the result is seen.**

---

## 6. Sanity bars

- **Roundness (§5.11 of the action plan).** Arm A's PF of 9.41 and 83.9% win
  rate are at or past the roundness bar. A *drop* in PF is the expected result,
  not a suspicious one. A rise would be the suspicious one.
- **Sample honesty.** Arm B's n is reported, not assumed. Sessions lacking a
  complete 4-leg chain are `NO TRADE` (§5.5 fail-closed), never interpolated.
- **No same-row self-comparison.** Arms A and B are marked on *identical*
  sessions before any statistic is taken, so a difference in totals cannot be
  an artefact of a changing trade list.
- **Distribution before PnL (§5.6 corollary).** The per-session mark gap is
  published alongside the total. A single mean difference is not a result.
- **Control beats diagnostic (§5.10).** Gate 0 is the load-bearing check. Fifty
  PnL metrics produce nothing; one control that reproduces a predecessor
  produces a decision.

---

## 7. Cost & machinery

- **New code:** one module (`audit_realmark.py`), one test file. The signal walk
  is re-implemented deliberately rather than imported, so that the control is a
  genuine reproduction and not a tautology against a shared helper.
- **New data:** none. Every input is already on disk —
  `experiments/e008_wall_flip/artifacts/walls/` (576 session files),
  `data/intraday/interval=5/` (spot bars), `data/historical/` (1,415 bhavcopy
  partitions). Runtime ~3 minutes.
- **Reused machinery:** `core.pricing`, `experiments.common.lots`,
  `core.feeds.intraday`, `core.feeds.bhavcopy.parse_date`, and e018's
  contract-identity expiry-resolution pattern.
- **Self-terminating:** yes. Gate 0 fails ⇒ nothing else is read. Gates 3–4 are
  decided by the run without a human choosing to stop.

---

## 8. What this experiment cannot do

Stated up front, so nobody reads a PASS as more than it is.

1. **It cannot validate fills.** Real *closing* prices are not real *executable*
   prices. Fill feasibility remains the job of the e009 live capture. A pass
   here means the edge survives real marks, not that it is tradeable.
2. **It cannot verify the entry credit.** No intraday option price exists on
   disk (§3). The credit leg keeps its Black-Scholes mark in every arm.
3. **It cannot make e013 live-replicable.** The signal is still day-t. Nothing
   here changes §Phase 6's Gate 0 requirements.
4. **It does not test the pin mechanism.** Whatever survives is whatever the
   expansion-ratio filter selects on real marks. If it survives, the *filter*
   has value; that is a narrower claim than "dealer pinning works".

---

## 9. Amendments

Full disclosure, in order. Two mechanical amendments were made after the first
runs but before any verdict; **neither touched a kill bar on the book**, and the
reasoning is given so a reader can disagree with it.

- 2026-10-03: initial pre-registration. No code, no engine, no artifacts in
  this directory. Any file here with an mtime earlier than this document, other
  than this document, means the discipline was violated — treat the experiment
  as contaminated and re-freeze.

- 2026-10-03 (run 1) — **Gate 0 caught a sign error in the audit engine.**
  The control landed on **−₹20,94,066** instead of +₹4,14,721. Cause: `e013_credit`
  negated e013's `credit` variable, which is positive fly value, not a negative.
  This is recorded as a *success of the design*, not a defect in it: a control
  that reproduces a predecessor to the paisa is exactly the instrument that
  catches an audit's own arithmetic before it can be mistaken for a finding
  about the book. Fixed, and re-frozen.

- 2026-10-03 (run 2) — **Amendment 1: the arithmetic bound is asserted on
  expiry marks only.** Gate 5 initially asserted the iron-fly bound on every
  mark. That is wrong: an ATM straddle with days of life can exceed 150 points,
  so `min(|S−K|, 150)` does not describe an intraday mark. The bound is now
  asserted only where the mark *is* the expiry payoff. This implements what §4
  already said about trusting expiry-day closes; it does not add a new standard.

- 2026-10-03 (run 3) — **Amendment 2: bound applicability and price trust are
  separate predicates.** Collapsing them into one flag silently dropped the
  expiry-day bound breach instead of reporting it. They are now distinct, and
  untrusted breaches are returned as evidence for Arm C's exclusion.

  This matters: the breach is **2026-01-20**, where the K=25000 PE closed at
  **0.20 on its expiry day while expiring at 0.00** — e018's stale-close artifact,
  rediscovered independently. Collapsing the two predicates would have thrown
  away the corroborating evidence for Arm C.

**Defence of the verdict's integrity:** amendments 1 and 2 changed only *audit
validity* predicates (gates 1, 5, 2). Gates 0, 3 and 4 — the control and both
kill bars on the book — were never amended. The verdict is therefore not the
product of a moved goal.

## 10. Verdict

- *Empty by design. Fills only after `audit_realmark.py` has run and every
  gate above has a recorded value.*