# E014 — Execution Microstructure & Limit Order TCA (Maker vs Taker)

**Contract & Pre-Registration:** [PREREG.md](PREREG.md) — frozen 2026-10-02 before the replay run (two pre-run mechanical amendments documented inside §2.5; no post-run tuning).
**Question:** Does the net alpha of the two validated strategies — E011 VRP delta-hedged straddle and E013 Pin Harvest Iron Fly — survive a realistic passive limit-order queue model, or does the modeled taker penalty hide a maker edge that never actually fills?

**Engine:** [core/execution/maker.py](../../core/execution/maker.py) — passive placement (bid + 1 tick / ask − 1 tick around the mid), bar-based queue & fill simulator (strict-through prints, or touch + 3× volume where a tape exists), adverse-selection penalty. Unit-tested in [tests/test_maker_execution.py](../../tests/test_maker_execution.py) (12 tests).

---

## 1. Verdict — PASSIVE-ONLY EXECUTION FAILS THE GATE (Both Strategies)

The maker engine works exactly as designed — **it is the strategy alpha that never shows up passively.**

| Kill Gate | Bar | E013 Pin Fly (MAKER) | E011 VRP Straddle (MAKER) |
|---|---|---|---|
| **1. Basket fill rate (AON)** | ≥ 50% of signaled sessions | **57.5%** (111/193) | **59.4%** (174/293) |
| **2. Per-trade quality** | Maker EV > Taker EV | ❌ **+₹1,018 < +₹2,149** | ❌ **+₹959 < +₹2,538** |
| **3. Aggregate survival** | Maker total ≥ 60% of taker | ❌ **27.3%** (₹1.13L / ₹4.15L) | ❌ **22.4%** (₹1.67L / ₹7.44L) |

**Gate 1 passes; Gates 2 and 3 fail decisively on both strategies.** Hybrid entry (E013) also fails quality: +₹667/trade vs +₹2,149 taker.

---

## 2. The Full Arm Comparison (2021–2026, all friction, era-correct lots)

### E013 — Pin Harvest Iron Fly (193 signaled sessions)

| Metric | TAKER | MAKER (AON) | HYBRID |
|---|---:|---:|---:|
| Sessions filled | 193 | 111 (57.5%) | 193 (100%) |
| Total net PnL | **+₹4,14,721** | +₹1,13,031 | +₹1,28,651 |
| Net EV / trade | **+₹2,148.81** | +₹1,018.29 | +₹666.58 |
| Win rate | 83.9% | 82.0% | 73.6% |
| Profit factor | **9.41** | 4.23 | 2.67 |
| Sharpe | **5.52** | 2.57 | 2.26 |
| Max drawdown | −₹11,940 | −₹10,622 | **−₹8,979** |
| Avg friction / trade | ₹551 | **₹202** | ₹243 |
| Adverse-selection events | 0 | 392 (₹69.6k penalty) | 657 (₹113.4k penalty) |

### E011 — VRP Delta-Hedged Straddle (293 signaled sessions)

| Metric | TAKER | MAKER (AON) |
|---|---:|---:|
| Sessions filled | 293 | 174 (59.4%) |
| Total net PnL | **+₹7,43,572** | +₹1,66,887 |
| Net EV / trade | **+₹2,537.79** | +₹959.12 |
| Win rate | 61.1% | 55.8% |
| Profit factor | **3.99** | 2.51 |
| Sharpe | **2.85** | 1.66 |
| Avg friction / trade | ₹912 | **₹530** (hedges remain taker) |
| Adverse-selection events | 0 | 522 (₹93.9k penalty) |

---

## 3. Why Passive Fills Destroy the Edge (Mechanism)

The decomposition below splits the taker-to-maker EV collapse for E013 (−₹1,130/trade) into its three causes:

1. **Session-level fill selection is a mirage — it is NOT the problem.** The taker EV on exactly the 111 maker-filled sessions is +₹2,161 vs +₹2,149 on all sessions (delta **+₹12**). On calmer days the 6-bar window simply fills more often. Gate 2 would have passed if selection were the story. It isn't.
2. **Adverse selection at the fill is real but secondary.** Across 1,914 passive fills, **71.8% were flagged** (2,372 total flagged incl. hybrid arms; ₹2.33L total penalty). Average clean-fill improvement ≈ 2.92 pts/leg, but flagged fills are re-priced at the taker alternative — i.e. the queue gives back nearly everything it saves whenever the option path runs ≥ 0.20% against the position within 5 minutes of the fill.
3. **Missed sessions are the killer.** E013 leaves 82 of 193 sessions untraded (≈ ₹1.76L forgone taker EV); E011 leaves 119 of 293 (≈ ₹3.02L). Both strategies are **theta-harvesting** books: their edge lives on the *fast* days, and on those days the option mid sweeps through any passive limit almost immediately — flagging the fill adverse — or never touches it at all.

**Structural conclusion:** these are spread-crossing strategies by nature. The option premium moves ≥ 1.5 pts (the full modeled half-spread) within a single 5-minute bar so often that a passive bid/ask − 1 tick simply does not get paid to wait. The only defensible passive execution is on the **exit** (54.7% of E013 exit legs filled passively, where urgency is lowest) — entry stays taker.

**Decision (per pre-registered gates): the production order path for E011/E013 remains taker at entry.** Phase 6 shadow trading will measure real queue dynamics via E009 60-second chains; the maker engine is retained as the measurement instrument, and the hybrid exit-leg variant is the only maker configuration that graduates to shadow testing.

---

## 4. Fidelity Verification (Apples-to-Apples Guarantee)

* **E013 TAKER arm** reproduces the published `pin_daily.csv` **per-session** gross/friction/net exactly (7/7 integration tests in [test_e014.py](test_e014.py), atol ₹0.01).
* **E011 TAKER arm** reproduces the published `vrp_daily.csv` **aggregate** total +₹7,43,572.25 exactly (293/293 sessions).
* Maker-arm structural invariants tested: AON basket property, zero-PnL NO-TRADE accounting, entry bars inside the frozen windows, flagged-fill re-pricing, gate presence.
* Maker arms reuse each strategy's own frozen valuation endpoints (PREREG §2.7); the only free variable across arms is execution style.

## 5. Declared Ceilings

Option mid paths are Black-Scholes models on 5-minute spot bars with session IV (no intraday surface dynamics, no volume-at-price tape → option fills use the strict-through clause only — pessimistic on fill probability); no re-pegging; AON ignores partial-fill leg risk; E011 hybrid out of scope (hedge schedule depends on entry timing). The real-queue measurement upgrades all of this in Phase 6 via E009 captures; the engine consumes them unchanged.

## 6. Artifacts

* `artifacts/metrics.json` — full per-arm metrics, gates, fill-selection effect, frozen params.
* `artifacts/trades.csv` — 1,165 session-arm records (filled + NO-TRADE).
* `artifacts/maker_fills.csv` — 3,467 leg-level fill records with limits, taker alternatives, flags, penalties.
