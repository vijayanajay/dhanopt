# E014 — Execution Microstructure & Limit Order TCA (Maker vs Taker)
**Pre-Registration Protocol (Frozen 2026-10-02, before any replay run)**

**Question:** Does the net alpha of the two validated strategies — E011 VRP delta-hedged straddle and E013 Pin Harvest Iron Fly — survive a realistic passive limit-order queue model, or does the modeled taker penalty hide a maker edge that never actually fills?

---

## 1. Scope & Data (No New Data Assumed)

| Input | Source |
|---|---|
| E011 signaled sessions (293) | `experiments/e011_vrp_delta_hedge/artifacts/vrp_daily.csv` (frozen) |
| E013 signaled Pin Iron Fly sessions (193) | `experiments/e013_0dte_pin/artifacts/pin_daily.csv` (frozen) |
| IV / DTE per session | `experiments/e011_vrp_delta_hedge/artifacts/volatility_daily.parquet` (frozen) |
| 5-minute NIFTY spot path | `data/intraday/interval=5/` (same store as E011/E013) |

No option quote tape exists for ATM strikes on disk (E008 omitted ATM; E009 is live-capture only). Option quotes are therefore **modeled** from the same frozen Black-Scholes mid used by E011/E013, with the spread model below. This is a declared data ceiling, not a hidden assumption. Real fill-rate validation is deferred to Phase 6 (E009 60-second chains).

---

## 2. Frozen Execution Model

### 2.1 Quotes and Passive Placement (`core/execution/maker.py`)
* Option half-spread = **1.5 index points** (identical to the 1.5 pts/leg taker slippage assumption already frozen in E011/E013 — one spread model, no double standard).
* Tick = **0.05** points.
* Quote: `bid = mid − 1.5`, `ask = mid + 1.5`.
* Passive placement: **BUY at bid + 1 tick**, **SELL at ask − 1 tick** (= mid ∓ 1.45).
* Taker price (baseline / fallback) = mid ∓ 1.5.

### 2.2 Queue & Fill Simulator
An order resting at limit `L` fills in a bar iff:
1. **Strict-through print:** bar low `< L` for a BUY, bar high `> L` for a SELL; **OR**
2. **Touch + volume:** bar range touches `L` **and** bar volume ≥ **3×** order quantity.

A touch alone never fills (we model ourselves at the back of the queue). Option mid paths have **no volume tape**, so clause 2 is disabled for options — fail-closed; fills occur only on clause 1. Futures/spot bars (used only as the hedge reference, which remains taker) retain clause 2 capability in the engine but are not passively traded in this experiment.

* Fill price is always the limit (no price improvement modeled beyond it).
* No cancel/replace or re-pegging. One resting limit per leg, then deadline.

### 2.3 Timing (identical across arms)
| Event | E013 Pin Fly | E011 VRP Straddle |
|---|---|---|
| Signal / decision | bar 39 close (12:30) | bar 0 close (09:20 signal) |
| Entry posting | bar 40 open (12:35) | bar 1 open (09:20) |
| Entry passive window | bars 40–45 (30 min) | bars 1–6 (30 min) |
| Exit posting | bar 68 close (15:00) | bar 68 close (15:00) |
| Exit passive window | bars 69–71 | bars 69–71 |
| Forced taker cross (unfilled) | bar 71 close (15:15) | bar 71 close (15:15) |

### 2.4 Basket Policy
* **TAKER arm:** all legs cross immediately at taker prices (reproduces E011/E013 accounting).
* **MAKER arm (all-or-none):** all entry legs post passive limits simultaneously; the session trades **only if every leg fills within the entry window**. Otherwise `NO TRADE` for the day — missed alpha is counted. No partial-fill leg risk is simulated. This is the conservative arm: it cannot benefit from favorable partial fills.
* **HYBRID arm (E013 only):** legs fill passively where possible; unfilled entry legs cross taker at **bar 46 open** (first bar after window expiry, respecting the t+1 rule). Always trades; the chase cost is measured. E011 hybrid is out of scope: its intraday delta-hedge schedule depends on entry timing and would require a second hedge engine; the AON + taker arms answer the gate for it.

### 2.5 Adverse Selection
* Reference series = **the filled instrument's own modeled price path** (the option mid for every leg in this experiment). Reference move for a fill on bar `b` = `close[b+1]/close[b] − 1`; for the final bar, that bar's own `close/open − 1`.
* Threshold = **0.20%**. A SELL fill is adversely selected when the move ≥ +0.20%; a BUY fill when the move ≤ −0.20%. Sign-correct by construction for both calls and puts.
* **Pre-run amendments (2026-10-02, before the frozen run):** (1) an earlier draft referenced the underlying spot move and mapped "against the leg direction" from the order side alone. A mechanics smoke test showed that mapping has the wrong sign for put legs (a BUY PE is adversely selected when the underlying *rises*) and misses stale-limit fills where the option price sweeps through a resting order. The reference series was corrected to the instrument's own path — the plain reading of "an adverse 5-minute move". (2) The reprice reference was pinned to the taker alternative at posting rather than the fill bar's close, which was inconsistent with the stated rationale (it folded intra-bar drift into the penalty and double-counted the move). Threshold, penalty size for a flagged fill (spread − tick), and all other parameters are unchanged.
* **Penalty:** the flagged fill is re-priced at the taker alternative at posting (mid at post ∓ half-spread) — i.e. it is counted as if it had been crossed, removing exactly the captured spread improvement (spread − tick) and nothing else. The price damage of the subsequent move itself remains solely in the mark-to-market, so nothing is double-counted. Events are logged per fill.

### 2.6 Friction
Per-arm friction mirrors the published E011/E013 formulas exactly (brokerage ₹20/leg/side, 0.1% STT on sell turnover, exchange + SEBI + GST), with one substitution: where a leg executes passively, its 1.5 pts/leg point-slippage line is removed (the spread now lives in the fill price). Forced taker crosses keep the taker price model. E011 futures hedges remain **taker at 0.5 pts** in both arms — hedges are urgent risk orders, not premium-structure legs (documented decision, actionplan §5.1 scope).

---

## 3. Pre-Registered Gates (Non-Negotiable)

Evaluated on each strategy's MAKER (all-or-none) arm vs its TAKER arm under identical timing:

| Gate | Pass Threshold | Failure Meaning |
|---|---|---|
| **1. Fill Feasibility** | AON basket fill rate ≥ **50%** of signaled sessions | Passive-only execution halves capacity; infeasible at retail scale |
| **2. Per-Trade Quality** | Maker net EV/trade (after adverse-selection penalty) **>** Taker net EV/trade | Passive execution destroys per-trade value |
| **3. Aggregate Survival** | Maker total net PnL ≥ **60%** of Taker total net PnL | Missed sessions cost more than the per-fill savings gain |

**Pass = all three.** Any failure is a decisive finding for the actionplan; no parameter will be tuned after observing results.

### 3.1 Reported Diagnostics (not gates)
* Per-leg fill rates (entry and exit) and fill-bar distribution.
* **Fill-selection effect:** Taker-arm net EV on the maker-filled subset vs Taker-arm net EV on all sessions. A negative delta means passive fills concentrate on days that are worse for the strategy (session-level adverse selection).
* Adverse-selection event count and total penalty rupees, split entry/exit.
* Slippage points saved per filled leg vs taker.

---

### 2.7 Mid-Path Interpolation (Clarification, pre-run)
The E013 maker arm reuses E013's frozen valuation endpoints exactly: entry mid = BS at `t_entry = (dte − 0.5)/365`, exit reference = BS at `t = 0.0001` (intrinsic when `dte ≤ 0.01`). For passive fills between bars 40 and 71 the option mid path interpolates `t` **linearly in bar time** between those two frozen endpoints. E011's mid path uses its own in-engine clock (`t(i) = t0 − i·5/(375·365)`) unchanged. No other valuation convention is altered — the comparison isolates execution style only.

---

## 4. Declared Ceilings (Known, Accepted, Documented)

1. Option mid paths are BS-modeled with frozen session IV; no intraday IV surface dynamics.
2. No volume-at-price tape: option fills use the strict-through clause only (pessimistic on fill probability).
3. No queue-position modeling beyond back-of-queue; no re-pegging.
4. AON policy ignores partial-fill leg risk (conservative on capacity, silent on leg-risk PnL).
5. Exit window (15:00–15:15) is shorter than a full session; passive exit fills are under-counted rather than over-counted.

**Upgrade path:** E009 live 60-second chain captures (Phase 6) replace the modeled quotes with real top-of-book depth and prints; the same engine consumes them without modification.
