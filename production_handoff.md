# Production Handoff — Breached-Wall Book (Sandbox → Live)

**Status: research complete; marks validated on 5 sessions across 2021→2026, composition robustness PARTIAL — NOT live-approved.**
All numbers 1 lot on ₹2,00,000, no compounding, real Zerodha friction, era-correct lots (75/50/25/75/65 — re-run 2026-09-30 after the era-table correction). Evidence: `experiments/collated_results.md`, `experiments/e005_theta_condor/README.md` (Add. 1–6), `experiment.md` (v1–v14).

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

## 2. Backtest evidence (full window, 249 trades)

| Metric | Value |
|---|---:|
| Net | +₹940,697 (SL + 100% target) |
| Per trade / per year (≈44 trades) | ₹3,778 / ≈₹1,65,000 (≈83%/yr on ₹2L) |
| WR / PF / max DD | 98.8% / 62.6 / ₹6,139 (3.1%) |
| Worst day | −₹6,139 (2025-08-07, put breach, SL) |
| Worst-5% day | **still positive** (+₹1,007) |
| Call breach vs put breach | 139 days +₹563k (100% WR) / 110 days +₹377k (97.3% WR) |

Side stats and worst-10 list: `experiments/e005_theta_condor/artifacts/breach_spread.json`.

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

1. **Composition robustness — sample extended from 1 to 5 sessions (2021→2026).** Dhan's Expired-Options API (`POST /v2/charts/rollingoption`, minute-level expired data, 5 yr depth) recovers fixed-strike legs for expired contracts: opens match bhavcopy **to the paisa on every fully-covered leg** (0.0 on the all-legs 2026-09-25 session, cross-checked by two independent endpoints), closes within last-trade/settlement timing noise (<1.25 pts) everywhere covered. Residual: edge-coverage sessions (2021-01, 2025-09) had 1–2 legs outside the API's ATM±10 window at the open slot — opens there differ a few points (stitching/edge effect), flagged NOT exact; walls-outside-ceiling days (2022-06-10: walls at ATM−26/+14) are uncoverable by design. **Next: sweep the remaining ~40 breach trades' open marks before stage-1 go-live; treat any non-exact leg as a re-price event in the sim.**
2. **Paper-trade the gate.** ≥4 consecutive expiry weeks: realized fills vs the 09:15 entry / +100% target / 1.4× SL assumptions; log slippage per leg against the 12× DD boundary from §3.
3. ~~**Core config audit**~~ — **DONE (2026-09-29)**: `NIFTY_LOT_SIZE` 75→65 (era table in `experiments/common/lots.py`), `WEEKDAY_SCHEDULES` recalibrated to Tuesday-expiry; 5 lot-hardcoded test pins updated to derive from config; 75 core + 36 experiment tests green.

## 5. Staged capital plan (after §4 gates pass; spread margin assumption)

| Stage | Bankroll | Book | Trigger to advance |
|---|---:|---|---|
| 0 | ₹2.0L | 1 lot breach spread, paper→live shadow | 4 clean expiry weeks (fills + slippage within 2× model) |
| 1 | ₹2.0L | 1 lot live | 8 expiry weeks; realized Calmar ≥ half of sim |
| 2 | ₹2.0–4.0L | 2–3 lots (spread margin ≈ ₹10k/lot → utilization still <50%) | margin verified with broker calculator; slippage tracking ≤ 5× model |
| 3 | Stop scaling at 3 lots | — | 0DTE capacity at size unproven; revisit only with LOB evidence |

Collateral yield (start immediately, independent of the book): pledge idle cash into overnight funds/liquid ETFs → ~₹10–13k/yr risk-free; margin is blocked only on trade days (~1–2/week), so the yield accrues nearly undisturbed.

## 6. Known ceilings (carried into live expectations)

- Breach-spread backtest is full-window on frozen daily marks; the +100% target and 1.4× SL are post-hoc choices (sweep-selected) — the pre-registered holdout (next 3 expiry months, config frozen) is the honest Calmar test.
- Theta path is first-order (no intraday vol response): spike losses understated; the defined-risk width and the 1.4× SL are the mitigations.
- One underlying, one mechanism (post-gap expiry crush). Multi-index rotation (BANKNIFTY/FINNIFTY/SENSEX — note BANKNIFTY weeklies were abolished Nov 2024; verify each index's current calendar) is a separate future experiment, only after the wall-breach edge is proven per index.
