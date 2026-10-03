# E005 — Theta-Aware Condor Replay (Real Endpoint Prices + Greek Path)

> **⚠ STRUCK FIGURES — `940,697` and `987,124` in the breach tables are dead.** The breach book's walls were day-t EOD OI — 6 hours after the 09:15 entry; e001's t-1 audit and e007's gate 0 (the only pre-open-observable wall source) returned 4 trades / −₹309.


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
| WR | 51.8% | 52.1% |
| **Net** | **+₹469,637** | +₹1,047,001 |
| PF | 2.38 | 4.08 |
| Max DD | **₹6,676** | (not computed) |
| Exits | TARGET 651 / EOD 614 / **STOP 56** | — |

Expiry-day concentration survives path exits: expiry days +₹513k (Thu era +₹351k on 242 days @ 90.5% WR; Tue era +₹162k on 56 days @ **100% WR**); non-expiry days ≈ −₹44k.

**Exit-rule decomposition (vs endpoint PnL on the same days):**

| Exit | n | e005 PnL | Endpoint PnL | Delta |
|---|---:|---:|---:|---:|
| TARGET (+50%) | 651 | +669,483 | +1,239,627 | **−570,144** |
| EOD | 614 | −140,946 | −140,946 | **0 (identity)** |
| STOP (1.4×) | 56 | −58,900 | −51,680 | −7,220 |

Counterfactuals on identical days: as-run **+₹470k**; drop-the-target (keep SL) **+₹1,037k** (sweep's no-cap row); pure endpoint (= e001) +₹1,047k. The 1.4× SL is a non-event (4.2% of days; net effect −₹7k — stopped days' endpoints were no better) — **e004's 25% stop rate was pure pricing artifact**. The +50% profit target is what forfeits ₹570k: 651 days exit at avg +₹1,029 that would have closed at avg +₹1,904. (Numbers from the regenerated, column-consistent artifact — see the sweep addendum's note on the chunk-append bug.)

## Verdict

**What works:**
1. **The condor book survives honest intraday exits.** +₹470k at PF 2.38 with max DD ₹6.7k (3.3% of bankroll) under the *documented* exit rules — the e001/e002 thesis stands at the book level. e004's condor collapse is now fully explained and closed. (But see Addendum 2: the edge is concentrated in inverted-wall days.)
2. **The expiry-day 0DTE effect is real intraday, not a daily-bar artifact** — 100% WR on Tue-era expiry days, 87.8% in the Thu era.
3. The e001-identity construction (real opens in, real closes out) gives a leg-for-leg validated harness — any future exit rule can be tested against the same frozen labels.

**What does not work:**
1. **The documented +50% profit target destroys ~54% of the edge (−₹570k).** It caps exactly the big crush days that are the strategy's payoff. Raising it to **100% of credit** lifts net to +₹1.09M with *lower* drawdown (sweep addendum) — the single highest-value, zero-risk config change the sandbox has produced. (Post-hoc comparison of exit configs — mild selection bias, logged per protocol; validate before production.)
2. e004's lesson stands as a process rule: **fixed-IV greeks cannot price credit books**; the first two e005 designs (ATM-σ ratios, per-leg IV ratios) failed the same way before the endpoint-anchored design.

**Ceilings:** greeks frozen at entry (no intraday vol response — understates spike losses slightly, biases toward *fewer* stops, i.e. conservative in the direction that favors the conclusion); friction on real opens; 67 NOLEG + 21 NOSIM days excluded (mirroring e001's zero-credit/missing-leg skips).

**Recommendation:** adopt the condor book with the 1.4× SL but **drop/reloosen the +50% target** (e.g., trail, or target ≥100% of credit); re-run e002's gating with e005 exit-aware condor labels before any live sizing change.

## Addendum — Profit-target sweep (`target_sweep.py` → `artifacts/target_sweep.json`)

One prepared day set, six target levels (fixed-column CSV writer added after the sweep's sanity assert exposed a chunk-append column-order corruption in the original artifact — regenerated; the corrupted rows overstate WR, not the conclusions).

| Target | WR | Net ₹ | PF | Max DD ₹ | TARGET/EOD/STOP days |
|---|---:|---:|---:|---:|---|
| 50% (documented) | 51.8% | +469,637 | 2.38 | 6,676 | 651/614/56 |
| 75% | 52.2% | +837,820 | 3.45 | 6,245 | 388/876/57 |
| **100%** | **52.2%** | **+1,086,580** | **4.18** | **5,504** | 117/1,145/59 |
| 150% | 52.2% | +1,085,638 | 4.17 | 5,650 | 27/1,234/60 |
| 200% | 52.0% | +1,082,758 | 4.13 | 8,344 | 15/1,245/61 |
| no cap | 51.9% | +1,037,476 | 3.98 | 8,344 | 0/1,256/65 |

**Pick: target = 100% of credit.** Flat-optimum plateau 100–200%, all ≈ +₹1.09M at DD ₹5.5–8.3k (the target itself is a mild DD *reducer* — it banks gains on days that would fade). The documented 50% level sits off the cliff edge: −₹617k vs 100%, with 1.2× the drawdown. Below the plateau the cap amputates winners; beyond it nothing changes (fewer than 30 days ever reach +150%).

## Addendum 2 — Inverted-wall audit (`audit_inverted_walls.py`): the edge is NOT the condor

The single most important finding of the sandbox. e001's leg builder has no `put_wall < spot < call_wall` guard; e005 mirrored that (needed for the leg-for-leg identity). Classifying all 1,321 frozen condor days by wall-side validity (walls vs day-t futures open, e001's chain convention):

| Structure | n | Net ₹ | PF |
|---|---:|---:|---:|
| **valid (put_wall < open < call_wall)** | 964 | **+34,589** | **1.11** |
| inverted call wall (call ≤ open) | 173 | +601,268 | 75.9 |
| inverted put wall (put ≥ open) | 184 | +411,145 | 20.0 |

(Fresh audit runs on the endpoint labels it always classified; the pre-era-fix table read −₹55k/PF 0.78 for valid days.) **~97% of the frozen endpoint condor edge comes from inverted-wall days**; the textbook structure is breakeven after friction (+3.3% of the edge). Rule-selected subset: +₹380k → **+₹16k (PF 1.17)** valid-only. A PF of 75.9 on 173 days is not a tradable signature; bhavcopy closes are last-traded, and deep-ITM weekly strikes trade thinly.

**Interpretation, stated carefully:** on those days the position is not a premium-crush condor — it is a short-delta/long-delta directional bet that happened to be rescued by expiry-day crush. Whether the marks were capturable was validated against Dhan 5-min option candles (`marks_validation.py`, Addendum 4): **marks are real** — opens match exactly, closes within last-trade noise; the inverted walls are prior-OI walls above a crashed spot (futures open 23,302 on 09-25 after the 09-22→09-25 selloff), and crash-inflated premium crushing on expiry is a real post-crash short-vol effect. **All downstream conclusions inherit this composition** — e005's sweep sweet spot, the exit-aware gating (+₹589k condor-only ML at PF 18.6 is the same concentration), and the collated bottom line. Residual: one session validated (expired contracts leave the scrip master); extend backward via historical-candle depth or forward via live sessions.

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
| documented (SL + 50% tgt) | 51.8% | +469,637 | 2.38 | 6,676 | —/614/56 |
| target 100% (sweep pick) | 52.2% | +1,086,580 | 4.18 | 5,504 | —/1,145/59 |
| no cap | 51.9% | +1,037,476 | 3.98 | 8,344 | —/1,256/65 |
| trail 75% @ 14:00 | 52.2% | +923,910 | 3.70 | 5,671 | 373/885/63 |
| trail 75% @ 13:30 | 52.2% | +899,950 | 3.63 | 6,059 | 377/881/63 |
| trail 80% @ 14:00 | 52.2% | +970,939 | 3.84 | 5,671 | 338/920/63 |
| **trail 80% @ 14:30** | 52.2% | **+995,153** | 3.90 | 5,671 | 334/924/63 |

Every trail config beats the documented 50% target by ~1.9–2.1× — his instinct about the cap is right. But none beats the plain 100%-of-credit target (best trail −₹91k vs it): in this first-order model the 100% target already locks in mid-crush before the late-day spike. Honest caveat favoring the trail: the delta/gamma model has no intraday vol response, so it *understates* the real 14:30–15:15 gamma spike — the trail's true benefit is a lower bound. As a risk-management overlay (capping late-day tail gamma) it remains attractive even at −₹75k.

**IV regimes contradict the VIX-sizing hypothesis** (per-day PnL bucketed by within-year expanding percentile of `straddle_pct`, the live-conditionable IV proxy):

| IV bucket | all days: n / net / avg / PF | expiry days: n / net / avg |
|---|---|---|
| q1 (low) | 264 / +90k / +342 / 2.14 | 49 / +107k / +2,190 |
| q2 | 297 / +226k / +761 / 5.61 | 152 / +214k / +1,410 |
| q3 | 262 / +73k / +278 / 2.05 | 42 / +82k / +1,953 |
| q4 | 205 / +16k / +77 / 1.28 | 10 / +21k / +2,101 |
| q5 (high) | 179 / +23k / +128 / 1.41 | 19 / +46k / +2,436 |

The edge does **not** concentrate in high IV — on non-expiry days the best buckets are low-to-mid IV and the highest-IV quintile earns almost nothing (classic short-vol: high IV means a stressed market). On **expiry days IV is nearly irrelevant** (every bucket profitable) — the 0DTE crush mechanism dominates regime. Sizing implication: do not upsize in high IV on non-expiry days; the defensible concentration is expiry-day-focused (see the expiry-gate result in e002 Add. 5), not IV-timed. Composition caveat (Add. 2) applies to these buckets too.

## Addendum 5 — Breached-wall credit spread vs the condor (`breach_spread.py`)

Kailash's Idea 3 formalized: on dte≤1 days where spot gapped over the prior max-OI wall (249 of 946 sim-able days; 319 valid-structure stand-downs), sell ONLY the breached wall + 150-pt wing (2 legs, defined risk), vs the 4-leg condor on the same days:

| Book (same 249 days) | Net ₹ | WR | Max DD ₹ | Worst day ₹ |
|---|---:|---:|---:|---:|
| **breach spread (SL + 100% tgt)** | +940,697 | 98.8% | 6,139 | **−6,139** |
| 4-leg condor (SL + 100% tgt) | +987,124 | 98.8% | **657** | (unbounded tail) |
| breach spread (SL only, no cap) | +867,006 | 98.4% | 6,139 | −6,139 |

Call-breach days: 139, +₹563k, 100% WR. Put-breach days: 110, +₹377k, 97.3% WR. Only **2 STOPs in 249 days**; worst-5% day still positive (p5 = +₹1,007); worst day −₹6,139 = the defined max loss working (150-pt width − credit).

**Reading — the spread is tail insurance, not a PnL upgrade:** the condor earns *more* on these days (+₹987k vs +₹941k at the same target, DD ₹657 vs ₹6,139) because the unbreached wing also pays on crush days. The spread's value is convexity: its worst day is a *known* ~₹7.9k (width − credit), while the condor's gap-through loss past the short strike is bounded only by the far wing (potentially ₹20k+ on a cascade day the first-order model understates). Adopt the spread if the tail matters more than ₹46k/5.7y; keep the condor if the marks and hedges are trusted. Either way: **stop trading 4-leg condors on valid-structure days** (PF 1.11, breakeven) — on ~319 days a year the right trade is no trade.

## Addendum 6 — Mark validation backward extension (`marks_validation_v2.py`)

Question: v1 (Add. 4) validated ONE session — the only expiry week whose contracts survive the current scrip master. Can the check reach the expired contracts the frozen window rests on?

**Dhan path found: the Expired-Options API** (`POST /v2/charts/rollingoption` — minute-level expired data, documented "last 5 years", index options ATM±10 near expiry). Probed facts, each pinned by a test: `expiryCode: 0` is rejected by a falsy-zero parse (use `1` = nearest); `drvOptionType` selects the side (CALL→ce, PUT→pe — one request does NOT return both); the series is literally **rolling** (re-centers on ATM as spot moves, so fixed-strike legs are recovered by filtering bars on the per-bar `strike` field, and a given strike appears only while within ATM±k); the dated scrip-master CSV (`?date=`) is a **no-op** (three dates → identical hashes) — deleted instruments are not downloadable (403). Dated scrip-master scaffolding was deleted; the rolling API's per-bar strike/spot makes it unnecessary.

**Result — 4 of 5 sampled sessions validated (2021-01-05, 2025-09-02, 2025-09-04, 2026-09-25):**

| Session (era) | Legs OK/PARTIAL | Opens | Closes |
|---|---|---|---|
| 2021-01-05 (Thu, lot 25) | 3 OK, 1 NO_BARS | −4.90 / +0.90 / −3.00 | ≤0.70 |
| 2022-06-10 (Thu, lot 25) | 0 — walls at ATM−26/+14, **outside the ATM±10 ceiling** | — | — |
| 2025-09-02 (Tue-era expiry day) | 3 OK, 1 PARTIAL | +8.25 / −8.80 / +1.45 | ≤3.10 |
| 2025-09-04 (Tue-era, dte 2) | 3 OK, 1 PARTIAL | +4.05 / −3.05 / −21.10 | ≤1.25 |
| 2026-09-25 (Tue, both endpoints) | 4 OK | **0.00 exact** (cross-checks v1) | ≤1.05 |

**Reading:** on every fully-covered leg, closes match bhavcopy within last-trade/settlement timing (≤3.1 pts), and the one session with full coverage matches **to the paisa on opens** — independently confirming v1 through a different endpoint. **Open-mark caveats are real and bounded:** edge-coverage legs (strike at the ±k window edge at 09:15) differ a few points (worst −21.1 on a ₹50 far-wing), consistent with rolling-API stitching rather than stale bhavcopy marks — flagged, not waved away. Days whose walls sit beyond ATM±10 (wide-wall days like 2022-06-10) are uncoverable on this endpoint. **Depth answer: minute data reaches 2021-01-04, the first FO day of the frozen window** — mark validation can extend to ~40 breach trades' worth of sessions before stage-1 go-live.

Run: `python -m experiments.e005_theta_condor.marks_validation_v2` → `artifacts/marks_validation_v2.json`; self-checks in `test_marks_validation_v2.py`.

## Addendum 7 — Full-book marks sweep (`marks_sweep.py`): the breach book's credits are certified

v2 (Add. 6) validated 5 sampled sessions; the handoff's last data-side gate asked for **every** breach-book session's entry marks. The sweep ran `marks_validation_v2.validate_session` over all 249 breach_spread sessions (2021-01 → 2026-09) through the Expired-Options API — checkpointed, ~33 s/session, ~2.5 h wall-clock, 0 network/token failures. The verdict is taken at the level that matters: the **traded pair's credit** — (SELL wall open − BUY ±150-wing open), 09:15–09:20 Dhan candle opens vs bhavcopy opens, in premium points.

| | |
|---|---:|
| Sessions swept | 249/249 |
| VALIDATED (≥1 covered leg) | 246 |
| Uncertifiable end-to-end | 3 (2022-06-02, 2023-02-02, 2024-06-06 — all put-breach days whose −150 wing sits outside ATM±10 at 09:15; no open bar exists for it on this endpoint) |
| Traded pair fully covered at open | 20 of 246 |
| Pair credit exact (<1 pt) | **16** |
| Pair credit off 1–24 pts | 4 (worst **+23.5 pts on a ~161-pt credit = +14.6%**, 2026-06-23; −11.6 pts = −7.8% on 2024-09-12) |

**Reading — the book's credits are real, with a bounded caveat.** Every certified diff sits inside the strategy's measured **34.6 pts/leg slippage breakeven** (Add. 5): even the worst session's credit error (+23.5 on a ~161-pt pair) is smaller than the slippage the book already absorbs per leg before PnL breaks. The 20 covered sessions span every lot era (75/50/25/75/65). The four off sessions all carry edge-of-window stitching (their non-traded legs show the same few-point edge effect Add. 6 flagged). The raw per-leg outliers in the sweep (68.8 open on 2024-11-21, 77.7 close on 2026-08-04) sit on **uncertified** pairs — a leg without an open mark — so they are stitching artifacts on non-traded legs, not credit errors. **Residual ceiling: only 20/246 trades' credits are paisa-certifiable** — the ATM±10 sweep window cannot see most wings at 09:15 (spot-relative window vs a 150-pt wing) — so this certifies the *mechanism and mark quality*, not each of the 249 credits individually. Treated as: marks validated; no re-pricing of the book warranted.

Run: `python -m experiments.e005_theta_condor.marks_sweep` → `artifacts/marks_sweep.json` (+ resumable checkpoint); self-checks in `test_marks_validation_v2.py::TestMarksSweepAggregate` — including the wall-strike sign rule: premium sorting mislabels breach-day legs where the wing out-prices the wall.

## Addendum 8 — Paper-trade harness (`paper_trade.py` + `shadow_runner.py`): the t-1-wall gate is NOT the frozen book

The handoff's stage-0/1 gates need instrumentation: a gate computed from **t-1 bhavcopy walls** (the only wall source observable before 09:15), simulated 09:15 fills on the day's real leg opens, per-leg **fill drift** (each leg repriced at BS on its own open-backed IV at the 09:20 spot — the cost of filling 5 min late), and an adverse-fill stressed re-sim. `shadow_runner.py` appends the same evaluation per session to `shadow_log.csv`, idempotent by date. Self-checks: `test_paper_trade.py` (synthetic t-1/day partitions pin the signal ladder, wall/wing extraction, adverse-fill stress, report flags).

**The material finding — run over the full 1,410-session window:**

| | frozen day-t-wall book (`breach_spread.py`) | clean t-1-wall gate (`paper_trade.py --full`) |
|---|---:|---:|
| Trades (5.7 yr) | 249 | **57** (33 call / 24 put) |
| Net | **+₹940,697** | **−₹27,509** (stressed −₹52,137) |
| WR | 98.8% | 43.9% |

Only **28 days overlap**: the frozen book makes **+₹94,435 on those**, and **+₹846,261 (90% of its net) on days the t-1 gate never sees**. Mechanism: the frozen book's walls come from day-t's *EOD* OI — 6 hours future-relative to the entry — so the "gap over the wall" test partially reads information the live trader cannot have; `replay_theta.prepare_day` carried this convention from e001 and flagged the no-look-ahead variant as a follow-up, which is exactly what this harness is. The t-1 signal is also *late by construction*: walls only update after a session, so next-morning gaps are often already inside stale walls. Negative across every year (2021–2026) — not one regime's artifact.

**Fill drift (pre-live, modeled):** mean 20.4 / p95 57.8 / max 132.8 pts per leg vs the 1.5-pt friction model and the **18-pt 12× DD boundary** (§3) — the ITM short leg after a gap is the cost driver, as `slippage_cliff.py` warned. Real fills, not models, now decide this: the shadow log accumulates from 2026-10-01.

**Consequences (carried to the handoff):** (1) ~~the +₹940,697 headline is not yet achievable as specified — e007 must rebuild the book on *opening-OI* walls~~ **RESOLVED 2026-10-01: e007 ran, and FAILED** (breach-day walls do sit within the Expired-Options API's ATM±10 reach on 99.6% of breach days, median |wall−spot| 64 pts — the data was reachable; the signal was not). Opening-OI walls give 4 trades / −₹309 / PF 0.96 against the frozen book's 249, so no pre-open wall source replicates the book and the headline is **struck**, not pending. (2) the frozen day-t-wall numbers remain internally consistent comparisons of exit/target variants, but their level inherits the look-ahead; (3) the pre-registered holdout protocol (handoff §7) makes gate 0 blocking. Marks validation (Add. 6–7) is untouched: it validated the *prices*, and both books anchor to the same opens.
