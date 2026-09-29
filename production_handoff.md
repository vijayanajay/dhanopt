# Production Handoff — Breached-Wall Book (Sandbox → Live)

**Status: research complete; marks validated on one session, composition robustness PARTIAL — NOT live-approved.**
All numbers 1 lot on ₹2,00,000, no compounding, real Zerodha friction. Evidence: `experiments/collated_results.md`, `experiments/e005_theta_condor/README.md` (Add. 1–5), `experiment.md` (v1–v13).

## 1. The book changed shape — it is now "breach-only"

The sandbox's final finding supersedes every earlier config: **the vanilla condor does not work on valid-structure days** (−₹55k, PF 0.78 over 964 days) and **107.6% of the frozen edge sits on inverted-wall days** — days where spot has gapped past the prior-day max-OI wall and the wall's inflated premium crushes on expiry (mechanism price-validated on the 2026-09-25 session: Dhan 5-min candle opens == bhavcopy opens exactly on all 6 legs).

So the production book trades **only** on dte ≤ 1 days with a breached wall, and **stands down entirely on valid-structure days** (~319 days a year — no trade is the correct trade there). Two acceptable executions, same 249-day backtest window (full 2021-01 → 2026-09):

### Decision box: spread vs condor on breach days

| | **Breach spread (2 legs)** | **4-leg condor on breach days** |
|---|---:|---:|
| Net (SL + 100% target) | +₹734,388 | +₹780,604 |
| WR / PF | 98.8% / 62.6 | 98.4% / — |
| Max DD | ₹6,139 | **₹551** |
| Worst day | **−₹6,139 = defined max loss** (width − credit) | **unbounded** (gap-through past short strike, bounded only by far wing) |
| STOPs in 249 days | 2 | 56 across the full condor book |
| Margin/lot | ≈ max loss ≈ **₹8–10k** (defined-risk spread margin; verify with broker calc) | ₹40–50k |
| Friction | 2 legs (≈ half the condor's) | 4 legs |

**Recommendation: breach spread.** It gives up ₹46k/5.7y to the condor but converts the reviewer's named tail (cascade through the short strike, SL slippage blowing through) into a *known, pre-paid* ~₹7.9k worst case, halves friction, and cuts margin ~5× — which moves every capital stage forward. Choose the condor variant only if intraday hedge liquidity is proven at size.

Notable: this book is **fully mechanical** — dte ≤ 1 + wall-breach test → trade. No ML required (98.8% WR leaves little for a selector to add; P(win) ranking added nothing within the gated set — see e002 Add. 6). The LightGBM/logistic stack remains valuable only for the *unrestricted* condor variant and as monitoring.

## 2. Backtest evidence (full window, 249 trades)

| Metric | Value |
|---|---:|
| Net | +₹734,388 (SL + 100% target) |
| Per trade / per year (≈44 trades) | ₹2,949 / ≈₹1,29,000 (≈64%/yr on ₹2L) |
| WR / PF / max DD | 98.8% / 62.6 / ₹6,139 (3.1%) |
| Worst day | −₹6,139 (2025-08-07, put breach, SL) |
| Worst-5% day | **still positive** (+₹678) |
| Call breach vs put breach | 139 days +₹444k (100% WR) / 110 days +₹290k (97.3% WR) |

Side stats and worst-10 list: `experiments/e005_theta_condor/artifacts/breach_spread.json`.

## 3. Slippage cliff (measured, `slippage_cliff.py`)

Charging k× the modeled 1.5 pts/leg (core formula: pts × qty × legs, linear):

| k× | pts/leg | Net ₹ | PF | Max DD |
|---:|---:|---:|---:|---:|
| 1 | 1.5 | +734,388 | 62.6 | 6,139 |
| 5 | 7.5 | +602,448 | 41.2 | 7,039 |
| 8 | 12.0 | +503,493 | 25.9 | 7,841 |
| 12 | 18.0 | +371,553 | 11.4 | **10,335** (monthly cap breached) |
| 16 | 24.0 | +239,613 | 4.58 | 15,065 |
| 20 | 30.0 | +107,673 | 1.92 | 34,721 |

**Breakeven at 23.3× = 34.9 pts/leg** — per-trade avg net ₹2,949 vs ₹132 of 1× slippage. The 2-leg structure absorbs extreme deterioration before losing money; the binding constraint at scale is the *monthly loss cap* (breached at ~12×) before net turns negative. Caveats: linear slippage model, so lot-invariant by construction — non-linear book-walking impact at 50+ lots is real and unmeasured (needs LOB data); the 0DTE ITM short leg is the leg to watch.

## 4. Required validations before live (in order)

1. **Composition robustness.** Marks validated on ONE session (the only still-listed expiry week). Extend: probe Dhan historical candle depth for *expired* contracts; if absent, validate 3–5 live sessions as they expire (~2–6 weeks of calendar). The crash-crush mechanism is coherent and price-consistent, but the sample is one observation.
2. **Paper-trade the gate.** ≥4 consecutive expiry weeks: realized fills vs the 09:15 entry / +100% target / 1.4× SL assumptions; log slippage per leg against the 12× DD boundary from §3.
3. **Core config audit** (flagged since research began): `config.NIFTY_LOT_SIZE` is 75, actual era 65 since 2025-12-30; `WEEKDAY_SCHEDULES` still Thursday-expiry. Fix before anything reads them live.

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
