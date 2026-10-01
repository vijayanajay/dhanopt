# Production Handoff — Breached-Wall Book (Sandbox → Live)

**Status: BREACH BOOK FAILED CERTIFICATION (gate 0, 2026-10-01) — NOT live-approvable; the +₹940,697 headline is a look-ahead artifact. Back to research.**
The pre-registered gate 0 (§7, e007) rebuilt the book on opening-OI walls — the only wall source observable at the 09:15 entry — and it produced **4 trades in 249 days (net −₹309, PF 0.96)** vs the frozen book's 249/+₹940,697. Independent confirmation: the t-1-wall harness (e005 Add. 8) gives 57 trades / −₹27.5k. The "gap over the wall" signal exists only against day-t EOD OI walls — information 6 hours *after* the entry. Marks validation (e005 Add. 6–7) is unaffected: the prices are real; the signal that selected them is not observable pre-open. Details: `experiments/e007_open_oi/README.md`. All live stages (§4–§5) below are **historical record, superseded by §7's outcome**; everything in this document that quotes the +₹940,697 (or e006's compounded projection, or e002's ML gates — see e002 Add. 7) inherits the artifact.

## 1. The book changed shape — it is now "breach-only"

The sandbox's final finding supersedes every earlier config: **the vanilla condor is only breakeven on valid-structure days** (+₹35k, PF 1.11 over 964 days) and **~97% of the frozen edge sits on inverted-wall days** — days where spot has gapped past the prior-day max-OI wall and the wall's inflated premium crushes on expiry (mechanism price-validated on 5 sessions 2021→2026; the fully-covered 2026-09-25 session matches to the paisa on all 6 legs).

So the production book trades **only** on dte ≤ 1 days with a breached wall, and **stands down entirely on valid-structure days** (~319 days a year — no trade is the correct trade there). Two acceptable executions, same 249-day backtest window (full 2021-01 → 2026-09):

### Decision box: spread vs condor on breach days

| | **Breach spread (2 legs)** | **4-leg condor on breach days** |
|---|---:|---:|
| Net (SL + 100% target) | +₹940,697 | +₹987,124 |
| WR / PF | 98.8% / 62.6 | 98.8% / — |
| Max DD | ₹6,139 | **₹551** |
| Worst day | **−₹6,139 = defined max loss** (width − credit) | **unbounded** (gap-through past short strike, bounded only by far wing) |
| STOPs in 249 days | 2 | 56 across the full condor book |
| Margin/lot | ≈ max loss ≈ **₹8–10k** (defined-risk spread margin; verify with broker calc) | ₹40–50k |
| Friction | 2 legs (≈ half the condor's) | 4 legs |

**Recommendation: breach spread.** It gives up ₹46k/5.7y to the condor but converts the reviewer's named tail (cascade through the short strike, SL slippage blowing through) into a *known, pre-paid* ~₹7.9k worst case, halves friction, and cuts margin ~5× — which moves every capital stage forward. Choose the condor variant only if intraday hedge liquidity is proven at size. (Valid-structure condor context: PF 1.11 — no trade is the right trade there.)

Notable: this book is **fully mechanical** — dte ≤ 1 + wall-breach test → trade. No ML required (98.8% WR leaves little for a selector to add; P(win) ranking added nothing within the gated set — see e002 Add. 6). The LightGBM/logistic stack remains valuable only for the *unrestricted* condor variant and as monitoring.

**⚠ Signal-timing caveat (found by the paper-trade harness, 2026-10-01):** the frozen book's breach test reads **day-t EOD OI** walls — information from 6 hours *after* the 09:15 entry. A clean t-1-wall gate (`paper_trade.py --full`) fires only 57 trades in 5.7 yr (vs 249) for **−₹27.5k**: 90% of the frozen net (+₹846k of +₹941k) comes from days the t-1 gate never sees. The edge is partly *in the wall update itself*. Repair path pre-registered in §7 gate 0 (e007: opening-OI walls via the Expired-Options API — walls sit within its ATM±10 reach on 99.6% of breach days, median |wall−spot| 64 pts). **No live order before gate 0 resolves.** → **Gate 0 resolved 2026-10-01: FAIL (e007)** — opening-OI walls give 4 trades / −₹309; no pre-open wall source replicates the book.

## 2. Backtest evidence (full window, 249 trades)

| Metric | Value |
|---|---:|
| Net | +₹940,697 (SL + 100% target) |
| Per trade / per year (≈44 trades) | ₹3,778 / ≈₹1,65,000 (≈83%/yr simple; see e006 for the compounded view) |
| WR / PF / max DD | 98.8% / 62.6 / ₹6,139 (3.1%) |
| Worst day | −₹6,139 (2025-08-07, put breach, SL) |
| Worst-5% day | **still positive** (+₹1,007) |
| Call breach vs put breach | 139 days +₹563k (100% WR) / 110 days +₹377k (97.3% WR) |

Side stats and worst-10 list: `experiments/e005_theta_condor/artifacts/breach_spread.json`.

**Compounded view (e006, `experiments/e006_compound_sim/`):** with config's caps live, the same trade list on the ₹2L account ends at **₹20,99,670 — CAGR 51.0%, max DD 1.2%**. The margin ladder runs 2 lots from day one (₹200k ≫ the ₹30k threshold); the `MAX_DAILY_LOSS` hard stop clamps the two gap-through days (−₹6,139/−₹5,499 at 2 lots → −₹2,500 each), which *cuts* max DD from 6.1% (uncapped 2-lot) to 1.2% while adding ₹18k net; the monthly breaker never binds (78% WR books don't lose ₹10k in a month at this size). Caveats carried in the e006 README: margin figure unverified with the broker calculator, clamp assumes fills at the cap, breaker semantics assumed.

## 3. Slippage cliff (measured, `slippage_cliff.py`)

Charging k× the modeled 1.5 pts/leg (core formula: pts × qty × legs, linear):

| k× | pts/leg | Net ₹ | PF | Max DD |
|---:|---:|---:|---:|---:|
| 1 | 1.5 | +940,697 | 62.6 | 6,139 |
| 5 | 7.5 | +808,757 | 41.2 | 7,039 |
| 8 | 12.0 | +709,802 | 25.9 | 7,841 |
| 12 | 18.0 | +577,862 | 11.4 | **10,335** (monthly cap breached) |
| 16 | 24.0 | +445,922 | 4.58 | 15,065 |
| 20 | 30.0 | +313,982 | 1.92 | 34,721 |

**Breakeven at 23.1× = 34.6 pts/leg** — per-trade avg net ₹3,778 vs ₹169 of 1× slippage. The 2-leg structure absorbs extreme deterioration before losing money; the binding constraint at scale is the *monthly loss cap* (breached at ~12×) before net turns negative. Caveats: linear slippage model, so lot-invariant by construction — non-linear book-walking impact at 50+ lots is real and unmeasured (needs LOB data); the 0DTE ITM short leg is the leg to watch.

## 4. Required validations before live (in order)

1. ~~**Composition robustness**~~ — **DONE (2026-10-01): all 249 breach sessions swept** through the Expired-Options API (`POST /v2/charts/rollingoption`). Verdict is taken at the trade level — the traded pair's credit (SELL wall − BUY ±150 wing, 09:15–09:20 opens, Dhan vs bhavcopy): **20 of 246 sessions pair-certified, 16 exact to <1 pt, worst diff +23.5 pts on a ~161-pt credit (+14.6%) — inside the 34.6 pts/leg slippage breakeven**, so no re-pricing of the book is warranted; the 4 off sessions all carry edge-of-window stitching. 3 sessions uncertifiable end-to-end (put wings outside the ATM±10 window at open; 2022-06-10-class ceiling). Residual ceiling, honest: the spot-relative sweep window cannot see most 150-pt wings at 09:15, so this certifies the mechanism and mark quality, not each of the 249 credits individually. Details: e005 README Add. 7; `artifacts/marks_sweep.json`.
2. **Paper-trade the gate (instrumented).** `paper_trade.py` + `shadow_runner.py` (e005) now log every session's gate decision, simulated 09:15 fills, per-leg fill drift, and a stressed re-sim; artifacts: `paper_trade.csv`/`.json`, `shadow_log.csv`. Pass bar over ≥4 consecutive expiry weeks: fills within the 12× DD boundary (18 pts/leg) on **every** trade, p95 within the 7.5-pt stage-2 trigger, WR ≥ 80% (pre-registered in §7 — below the 98.8% in-sample, far above coin-flip). Modeled pre-live drift already breaches the boundary on gap days (max 132.8 pts), so real fills decide this gate.
3. ~~**Core config audit**~~ — **DONE (2026-09-29)**: `NIFTY_LOT_SIZE` 75→65 (era table in `experiments/common/lots.py`), `WEEKDAY_SCHEDULES` recalibrated to Tuesday-expiry; 5 lot-hardcoded test pins updated to derive from config; 75 core + 36 experiment tests green.

## 5. Staged capital plan (after §4 gates pass; spread margin assumption)

| Stage | Bankroll | Book | Trigger to advance |
|---|---:|---|---|
| 0 | ₹2.0L | 1 lot breach spread, paper→live shadow | 4 clean expiry weeks (fills + slippage within 2× model) |
| 1 | ₹2.0L | 1 lot live | 8 expiry weeks; realized Calmar ≥ half of sim |
| 2 | ₹2.0–4.0L | 2–3 lots (spread margin ≈ ₹10k/lot → utilization still <50%) | margin verified with broker calculator; slippage tracking ≤ 5× model |
| 3 | Stop scaling at 3 lots | — | 0DTE capacity at size unproven; revisit only with LOB evidence |

Collateral yield (start immediately, independent of the book): pledge idle cash into overnight funds/liquid ETFs → ~₹10.6k/yr gross at Oct-2026 rates (₹7.4–10k post-tax by bracket; the ₹10–13k earlier figure assumed repo 6.0–6.5%) — mechanics in [COLLATERAL_PLAYBOOK.md](COLLATERAL_PLAYBOOK.md); margin is blocked only on trade days (~1–2/week), so the yield accrues nearly undisturbed.

## 6. Known ceilings (carried into live expectations)

- Breach-spread backtest is full-window on frozen daily marks; the +100% target and 1.4× SL are post-hoc choices (sweep-selected) — the pre-registered holdout (§7) is the honest Calmar test.
- **The frozen wall signal is not yet live-replicable** (§1 caveat): day-t EOD OI is 6h future-relative to the entry. Gate 0 (e007) must re-certify the book on opening-OI walls before the headline +₹940,697 can be treated as achievable.
- Theta path is first-order (no intraday vol response): spike losses understated; the defined-risk width and the 1.4× SL are the mitigations.
- One underlying, one mechanism (post-gap expiry crush). Multi-index rotation (BANKNIFTY/FINNIFTY/SENSEX — note BANKNIFTY weeklies were abolished Nov 2024; verify each index's current calendar) is a separate future experiment, only after the wall-breach edge is proven per index.

## 7. Pre-registered holdout protocol (frozen 2026-10-01, before any live order)

This section is written **before** the holdout window opens; it is a commitment, not a report. Nothing in it may be edited after the first holdout day except to append the actuals table. Changing a pass bar post-hoc invalidates the protocol — the whole point is to close the post-hoc-selection criticism recorded in §6.

**Frozen config (the only book evaluated):** dte ≤ 1 + wall-breach gate (wall source: whatever gate 0 certifies); SELL breached wall / BUY ±150-pt wing; entry 09:15 ± 5 min; SL 1.4× credit; target 100% of credit; EOD 15:25; 1 lot; real Zerodha friction. No other exit or sizing variant may be evaluated on holdout data — §3's sweep showed how post-hoc exit comparison inflates results.

**Holdout window:** the next 3 full expiry months after gate 0 certifies the wall source (≈ 13 expiry weeks / ~11 trades at the frozen book's rate). Sessions before the certification date are in-sample, whatever they show.

**Gate 0 — wall-source certification (blocks everything):** e007 rebuilds the breach gate from opening OI walls (Dhan Expired-Options API, per-strike OI at 09:15; feasible — 99.6% of breach-day walls within its ATM±10 reach). The frozen book is then **re-certified only if** the opening-OI book (same window, same exits) keeps: PF ≥ 5, WR ≥ 85%, net ≥ 40% of the frozen +₹941k. If it fails, the +₹940,697 is declared a look-ahead artifact, the book goes back to research, and §7 expires.

**Gates 1–3 (paper → live):**

1. **Paper (weeks 1–4):** ≥ 4 consecutive expiry weeks of shadow_log.csv with real quotes; every trade's realized slippage within 18 pts/leg (12× DD boundary, §3); p95 within 7.5 pts (stage-2 trigger); WR ≥ 80%. Any boundary breach = fail, re-run after instrument review.
2. **Live micro (weeks 5–12):** 1 lot real money on the certified gate; realized WR ≥ 70%; realized slippage p95 ≤ 7.5 pts; no clamp day. Two consecutive boundary breaches = stop, back to stage 1.
3. **Holdout verdict (end of month 3):** Calmar ≥ 0.5× the in-sample 62.6/6,139 ≈ **≥ 5.1** (i.e., annualized net / max DD ≥ ~5); WR ≥ 70%; PF ≥ 3. Pass = scale per §5. Fail = the in-sample edge does not replicate; stop trading, do not re-tune on the holdout (that re-opens the criticism this section exists to close).

**Record-keeping:** every session appends to `shadow_log.csv` (gate decision even on stand-downs — absence of trades is data); every live trade logs per-leg fills vs the 09:15 quote in the same schema. The actuals table below is the only permitted post-hoc addition.

| Gate | Window | Result | Date |
|---|---|---|---|
| 0: opening-OI walls | full 249-day rebuild (e007) | **FAIL** — 4 trades, net −₹309, PF 0.96, WR 0.50 (bars: ≥5 / ≥₹376,279 / ≥85%) | 2026-10-01 |
| 1: paper 4w | — | **expired** (gate 0 failed; §7's entry condition unmet) | 2026-10-01 |
| 2: live micro 8w | — | expired (gate 0 failed) | 2026-10-01 |
| 3: holdout verdict | — | expired (gate 0 failed) | 2026-10-01 |

**Post-failure direction (the only surviving lead):** walls move early and informatively *during* the session — an intraday wall-flip response strategy (reacting to real-time OI shifts after 09:15) is genuinely different from the pre-open gate, untested, and starts from zero. The shadow-runner instrumentation (`shadow_runner.py`) carries over to any successor signal. Marks validation, friction/slippage machinery, and e006's simulation semantics all remain valid tools; only the signal they measured failed.
