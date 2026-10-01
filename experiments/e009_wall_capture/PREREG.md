# PREREG — e009: live wall-capture collector (infrastructure only)

Status: **PREREGISTRATION ONLY — no code written, by design.** Filled
2026-10-01 using [../PRE_REGISTRATION_TEMPLATE.md](../PRE_REGISTRATION_TEMPLATE.md).
This is the one idea the sandbox left standing (see the closing verdicts in
[../experiment.md](../../experiment.md) v19–v21): every *observable* wall data
class is falsified, and the single untested source is a live feed with
per-minute freshness. This document exists so that if that feed ever gets
built, it starts from a pre-registered kill contract instead of enthusiasm.

---

## 1. Hypothesis

- **Claim:** *conditional* — IF a live chain-snapshot feed (full NIFTY OPTIDX
  chain, ≤60 s freshness, persisted) is operated for ≥6 months, THEN the
  intraday fresh-wall flip signal (e008's definition, unchanged) can be
  evaluated on fillable events for the first time.
- **Mechanism (why should this edge exist?):** walls are large resting OI;
  spot crossing a fresh wall produces measurable reaction/absorption intraday
  (74% of breach days had opening walls ≠ t-1 walls — walls genuinely move
  early). e008 proved the *events* exist: 111.9 flips/yr.
- **Why it might be an artifact:** it is one variable away from the family's
  sin — snapshots persisted from *my own* collector are timestamped by my
  clock and my sampler; a laggy or gappy capture reconstructs exactly the
  "observable only after the fill window" failure e008 died of. Also: the
  flip signal has never shown a rupee of certified edge (n=8, unjudgeable) —
  the hypothesis is that the edge becomes *measurable*, not that it exists.
- **Honest prior:** **low** for edge, **high** for measurability. The family
  is 0-for-4 on edge; what changes here is only the data class.

## 2. Information set

- **Decision at bar t sees:** the snapshot captured at time ≤ t (wall-clock
  stamped at capture, not at write). No reconstruction, no backfill from
  later snapshots.
- **Fill rule:** signal at t, fill at t+1's captured quotes; no same-bar
  fills. Unchanged from e008 — this rule is permanent (RETROSPECTIVE rule 5).
- **Leak-registry entry to add:** `e009_wall_capture: info=live-chain,
  live=True (self-captured)`, plus a note that capture gaps > 60 s suspend
  signal generation for the day (a gap is a data outage, not a fillable
  signal).
- **Day-t anything:** capture is day-t *by construction and honestly live*;
  that is the entire point of the experiment.

## 3. Data class

- **Source + freshness:** full NIFTY OPTIDX chain snapshots (all strikes with
  OI > 0), captured every ≤60 s during 09:00–15:35 IST on live sessions, via
  the broker/Dhan live quote API — **not** the Expired-Options rolling API
  (its sporadic rolling-window service is the exact ceiling that killed e008).
- **Completeness ceiling:** only strikes the feed returns; whatever the live
  chain omits is invisible, same as any live book. Outage policy: gaps > 60 s
  mark the session `PARTIAL`; a session is evaluable only if capture coverage
  ≥ 95% of 09:15–15:30.
- **Observability-vs-fill check (the e008 kill):** trivially satisfiable by
  construction — every captured strike carries its own fresh quote, so
  fillability is limited by the market, not the data. This is the property
  e008's data class lacked (2.4% fillable).
- **Marks validation plan:** live snapshots are the marks. Weekly spot-check:
  capture at 09:20 vs the day's bhavcopy opens for 10 random strikes (the
  marks-validation pattern from e005, reused); > 5 pts median drift on
  non-expiry days flags a feed problem before any PnL is computed.

## 4. Kill criteria (numeric, fail-only, set before any capture)

Any one kills e009 *as a strategy path* (the collector itself may still be
kept as instrumentation if §6 says so).

| # | Bar | Value | Why this number |
|---|-----|-------|-----------------|
| 1 | Coverage | ≥ 95% of sessions with ≥95% capture coverage | below this the capture is reconstructing the e008 blindness |
| 2 | Capacity | ≥ 60 certified flips/yr (fresh wall OI ≤ 2 min old at decision, both legs quoted ≤ 60 s) | e008 showed 111.9 flips/yr exist; if live freshness yields < 60 fillable, the signal is thinner than the family's own best case |
| 3 | Edge | PF ≥ 1.5 net of friction, n ≥ 20 certified trades | the family bar; n ≥ 20 because a live capture should not be starved |
| 4 | Composition | median wall-OI age at decision ≤ 5 min | e008's decisive bar, re-expressed for live data; if the flip confirms late even on live data, the mechanism itself is dead, not the feed |

**Verdict protocol:** README verdict-first, changelog entry either way, FAIL
documented identically to PASS. If criterion 1 fails, the *collector* fails
its build QA — fix the collector before judging the signal.

## 5. Sanity bars

- WR > 85% on the credit book = presumptively broken until the information-
  set audit clears it (this family already produced one 98.8% WR leak).
- PF > 10 anywhere = audit before belief.
- Friction: e005's measured per-leg cost model and the 34.6 pts/leg slippage
  breakeven reused; no net PnL read before friction is applied.
- Lot era from `experiments/common/lots.py`; labels follow the
  Tuesday-expiry era (2025-09-01+).
- n < 20 reported as unjudgeable, not suggestive.

## 6. Cost & machinery

- **Does this need to be built at all?** The *collector* is the only new
  machinery; evaluation reuses e008's `build_signal` walk verbatim (walls
  from snapshots instead of rolling bars — the `_wall_of`/`_spread_at`
  helpers carry over). No new backtest code beyond the reader.
- **Reuse inventory:** e008 signal walk, leak registry, friction model,
  marks-validation pattern, shadow runner (the collector *is* the shadow
  runner's data source), lots.py.
- **Incremental cost:** the collector itself (~1–2 days of code) + running
  it on live sessions for ≥6 months before the evaluation has n ≥ 20. That
  6-month clock is the real cost — and the reason this is preregistered
  now: the kill contract must be frozen before the first snapshot is saved.
- **Self-terminating?** Yes — criteria 1–4 judge it without a human
  deciding to stop; criterion 4 can fail as early as month 1.

## 7. Amendments

- 2026-10-01: initial pre-registration. No code exists. If this file is
  ever found alongside fetch/model/backtest code with an earlier mtime than
  its own commit, the pre-registration discipline has been violated — treat
  the experiment as contaminated.

## 8. Verdict

- *Empty by design. Fills only after ≥6 months of captures exist.*
