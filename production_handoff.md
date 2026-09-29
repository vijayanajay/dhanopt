# Production Handoff — Expiry-Gated Condor Book (Sandbox → Live)

**Status: research complete; one validation DONE (marks), one PARTIAL (sample depth) — NOT live-approved.**
Every number below is 1 lot on a ₹2,00,000 bankroll, no compounding, real Zerodha friction. Evidence: `experiments/collated_results.md`; protocol + changelog: `experiment.md` (v1–v10).

## 1. What the sandbox established

| Finding | Evidence |
|---|---|
| Directional spreads are net-negative under two independent pricings — permanently retire them | e001 (−₹653k), e004 (bull −₹314k, bear −₹147k) |
| The edge is expiry-day (0DTE) short-vol on the condor-shaped book; it survives honest intraday exits | e005 (+₹288,581 documented exits, PF 2.05; SL fires on only 4.2% of days) |
| The documented +50% profit target is the single biggest PnL leak (−₹438k); **pick target = 100% of credit** (+₹760,856, PF 3.76, DD ₹3,888) | e005 target sweep, exit sweep |
| **Expiry-gating (dte ≤ 1) adds money while cutting trades 56% and DD to 1.2%** (+₹377k documented / +₹748k no-cap at 75–77% WR, 371 trades) | e002 Add. 5 |
| ML selection (dte features, EV ranking) beats the naive rule at every operating point; IV regime is irrelevant on expiry days | e002 dte variant, expiry gate, e005 iv_regimes |
| Decay-trailing exit (75–80% of credit after 14:00/14:30) is a good gamma-dodge overlay but trails the plain 100% target by ~₹75k in-sim | e005 exit sweep |
| ⚠ Composition: valid-structure condors LOSE (−₹55k, PF 0.78); 107.6% of the edge sits on inverted-wall days (prior-OI wall above/below a gapped spot; PF 91.8) | e005 inverted-wall audit |

## 2. Mark validation — DONE, honest marks confirmed (e005 `marks_validation.py`)

Dhan serves 5-min OHLC+OI for NSE_FNO options; validated the latest frozen session (2026-09-25, expiry 2026-09-29 — the only contracts still listed in the current scrip master):

- **Candle opens == bhavcopy opens EXACTLY on all 6 legs** (428.70 / 14.95 / 215.85 / 6.90 / 336.90 / 27.95).
- Closes match to last-trade vs settlement timing (max diff ₹0.90 on a 323-print).
- Scrip-mapping hazard found on the way: FINNIFTY shares NIFTY strikes — map by exact `SEM_TRADING_SYMBOL == 'NIFTY'`, never by strike alone.
- Mechanism explained: the "inverted" walls are prior-OI walls above a spot that **crashed between 09-22 and 09-25** (futures open 23,302 on 09-25). The short wall put's crash-inflated premium crushing on expiry is a real post-crash short-vol effect — **stale-mark contamination is excluded for this session.**

**Residual limitation:** this validates one session (the only one whose contracts survive delisting). The mechanism (crash-inflated premium crush) is coherent and price-consistent, but it is ONE observation. See §4.

## 3. The production config (proposed)

| Parameter | Value | Basis |
|---|---|---|
| Book | Iron condor only (put wall / call wall + 150-pt wings), max-OI walls, nearest expiry | e001 leg-for-leg identity; e005 |
| Day gate | **dte ≤ 1 only** (375 of 920 OOS days); no trades otherwise | e002 Add. 5 |
| Selector | ML P(win) per expiry day — logistic on dte feature set (fold-honest calibration), EV-ranked | e002 Add. 3/4 |
| Entry | 09:15–09:20, leg opens observable; 1 lot | e005 identity |
| Profit exit | **close at +100% of entry credit** (never 50%); optional decay-trail overlay (80% after 14:30) | e005 sweep + exit sweep |
| Stop | 1.4× credit (empirically fires on ~4% of days) | e005 |
| Hard EOD | 15:20 square-off (conservative vs the 15:25 replay bar) | engine mandate |
| Risk caps | Existing engine limits unchanged: ₹2,500 daily / ₹10,000 monthly | config.py |

## 4. Required validations before live (in order)

1. **Composition robustness (the big one).** Only the latest expiry week could be mark-validated. Extend validation backward: Dhan historical candle depth for *expired* option contracts is the open question — probe 1 week, 1 month, 1 year back (same probe script, older sessions). If expired contracts are not served, the fallback is validating 3–5 more live sessions as they expire (cheap: ~2 weeks of calendar).
2. **Paper-trade the gate.** Run the expiry-gated book on paper (or 1 lot live-minimum) for ≥4 consecutive expiry weeks; compare realized fills vs e005's assumptions (09:15 entry, +100% target, SL).
3. **Lot-size / schedule audit in core** (flagged since research began): `config.NIFTY_LOT_SIZE` is 75, actual era is 65 since 2025-12-30; `WEEKDAY_SCHEDULES` still carries Thursday-expiry logic. Fix before anything reads them live.

## 5. Staged capital plan (after §4 gates pass)

| Stage | Bankroll | Book | Trigger to advance |
|---|---:|---|---|
| 0 | ₹2.0L | 1 lot, expiry-gated, paper→live shadow | 4 clean expiry weeks (fills + slippage within 2× model) |
| 1 | ₹2.0L | 1 lot live, all rules active | 8 expiry weeks, realized Calmar ≥ half of sim |
| 2 | ₹4.0L | 2 lots on high-conviction days only (EV-ranked top half) | margin headroom verified (₹40–50k/lot; keep ≤50% utilization) |
| 3 | ₹6.0L+ | 3 lots max; **stop scaling regardless of results** | 0DTE short-vol capacity at 3 lots is unproven; slippage on ITM legs is the binding constraint |

Collateral yield (independent, start immediately): pledge idle cash (₹1.5L at stage 0–1) into overnight funds/liquid ETFs → ~₹10–13k/yr risk-free; the book is flat ~80% of days, so this does not collide with margin needs.

## 6. Known ceilings (carried into live expectations)

- Sim PnLs are 1-lot, no compounding; realized Calmar will be lower than the panel's best-of (selection inflation across ~10 read-outs of the same window).
- Theta path is first-order (no intraday vol response) — spike losses are understated; the trail overlay and the 1.4× SL are the mitigations.
- One underlying, one regime family (crash-adjacent expiry crush). Multi-index rotation (BANKNIFTY/FINNIFTY/SENSEX) is a *separate* future experiment, not part of this handoff.
