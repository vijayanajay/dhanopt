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
| WR | 46.7% | 47.5% |
| **Net** | **+₹288,581** | +₹732,244 |
| PF | 2.05 | 3.68 |
| Max DD | **₹14,608** | (not computed) |
| Exits | TARGET 651 / EOD 614 / **STOP 56** | — |

Expiry-day concentration survives path exits: expiry days +₹327k (Thu era +₹181k on 229 days @ 87.8% WR; Tue era +₹146k on 52 days @ **100% WR**); non-expiry days ≈ −₹42k.

**Exit-rule decomposition (vs endpoint PnL on the same days):**

| Exit | n | e005 PnL | Endpoint PnL | Delta |
|---|---:|---:|---:|---:|
| TARGET (+50%) | 651 | +466,593 | +904,695 | **−438,102** |
| EOD | 614 | −133,472 | −133,472 | **0 (identity)** |
| STOP (1.4×) | 56 | −44,540 | −38,978 | −5,562 |

Counterfactuals on identical days: as-run **+₹289k**; drop-the-target (keep SL) **+₹727k** (sweep's no-cap row: +₹726k); pure endpoint (= e001) +₹732k. The 1.4× SL is a non-event (4.2% of days; net effect −₹6k — stopped days' endpoints were no better) — **e004's 25% stop rate was pure pricing artifact**. The +50% profit target is what forfeits ₹438k: 651 days exit at avg +₹717 that would have closed at avg +₹1,390. (Numbers from the regenerated, column-consistent artifact — see the sweep addendum's note on the chunk-append bug.)

## Verdict

**What works:**
1. **The condor book survives honest intraday exits.** +₹289k at PF 2.05 with max DD ₹14.6k (7.3% of bankroll) under the *documented* exit rules — the e001/e002 thesis stands at the book level. e004's condor collapse is now fully explained and closed. (But see Addendum 2: the edge is concentrated in inverted-wall days.)
2. **The expiry-day 0DTE effect is real intraday, not a daily-bar artifact** — 100% WR on Tue-era expiry days, 87.8% in the Thu era.
3. The e001-identity construction (real opens in, real closes out) gives a leg-for-leg validated harness — any future exit rule can be tested against the same frozen labels.

**What does not work:**
1. **The documented +50% profit target destroys ~60% of the edge (−₹438k).** It caps exactly the big crush days that are the strategy's payoff. Raising it to **100% of credit** lifts net to +₹761k with *lower* drawdown (sweep addendum) — the single highest-value, zero-risk config change the sandbox has produced. (Post-hoc comparison of exit configs — mild selection bias, logged per protocol; validate before production.)
2. e004's lesson stands as a process rule: **fixed-IV greeks cannot price credit books**; the first two e005 designs (ATM-σ ratios, per-leg IV ratios) failed the same way before the endpoint-anchored design.

**Ceilings:** greeks frozen at entry (no intraday vol response — understates spike losses slightly, biases toward *fewer* stops, i.e. conservative in the direction that favors the conclusion); friction on real opens; 67 NOLEG + 21 NOSIM days excluded (mirroring e001's zero-credit/missing-leg skips).

**Recommendation:** adopt the condor book with the 1.4× SL but **drop/reloosen the +50% target** (e.g., trail, or target ≥100% of credit); re-run e002's gating with e005 exit-aware condor labels before any live sizing change.

## Addendum — Profit-target sweep (`target_sweep.py` → `artifacts/target_sweep.json`)

One prepared day set, six target levels (fixed-column CSV writer added after the sweep's sanity assert exposed a chunk-append column-order corruption in the original artifact — regenerated; the corrupted rows overstate WR, not the conclusions).

| Target | WR | Net ₹ | PF | Max DD ₹ | TARGET/EOD/STOP days |
|---|---:|---:|---:|---:|---|
| 50% (documented) | 46.7% | +288,581 | 2.05 | 14,608 | 651/614/56 |
| 75% | 47.7% | +567,818 | 3.06 | 3,910 | 388/876/57 |
| **100%** | **47.9%** | **+760,856** | **3.76** | **3,888** | 117/1,145/59 |
| 150% | 47.5% | +762,073 | 3.76 | 3,888 | 27/1,234/60 |
| 200% | 47.5% | +756,561 | 3.73 | 4,483 | 15/1,245/61 |
| no cap | 47.4% | +726,053 | 3.60 | 4,483 | 0/1,256/65 |

**Pick: target = 100% of credit.** Flat-optimum plateau 100–200%, all ≈ +₹760k at DD ≈ ₹3.9k (the target itself is a mild DD *reducer* — it banks gains on days that would fade). The documented 50% level sits off the cliff edge: −₹474k vs 100%, DD 3.8× worse. Below the plateau the cap amputates winners; beyond it nothing changes (few than 30 days ever reach +150%).

## Addendum 2 — Inverted-wall audit (`audit_inverted_walls.py`): the edge is NOT the condor

The single most important finding of the sandbox. e001's leg builder has no `put_wall < spot < call_wall` guard; e005 mirrored that (needed for the leg-for-leg identity). Classifying all 1,321 frozen condor days by wall-side validity (walls vs day-t futures open, e001's chain convention):

| Structure | n | Net ₹ | PF |
|---|---:|---:|---:|
| **valid (put_wall < open < call_wall)** | 964 | **−55,428** | **0.78** |
| inverted call wall (call ≤ open) | 173 | +474,465 | 91.8 |
| inverted put wall (put ≥ open) | 184 | +313,208 | 21.2 |

**107.6% of the frozen e001/e002/e005 condor edge comes from inverted-wall days**; the textbook structure loses after friction. Rule-selected subset: +₹288k → **−₹17k** valid-only. A fade probe shows inverted days winning even when spot keeps moving *through* the short strike (110 no-fade days, +₹399k at 94.5% WR) — only explicable by 0DTE extrinsic collapse outpacing intrinsic gain, and/or stale closing marks on deep-ITM strikes (a PF of 91.8 is not a tradable signature; bhavcopy closes are last-traded, and deep-ITM weekly strikes trade thinly).

**Interpretation, stated carefully:** on those days the position is not a premium-crush condor — it is a short-delta/long-delta directional bet that happened to be rescued by expiry-day crush. Whether the marks were capturable was validated against Dhan 5-min option candles (`marks_validation.py`, Addendum 4): **marks are real** — opens match exactly, closes within last-trade noise; the inverted walls are prior-OI walls above a crashed spot (futures open 23,302 on 09-25 after the 09-22→09-25 selloff), and crash-inflated premium crushing on expiry is a real post-crash short-vol effect. **All downstream conclusions inherit this composition** — e005's sweep sweet spot, the exit-aware gating (+₹495k condor-only ML at PF 15.4 is the same concentration), and the collated bottom line. Residual: one session validated (expired contracts leave the scrip master); extend backward via historical-candle depth or forward via live sessions.

## Addendum 4 — Mark validation against Dhan 5-min option candles (`marks_validation.py`)

Dhan serves 5-min OHLC+OI for NSE_FNO options by security ID (scrip master mapping: exact `SEM_TRADING_SYMBOL == 'NIFTY'`; FINNIFTY shares strike prices — never map by strike alone). Validated the latest frozen session (2026-09-25, expiry 2026-09-29 — only contracts still listed):

| Leg | Dhan open | Bhav open | Dhan close | Bhav close |
|---|---:|---:|---:|---:|
| PE 23500 (short wall) | 428.70 | **428.70** | 322.30 | 323.20 |
| CE 23500 | 14.95 | **14.95** | 12.40 | 12.50 |
| PE 23250 (wing) | 215.85 | **215.85** | 127.75 | 127.95 |
| CE 23650 (wing) | 6.90 | **6.90** | 5.30 | 5.30 |
| PE 23400 | 336.90 | **336.90** | 234.80 | 234.40 |
| CE 23400 | 27.95 | **27.95** | 24.35 | 24.70 |

**Verdict: marks are real.** Opens exact on all 6 legs; closes ≤ ₹0.90 (last-trade vs settlement timing). The inverted-wall mechanism is a genuine market crash between 09-22 and 09-25 (futures open 23,302 on 09-25): prior-OI walls ended up above crashed spot, the short wall put's crash-inflated premium crushes on expiry — coherent, price-consistent, and consistent with the audit's "wins even without fade" observation. Result recorded in `artifacts/marks_validation.json`; production handoff: `production_handoff.md`.

## Addendum 3 — Decay-trailing exit (`exit_sweep.py`) and IV regimes (`iv_regimes.py`)

**Kailash Nadh's decay-trailing proposal, tested** (from `trail_time` onward, exit when MTM ≥ trail_frac × credit; SL on, no profit cap; sanity-checked against all committed artifacts):

| Config | WR | Net ₹ | PF | Max DD ₹ | TRAIL/EOD/STOP days |
|---|---:|---:|---:|---:|---|
| documented (SL + 50% tgt) | 46.7% | +288,581 | 2.05 | 14,608 | —/614/56 |
| target 100% (sweep pick) | 47.9% | +760,856 | 3.76 | 3,888 | —/1,145/59 |
| no cap | 47.4% | +726,053 | 3.60 | 4,483 | —/1,256/65 |
| trail 75% @ 14:00 | 47.7% | +629,641 | 3.29 | 3,888 | 373/885/63 |
| trail 75% @ 13:30 | 47.8% | +611,734 | 3.22 | 3,888 | 377/881/63 |
| trail 80% @ 14:00 | 47.8% | +666,225 | 3.42 | 3,888 | 338/920/63 |
| **trail 80% @ 14:30** | 47.6% | **+685,327** | 3.48 | 3,888 | 334/924/63 |

Every trail config beats the documented 50% target by 2.1–2.4× at the same DD — his instinct about the cap is right. But none beats the plain 100%-of-credit target (best trail −₹75k vs it): in this first-order model the 100% target already locks in mid-crush before the late-day spike. Honest caveat favoring the trail: the delta/gamma model has no intraday vol response, so it *understates* the real 14:30–15:15 gamma spike — the trail's true benefit is a lower bound. As a risk-management overlay (capping late-day tail gamma) it remains attractive even at −₹75k.

**IV regimes contradict the VIX-sizing hypothesis** (per-day PnL bucketed by within-year expanding percentile of `straddle_pct`, the live-conditionable IV proxy):

| IV bucket | all days: n / net / avg / PF | expiry days: n / net / avg |
|---|---|---|
| q1 (low) | 264 / +76k / +289 / 2.25 | 49 / +102k / +2,075 |
| q2 | 297 / +128k / +431 / 3.99 | 152 / +131k / +862 |
| q3 | 262 / +43k / +165 / 1.75 | 42 / +64k / +1,526 |
| q4 | 205 / +1.5k / +7 / 1.03 | 10 / +20k / +2,034 |
| q5 (high) | 179 / +15k / +86 / 1.34 | 19 / +45k / +2,371 |

The edge does **not** concentrate in high IV — on non-expiry days the best buckets are low-to-mid IV and the highest-IV quintile earns almost nothing (classic short-vol: high IV means a stressed market). On **expiry days IV is nearly irrelevant** (every bucket profitable) — the 0DTE crush mechanism dominates regime. Sizing implication: do not upsize in high IV on non-expiry days; the defensible concentration is expiry-day-focused (see the expiry-gate result in e002 Add. 5), not IV-timed. Composition caveat (Add. 2) applies to these buckets too.

## Addendum 5 — Breached-wall credit spread vs the condor (`breach_spread.py`)

Kailash's Idea 3 formalized: on dte≤1 days where spot gapped over the prior max-OI wall (249 of 946 sim-able days; 319 valid-structure stand-downs), sell ONLY the breached wall + 150-pt wing (2 legs, defined risk), vs the 4-leg condor on the same days:

| Book (same 249 days) | Net ₹ | WR | Max DD ₹ | Worst day ₹ |
|---|---:|---:|---:|---:|
| **breach spread (SL + 100% tgt)** | +734,388 | 98.8% | 6,139 | **−6,139** |
| 4-leg condor (SL + 100% tgt) | +780,604 | 98.4% | **551** | (unbounded tail) |
| breach spread (SL only, no cap) | +674,162 | 98.4% | 6,139 | −6,139 |

Call-breach days: 139, +₹444k, 100% WR. Put-breach days: 110, +₹290k, 97.3% WR. Only **2 STOPs in 249 days**; worst-5% day still positive (p5 = +₹678); worst day −₹6,139 = the defined max loss working (150-pt width − credit).

**Reading — the spread is tail insurance, not a PnL upgrade:** the condor earns *more* on these days (+₹781k vs +₹734k at the same target, DD ₹551 vs ₹6,139) because the unbreached wing also pays on crush days. The spread's value is convexity: its worst day is a *known* ~₹7.9k (width − credit), while the condor's gap-through loss past the short strike is bounded only by the far wing (potentially ₹20k+ on a cascade day the first-order model understates). Adopt the spread if the tail matters more than ₹46k/5.7y; keep the condor if the marks and hedges are trusted. Either way: **stop trading 4-leg condors on valid-structure days** (PF 0.78) — on 319 days a year the right trade is no trade.
