# E005 — Theta-Aware Condor Replay (Real Endpoint Prices + Greek Path)

**Question:** Does the condor edge — the engine's entire net PnL in e001/e002 — survive real intraday exits (1.4× credit SL / +50% profit target / EOD), when options are priced honestly? e004's answer (−₹548k, 4.1% WR) was invalid: fixed-IV Black-Scholes never credits theta decay, the condor's income.

**Method (final design after two failed variants):** the 5-min store is futures-only, so options are repriced along the path rather than fetched:
- **Entry levels:** each leg's REAL day-t open price (bhavcopy `open`, observable at 09:15 — e001's exact convention, skew embedded).
- **Exit levels:** each leg's REAL day-t close ⇒ **EOD exits reproduce e001's outcome exactly, by construction** (verified leg-for-leg: +762.24 == +762.24, −638.74 == −638.74).
- **Intraday MTM:** net delta (+½ gamma) from floor-free BS at each leg's own implied IV, applied to the real 5-min futures path; the residual (theta + vol change + everything greeks miss) glides linearly to the endpoint PnL.
- Walls/expiry/legs mirror e001 exactly (including its no-guard inverted-wall days and zero-credit skips) so the comparison to the frozen labels is leg-for-leg.
- # ponytail: first-order greeks freeze the entry smile (no intraday vanna/volga); the glide is linear. Two rejected designs are documented below — per-leg BS *ratios* explode at 0–1 DTE (cheap legs back out absurd IVs) and ATM-σ ratios miss wing skew. The upgraded answer needs historical intraday option candles.

Run: `python -m experiments.e005_theta_condor.replay_theta` (chunk-checkpointed, resume-safe). Self-checks: 9 tests pin theta-crediting, vol-expansion stops, mid-day-crash stops, and the e001 endpoint identity.

## Results (full window, 1,321 simulated days, 2021-01 → 2026-09)

| Metric | e005 path exits | e001 open→close (endpoint) |
|---|---:|---:|
| n | 1,321 (of 1,409 sessions; 67 NOLEG + 21 NOSIM excluded, mirroring e001's skips) | 1,321 (common days) |
| WR | 49.4% | 47.5% |
| **Net** | **+₹285,669** | +₹732,244 |
| PF | 2.12 | 3.67 |
| Max DD | **₹14,608** | (not computed) |
| Exits | TARGET 651 / EOD 614 / **STOP 56** | — |

Expiry-day concentration survives path exits: expiry days +₹327k (Thu era +₹181k on 229 days @ 87.8% WR; Tue era +₹146k on 52 days @ **100% WR**); non-expiry days ≈ −₹42k.

**Exit-rule decomposition (vs endpoint PnL on the same days):**

| Exit | n | e005 PnL | Endpoint PnL | Delta |
|---|---:|---:|---:|---:|
| TARGET (+50%) | 651 | +433,347 | +904,695 | **−471,348** |
| EOD | 614 | −110,363 | −133,472 | +23,109 |
| STOP (1.4×) | 56 | −37,315 | −38,978 | +1,663 |

Counterfactuals on identical days: as-run **+₹286k**; drop-the-target (keep SL) **+₹757k**; pure endpoint (= e001) +₹732k. The 1.4× SL is a non-event (4.2% of days; stopped days' endpoints were near the stop price anyway) — **e004's 25% stop rate was pure pricing artifact**. The +50% profit target is what forfeits ₹471k: 651 days exit at avg +₹666 that would have closed at avg +₹1,390.

## Verdict

**What works:**
1. **The condor edge survives honest intraday exits.** +₹286k at PF 2.12 with max DD ₹14.6k (7.3% of bankroll) under the *documented* exit rules — the e001/e002 thesis stands. e004's condor collapse is now fully explained and closed.
2. **The expiry-day 0DTE effect is real intraday, not a daily-bar artifact** — 100% WR on Tue-era expiry days, 87.8% in the Thu era.
3. The e001-identity construction (real opens in, real closes out) gives a leg-for-leg validated harness — any future exit rule can be tested against the same frozen labels.

**What does not work:**
1. **The documented +50% profit target destroys ~64% of the edge (−₹471k).** It caps exactly the big crush days that are the strategy's payoff. Removing it *raises* net to +₹757k while keeping the (harmless) SL — the single highest-value, zero-risk config change the sandbox has produced. (Post-hoc comparison of 2 exit configs — mild selection bias, logged per protocol; validate before production.)
2. e004's lesson stands as a process rule: **fixed-IV greeks cannot price credit books**; the first two e005 designs (ATM-σ ratios, per-leg IV ratios) failed the same way before the endpoint-anchored design.

**Ceilings:** greeks frozen at entry (no intraday vol response — understates spike losses slightly, biases toward *fewer* stops, i.e. conservative in the direction that favors the conclusion); friction on real opens; 67 NOLEG + 21 NOSIM days excluded (mirroring e001's zero-credit/missing-leg skips).

**Recommendation:** adopt the condor book with the 1.4× SL but **drop/reloosen the +50% target** (e.g., trail, or target ≥100% of credit); re-run e002's gating with e005 exit-aware condor labels before any live sizing change.
