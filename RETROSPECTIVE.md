# Sandbox Retrospective — What the Leak Taught Us (2026-10-01)

**TL;DR: every strategy number this sandbox ever celebrated was produced by a measurement bug, and the sandbox's own pre-registered gate killed the family before it cost a rupee. The machinery is the asset; the strategies were the noise. This file is the permanent record and the rulebook for the next search.**

## 1. What the day-t wall leak actually was

One convention, inherited silently through four generations of code: **walls = max-OI strikes of day t's own EOD option chain**. It entered at e001 (mirroring the original engine's labels), was kept by e005 deliberately ("leg-for-leg comparison to the frozen labels"), and became load-bearing when the breach book made the wall-crossing test its entire signal. The problem: the entry happens at 09:15, but the walls are computed from OI as it stood at **15:30** — 6 hours of information the live trader cannot have. The "spot gapped over the wall" event exists only against walls that moved into the way *during* the day being traded. The book's entire edge was the wall update itself.

Three properties made it dangerous, in ascending order of lesson value:

1. **It was invisible to every statistical gate.** Calibration was excellent (Brier ≈ 0.20) *because* the models faithfully predicted the leaky labels. Win rates of 98.8% raise suspicion only after a leak is suspected; before that, they look like skill. **Calibration measures fidelity to the labels, not truth of the labels.**
2. **It compounded through inheritance.** e001 → e002 labels → e005 walls → breach book → e006 compounding → the handoff. Each consumer added a "caveat" line, none re-derived the foundation. By the time the number reached ₹940,697, six documents vouched for it and none had checked it.
3. **It survived because the sandbox measured the right things on the wrong object.** Marks were validated to the paisa, friction was real, exits were honest — every *price* was genuine. Only the *selection signal* was fictional. Honest components ≠ honest assembly.

## 2. How it was caught — and why that part worked

The leak was not caught by reviewing numbers; it was caught by **simulating the live information set**. The paper-trade harness asked one question the frozen pipeline never had: *what could the trader actually know at 09:15?* Walls from t-1 EOD bhavcopy — the only observable source — collapsed the book (57 trades, −₹27.5k). The pre-registered gate 0 then completed the proof with the freshest possible observable source (opening-OI walls via the per-bar-OI API): 4 trades, −₹309, and the decisive diagnostic that opening walls differ from t-1 walls on 74% of days (so no "stale copy" excuse exists) and the opening structure is valid on 244 of 249 "breach" days (so the signal has nothing to fire on).

The structural lesson: **the gates that worked were the ones written as commitments before the answer was known** — kill bars, coverage requirements, "fail = declare artifact and stop." The gates that failed were diagnostics run on the artifact itself (calibration, PF, WR, marks).

## 3. What survives untouched (the honest inventory)

| Survives | Why |
|---|---|
| **Marks validation (e005 Add. 6–7)** | Validated *prices*, not signals: 249 sessions swept, traded-pair credit certified on 20 (16 exact to the paisa), worst diff +23.5 pts — inside the 34.6-pt slippage breakeven. Whatever signal comes next, its entry marks are measurable. |
| **Friction / slippage machinery** | Core Zerodha friction, the 1.5 pts/leg model, the 12× DD boundary, the 34.6-pt/leg breakeven method — signal-independent arithmetic, now with a measured pre-live drift estimator. |
| **The 5-min store + path simulator** | Identity-validated (EOD exits reproduce e001 leg-for-leg); reusable for any intraday book. |
| **e004's spread verdicts** | Bull/bear spreads are net-negative under path exits — wall-free labels, unaffected. A confirmed *avoid*. |
| **e006's constraint semantics** | Margin ladder, daily-stop clamp, monthly breaker — tested machinery awaiting a real trade list. |
| **The shadow runner + leak registry + pre-registration discipline** | The process layer: daily evidence accumulation, structural leak guards, commitment-first gates. |
| **Negative results as knowledge** | Valid-structure condors are breakeven at best; IV-regime timing adds nothing on expiry days; P(win) doesn't size positions; directional spreads lose. The next search starts from a *pruned* hypothesis space. |

**Expected honest returns today: ₹0 from any strategy, ~₹10–13k/yr from collateral yield on the idle ₹2L** (pledging into overnight funds/liquid ETFs — independent of all research, and the only certified-positive action available).

## 4. What a clean strategy search does differently from day one

1. **Live-replicability is the design constraint, not a validation step.** Every pipeline starts with the question "what information exists at decision time?" answered *before* the strategy is written. If the answer needs future data, the strategy dies in design, not in gate 0.
2. **The leak registry is constitutional.** No PnL number enters the record without a declared information set (`t-1` / `day-t` / `none`) and a live-replicability flag; day-t ⇒ not live, enforced by test. New experiments inherit this the way they inherit the sandbox policy.
3. **Pre-register kill criteria before the first run, and make them cheap to fail.** e008's scope did this right: signal, data ceiling, and three kill bars written *before* the fetch. It died in one afternoon for the cost of a verdict script. That is what a healthy kill looks like.
4. **Suspicion scales with roundness.** 98.8% WR, PF 62.6, "worst-5% day still positive" — the smoother the story, the harder the look. Real books have ugly tails. A future search treats any WR > 85% on a credit book as presumptively broken until the information-set audit clears it.
5. **The t+1-fill hard rule is permanent.** Signal at bar t, fill at bar t+1's observable quote, with the quote's freshness recorded. Every backtest in this sandbox will carry it from now on; drift gets measured, not assumed away.
6. **One data class per question.** e008 died not of look-ahead but of *observability* — the only data class that can see the signal (sporadic rolling-window bars) cannot carry the fills. Match the data's freshness and completeness to the signal's clock before falling in love with a hypothesis.

## 5. Where the search actually stands

- **Dead:** the condor family in all forms (day-t walls convicted: e001 −₹232,823, e002 −₹140,520, breach spread 4 trades/−₹309 at gate 0); intraday wall flips on this data class (FINAL, full 576-session sweep: 638 flips at 111.9/yr but **15/638 = 2.4% fillable** — all three kill criteria failed; median wall-OI age at decision 75 min).
- **Closed:** the wall family is exhausted on every observable data class — day-t EOD walls (the leak), t-1 bhavcopy walls, opening-OI walls, intraday fresh flips. The one untested source is a live chain-snapshot feed with per-minute freshness: a production-infrastructure decision, not a different backtest. No further wall backtests are warranted.
- **Unconditional:** collect the collateral yield; keep the shadow runner logging; keep the suite green.

The sandbox spent its fortnight buying the most expensive-sounding thing in quant research — **a falsified favorite** — and paid in compute instead of capital. That trade is repeatable only if this file stays true.
