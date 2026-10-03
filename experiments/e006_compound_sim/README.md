# E006 — Compounded Re-Sim: the Breach-Only Book Under LIVE Constraints

> **⚠ STRUCK FIGURE — the `₹940,697` headline this compounds is dead.** The breach book's walls were day-t EOD OI — 6 hours after the 09:15 entry; e001's t-1 audit and e007's gate 0 (the only pre-open-observable wall source) returned 4 trades / −₹309. The arithmetic below is valid; the object is void (MOOT).


**Question:** the handoff's +₹940k / 83%-yr headline is a flat 1 lot with no compounding and
no risk caps. What does the same trade list do on the real ₹2,00,000 account with
config's `MONTHLY_DRAWDOWN_CAP` circuit-breaker, the `MAX_DAILY_LOSS` hard stop, and a
margin-aware 1→2-lot ladder?

**Method (frozen, no tuning):** replay `breach_spread_target_100.csv` (249 trades,
2021-01 → 2026-09, SL 1.4× / target 100% of credit, era-correct lots) chronologically:
- **Ladder:** 1 lot below ₹30,000 cash (2 × ₹10k spread margin + one DD-cap of headroom),
  2 lots above; demotes automatically. The ₹10k/lot margin is the handoff's
  broker-calculator estimate — verify before stage-2.
- **Daily stop:** `MAX_DAILY_LOSS` (₹2,500) is a hard stop — when a day's loss breaches
  the cap the position is flattened and the day books exactly −₹2,500. # ponytail: the
  daily CSV cannot see the intraday bar where the cap fires, so the clamp assumes the
  flatten fills AT the cap; gap-through days would lose a bit more (5-min replay = upgrade).
- **Monthly breaker:** dip from the month's cash peak exceeding `MONTHLY_DRAWDOWN_CAP`
  (₹10,000) → no more trades that calendar month. # ponytail: the live reset semantics
  (peak-vs-start-of-month, counter reset timing) are unwritten in the BRD; this sim uses
  monthly peak-to-trough, reset on month change — pin the broker semantics before go-live.

**Reconciles with the frozen book:** flat 1-lot end value = ₹200,000 + Σ net = ₹1,140,697,
i.e. the +₹940,697 headline — asserted in `test_compound_sim.py`.

## Results (`artifacts/compound_sim.json`)

| Run | End cash | CAGR | Max DD (DD%) | Notes |
|---|---:|---:|---:|---|
| flat 1 lot (handoff baseline) | ₹11,40,697 | 35.7% | ₹6,139 (3.1%) | no caps, no ladder |
| **live constraints (ladder + both caps)** | **₹20,99,670** | **51.0%** | **₹2,500 (1.2%)** | 2 daily-stop clamps, 0 breaker months |
| ladder only | ₹20,81,394 | 50.8% | ₹12,278 (6.1%) | isolates the caps' effect |
| flat 2 lots, no caps (upper bound) | ₹20,81,394 | 50.8% | ₹12,278 (6.1%) | arithmetic reference |

**Reading — the caps IMPROVE the book, they don't constrain it.** With ₹2L capital the
margin threshold is cleared on day one, so the ladder runs 2 lots throughout; the
interesting result is the risk side: the two catastrophic days (2025-08-07 put breach
−₹6,139×2, 2025-11-11 −₹5,499×2) are clamped to −₹2,500 each by the daily hard stop,
cutting max drawdown **from 6.1% to 1.2% of bankroll** while *adding* ₹18k of net (the
clamped losses are smaller than the raw ones). The monthly breaker never binds — with
78.2% WR the book's losing streaks are too short to lose ₹10k in a month — so it is
pure insurance here, not a PnL drag.

**Honest ₹/yr on the ₹2L bankroll:** **~₹1,84,000/yr compounded (CAGR 51.0%)** at 1.2%
max drawdown, versus the handoff's flat-lot ~₹1,65,000/yr (83%/yr is a simple-return
number, not CAGR). The distinction matters: no-compounding ₹/yr overstates nothing, but
it is not what a compounding account earns — and the compounded path's risk (1.2% DD)
is *lower* than the flat path's (3.1%).

**Ceilings (unchanged from the handoff, now sharper):** margin figure unverified with a
broker calculator; daily clamp assumes fills at the cap (5-min replay would measure
gap-through); monthly-breaker semantics assumed (monthly peak-to-trough, month reset);
the +100% target and 1.4× SL remain post-hoc sweep choices — the pre-registered holdout
(next 3 expiry months) is still the honest test; and the composition caveat (edge
concentrated in inverted-wall days) applies to every row above.

Run: `python -m experiments.e006_compound_sim.compound_sim`;
checks: `python -m unittest experiments.e006_compound_sim.test_compound_sim`.
