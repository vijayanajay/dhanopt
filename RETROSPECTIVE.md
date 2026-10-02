# Sandbox Retrospective — Two Leaks, One Species (2026-10-02)

**TL;DR: two measurement bugs, the same species, and the sandbox's own pre-registered gates killed both before either cost a rupee. Every strategy number this sandbox ever celebrated was produced by a bug. The machinery is the asset; the strategies were the noise. This file is the permanent record and the rulebook for the next search.**

The second leak (contract identity, found 2026-10-02) voided the sandbox's second-best result and every experiment built on it. This revision is the complete record: e001–e020, the surviving inventory, and the rules the next search inherits.

---

## 1. What the day-t wall leak actually was

One convention, inherited silently through four generations of code: **walls = max-OI strikes of day t's own EOD option chain**. It entered at e001 (mirroring the original engine's labels), was kept by e005 deliberately ("leg-for-leg comparison to the frozen labels"), and became load-bearing when the breach book made the wall-crossing test its entire signal. The problem: the entry happens at 09:15, but the walls are computed from OI as it stood at **15:30** — 6 hours of information the live trader cannot have. The "spot gapped over the wall" event exists only against walls that moved into the way *during* the day being traded. The book's entire edge was the wall update itself.

Three properties made it dangerous, in ascending order of lesson value:

1. **It was invisible to every statistical gate.** Calibration was excellent (Brier ≈ 0.20) *because* the models faithfully predicted the leaky labels. Win rates of 98.8% raise suspicion only after a leak is suspected; before that, they look like skill. **Calibration measures fidelity to the labels, not truth of the labels.**
2. **It compounded through inheritance.** e001 → e002 labels → e005 walls → breach book → e006 compounding → the handoff. Each consumer added a "caveat" line, none re-derived the foundation. By the time the number reached ₹940,697, six documents vouched for it and none had checked it.
3. **It survived because the sandbox measured the right things on the wrong object.** Marks were validated to the paisa, friction was real, exits were honest — every *price* was genuine. Only the *selection signal* was fictional. Honest components ≠ honest assembly.

## 2. The second leak: contract identity

[experiments/e011_vrp_delta_hedge/volatility.py](experiments/e011_vrp_delta_hedge/volatility.py) built its implied-volatility signal by taking **the expiry nearest to day t-1**, inverting that ATM straddle, and then shifting the result by one row. The shift was correct; the *instrument* was not. The contract tradable on day t is the expiry nearest to **t**. When t-1 was an expiry day, those are different contracts, and the pinned straddle got inverted with a tenor ~1/5 of its real life. `e018` re-derives the same measurement on 293 E011 signal sessions:

| | E011 (convicted) | contract-identity-correct |
|---|---:|---:|
| mean signal IV | 0.476 | **0.163** |
| max signal IV | 1.929 | **0.473** |
| sessions IV > 1.00 | 35 | **0** |
| sessions IV ≥ 0.60 | 68 | **0** |
| mean tenor credited | 0.95 days | **4.71 days** |
| roll-day enrichment in the signal | **2.55×** | **1.00×** (none) |

Three things make this the more instructive of the two leaks:

1. **The published PnL was not inflated by optimism — it was measured on a contract that did not exist.** +₹7,43,572.25, Sharpe 2.85, PF 3.99 across 293 trades. Every rupee of it is a bisection artifact.
2. **The gate selected on the bug.** Roll sessions are 21% of trading days but **54%** of E011's signals — the entry rule fired 2.55× more often on exactly the days its own inversion had broken. The strategy was not trading a regime; it was trading its instrumentation error. Correct the instrument and the selection disappears entirely.
3. **It propagated the same way the wall leak did.** e015, e016 and e017 each froze e011's artifacts and reasoned carefully *on top of them* — a book combination, a wings test, a sizing study, three papers deep. The contract-identity defect was inherited silently by each. All three are void. e013 is clean: it replays only genuine `dte ≤ 1` sessions, so the contract identity holds by construction.

**Why it survived the first leak's autopsy.** The sandbox had built a whole apparatus against `t-1` discipline — registry rows, `t+1`-fill tests, shift-pinned feature tests — and all of it was satisfied. `t-1` is a claim about **when** an input was observed. It says nothing about **which instrument** the observation belongs to. A shifted frame can hand you yesterday's tenor. The first bug was a wrong *time*; the second was a wrong *object*, wearing a correct timestamp.

**Same species, stated once:** both bugs are a silent convention inherited through generations of consumers, each of which added a caveat line instead of re-deriving the foundation. A convention cannot stop this, because the convention is what broke. **A test is the only thing that stops it** — and the test has to be written against the *quantity*, not the intent:

- `test_front_expiry_roll_is_not_yesterdays_contract` — the front expiry is resolved out of the trade date's own partition, so identity is a fact, not an inference.
- `test_tenor_matches_the_contract_not_a_stale_offset` — observed tenor must strictly *lead* traded tenor; e011's failure was the opposite sign.
- `test_no_degenerate_iv_in_the_dataset` — the signal's own distribution is checked. **A mean IV of 0.476 with a max of 1.93 is not a strategy result, it is a bug report.** Nobody had ever plotted the shape of the signal; every gate in the repo looked at PnL.
- `_identity_ok` re-derives the intended expiry from the trade date's partition on **every trade** and gate 4 fails the run on a single mismatch. 0 violations across 141 trades.

## 3. How they were caught — and why that part worked

Neither leak was caught by reviewing numbers. Both were caught by **asking a question the frozen pipeline had never asked.**

The wall leak: the paper-trade harness asked *what could the trader actually know at 09:15?* Walls from t-1 EOD bhavcopy — the only observable source — collapsed the book (57 trades, −₹27.5k). Pre-registered gate 0 finished the proof with the freshest possible observable source (opening-OI walls via the per-bar-OI API): 4 trades, −₹309, plus the decisive diagnostics — opening walls differ from t-1 walls on 74% of days (no "stale copy" excuse) and the opening structure is valid on 244 of 249 "breach" days (the signal has nothing to fire on).

The contract-identity bug: a **brainstorm** asked a question no gate ever had — *which contract is this PnL actually about?* It was not a review pass, not a refactor, not a data audit. It was the question "shifted by one, is that the same object?" — and no test in the repo asked it, because every test asked the same question the code did.

Then the fix was deliberately **pre-registered as a hypothesis test, not a patch**: e018's PREREG froze six gates on Option 1's own terms (weekly 3–7 DTE condor held to expiry) before any code ran. The fix got a verdict instead of a pass. It failed — and that failure is the reason we know the fix is real rather than merely plausible: a fix that had been tuned to reproduce +₹7.43L would have been a worse fix.

The structural lesson, twice over: **the gates that worked were the ones written as commitments before the answer was known.** The gates that failed were diagnostics run on the artifact itself (calibration, PF, WR, marks, Sharpe).

## 4. What survives untouched (the honest inventory)

| Survives | Why |
|---|---|
| **Contract-identity engine** ([e018 volatility_fixed.py](experiments/e018_vrp_weekly/volatility_fixed.py)) | Clean IV distribution, roll-day enrichment eliminated, 1,410 sessions, 3 minutes to rebuild. Signal-independent, and the fix e011 needed. |
| **Hold-to-expiry mark path** (e018) | Entry at day-t EOD close, settle at the expiry date's EOD close, marked on real bhavcopy prices with **no Black-Scholes reconstruction anywhere**. No PnL in that book depends on a model's opinion of a price. |
| **The arithmetic-impossibility audit** (e018) | A condor's maximum loss is closed-form. Any backtest whose marks violate it has a pricing bug. Cheap, general, and it caught a ₹104k phantom loss (expiry-day bhavcopy `close` is a *stale last-trade* price — 0.30 on options expiring at 0.00 — on 34 of 141 trades). Marking expiry as intrinsic-vs-futures-close moved the book −₹165,194 → −₹61,306. Net changed; verdict did not. |
| **Marks validation (e005 Add. 6–7)** | Validated *prices*, not signals: 249 sessions swept, traded-pair credit certified on 20 (16 exact to the paisa), worst diff +23.5 pts — inside the 34.6-pt slippage breakeven. |
| **Friction / slippage machinery** | Core Zerodha friction, the 1.5 pts/leg model, the 12× DD boundary, the 34.6-pt/leg breakeven method — signal-independent arithmetic, now with a measured pre-live drift estimator. |
| **The 5-min store + path simulator** | Identity-validated (EOD exits reproduce e001 leg-for-leg); reusable for any intraday book. |
| **The free cash price store** ([e019 data/cash](experiments/e019_momentum/)) | 1,420 sessions × 6,475 symbols, 215 MB, free NSE daily bhavcopy, idempotent dual-URL downloader, survivorship-safe by construction. Reusable for any cross-sectional equity study. |
| **Corporate-action back-adjustment** (e019 engine) | 453 events across 397 symbols, back-adjusted at clean 1:1/1:2/1:3/1:4 ratios. RELIANCE's 1:1 bonus reads as a −49.8% crash in raw bhavcopy and becomes +0.98%. Every momentum or mean-reversion study on raw Indian EOD data needs this and almost nobody does it. |
| **Point-in-time liquidity** (e019 engine) | Trailing-252 median turnover ending t-1, computed once instead of 1,100 times. |
| **The anti-beta gate** (e019 gate 6, e020 gate 5) | A long-only book in a bull market earns 21% CAGR at 1.15 Sharpe from beta alone. Gating on *excess Sharpe vs a same-universe equal-weight benchmark* is the only reason e019 and e020 produced a decision instead of a celebration. |
| **The death-rate diagnostic** (e020 gate 6) | What fraction of a book's holdings stop trading within the holding period, versus the universe. No standard backtest reports it; it is the mechanism that explained e019's −55% drawdown. |
| **The control-reproduces-predecessor pattern** (e020) | Re-running e019's exact configuration inside e020 and landing on **excess Sharpe −0.81 to the decimal** is the strongest single piece of evidence in this repo that a backtest engine measures what it claims. |
| **e004's spread verdicts** | Bull/bear spreads are net-negative under path exits — wall-free labels, unaffected. A confirmed *avoid*. |
| **e006's constraint semantics** | Margin ladder, daily-stop clamp, monthly breaker — tested machinery awaiting a real trade list. |
| **e012's skew verdict** | Wall-free labels, unaffected by either leak. Ratio spreads bleed: PF 0.13. A confirmed *avoid*. |
| **e014's maker verdict (E013 legs only)** | Passive all-or-none entry is strictly worse than taker on the one book that survived (EV +₹1,018 vs +₹2,149; 27.3% of taker, bar was 60%). Spread-crossing is structural. |
| **The shadow runner + leak registry + pre-registration discipline** | The process layer: daily evidence accumulation, structural leak guards, commitment-first gates. |
| **Negative results as knowledge** | The hypothesis space is now pruned hard — see §6. |

**Expected honest returns today: ₹0 from any strategy, ~₹10.6k/yr gross (~₹7.4–10k post-tax by bracket) from collateral yield on the idle ₹2L at Oct-2026 rates** (overnight fund pledged for margin; full mechanics in [COLLATERAL_PLAYBOOK.md](COLLATERAL_PLAYBOOK.md) — the ₹10–13k earlier figure was written at repo 6.0–6.5%).

## 5. What a clean strategy search does differently

1. **Live-replicability is the design constraint, not a validation step.** Every pipeline starts with "what information exists at decision time?" answered *before* the strategy is written. If the answer needs future data, the strategy dies in design, not in gate 0.
2. **The leak registry is constitutional.** No PnL number enters the record without a declared information set (`t-1` / `day-t` / `none`) and a live-replicability flag; day-t ⇒ not live, enforced by test. New experiments inherit this the way they inherit the sandbox policy. The E011 conviction is a registry row now, so it cannot be quietly inherited a third time.
3. **Pre-register kill criteria before the first run, and make them cheap to fail.** e008's scope did this right: signal, data ceiling, and three kill bars written *before* the fetch. It died in one afternoon for the cost of a verdict script. e019 died the same way, for the cost of a data download. That is what a healthy kill looks like.
4. **Suspicion scales with roundness.** 98.8% WR, PF 62.6, a max IV of 1.93 — the smoother the story, the harder the look. Real books have ugly tails. Treat any WR > 85% on a credit book, or any implied volatility above 1.0, as presumptively broken until the information-set audit clears it.
5. **The t+1-fill hard rule is permanent.** Signal at bar t, fill at bar t+1's observable quote, with the quote's freshness recorded.
6. **One data class per question.** e008 died not of look-ahead but of *observability* — the only data class that can see the signal cannot carry the fills. Match the data's freshness and completeness to the signal's clock before falling in love with a hypothesis.
7. **Name the instrument, then shift the frame.** A `shift(1)` is a claim about *when*, not *what*. Any signal row must be able to answer "which contract, which strike, which expiry, which tenor" from the trade date's own partition, and a test must re-derive that answer per row. Corollary: **publish the signal's distribution before its PnL.** A histogram costs nothing and has now caught a bug that moved ₹7.43 lakh.
8. **Benchmark first; gate on excess, not on level.** Every long-only equity book is reported against a same-universe equal-weight benchmark over the same days with the same costs, and the bar is on excess Sharpe. "24.8% CAGR" and "3.1% CAGR" in the same table were both beta; only the benchmark column says so.
9. **A control beats a diagnostic.** Two cheap checks that produce decisions where fifty PnL metrics produce nothing: (a) *the successor must reproduce the predecessor's number to the decimal before its new numbers are believed*; (b) *any structure with a closed-form maximum loss must be checked against it per trade* — violations are pricing bugs, not tail events.

## 6. The complete record — every experiment, its honest verdict (final, 2026-10-02)

| # | Question asked | Frozen result | Honest verdict after audit | Status |
|---|---|---|---|---|
| e001 | Rule condor book, leak-free replay | +₹152,346 | **−₹232,823** on t-1 walls — the day-t convention; wall-free spread legs lose (verdict stands) | DEAD |
| e002 | ML strategy selection (LightGBM/logistic) | ml_logistic+dte **+₹793,906** | **−₹140,520** on t-1 labels — the edge *was* the leak; features themselves clean | DEAD |
| e003 | Meta-labeling per-trade filter | dominated | Brier ≈ base rate — no per-trade signal exists | MOOT, confirmed by e010 |
| e004 | 5-min path replay, 3 archetypes | spreads negative | bull −₹314k / bear −₹147k, **wall-free labels — stands untouched** | CLOSED (negative) |
| e005 | Theta-aware condor + breach book | +₹288k–₹1.09M | day-t walls throughout; family convicted by e007/e001-audit; machinery (pricing, exits, marks) survives | DEAD (machinery survives) |
| e006 | Compounded live projection | CAGR 51% | compounded a falsified trade list — arithmetic valid, object void | MOOT |
| e007 | Gate 0: opening-OI walls | — | **4 trades / −₹309 / PF 0.96** — the certification that killed the book | SUCCESS (as a gate) |
| e008 | Intraday wall-flip (live-fresh signal) | FAIL 3/3 bars | flips exist (111.9/yr), **2.4% fillable**, median wall-OI age 75 min — the data class dies, not the hypothesis | DEAD on observability |
| e009 | Live chain capture (per-minute freshness) | dormant | collector built to PREREG; clock ready; **no verdict possible for ≥6 months** | INSTRUMENT (running) |
| e010 | One frozen spread + LightGBM when-gate | FAIL 3/5 bars | gated −₹121k (PF 0.36) but **Brier beats majority** — discrimination without monetization; selection cut the loss 4.6× and landed negative | CLOSED (negative) |
| e011 | True VRP, delta-hedged ATM straddle | +₹7,43,572, Sharpe 2.85, PF 3.99 | **CONTRACT-IDENTITY BUG** — priced t's contract with t−1's expiry and tenor; mean signal IV 0.476, max 1.93, 35 sessions > 1.00; the gate fired 2.55× on roll days | **VOID** |
| e012 | Skew & 1×2 ratio spread | −₹98,802, PF 0.13 | wall-free labels; verdict stands — 4-leg friction turns +₹33/trade gross into −₹859/trade net | DEAD (confirmed avoid) |
| e013 | 0DTE pin harvest (iron fly) | +₹4,14,721, PF 9.41, DD 5.97% | **clean** — replays only genuine dte≤1 sessions, so contract identity holds by construction; fill feasibility unverified (needs e009 live chains) | **SURVIVING CANDIDATE** |
| e014 | Maker vs taker TCA | gates 2 & 3 fail | E013 legs stand (maker +₹1,018 vs taker +₹2,149, 27.3% < 60% bar); E011 arms void with the book | CLOSED (negative, on E013) |
| e015 | Book combination E011 × E013 | +₹11,58,293, Sharpe 4.14 | one leg void ⇒ the combined book is void; the 10-overlap-day margin breach survives as a *capital* fact | **VOID** |
| e016 | VRP-gated iron-fly wings | −₹1,56,941, DD 101.5% | inherits e011's mispriced signal; the wings finding (cap the tail, not the drawdown) is untested on a correct contract | **VOID** |
| e017 | Regime sizing + risk budget | sizing killed; 8% ceiling unreachable | sizing arithmetic is valid *on the frozen book*, but the book is void; "needs ₹6.4L capital" is a statement about a bug | **VOID** |
| e018 | Contract-correct VRP: weekly 3–7 DTE condor held to expiry | — | **−₹61,306, EV −₹435, PF 0.82, DD −₹96,835 (48.4%)**, 0 identity violations | DEAD (fix survives) |
| e019 | Cash momentum, monthly + daily, free EOD | — | **friction-decay premise falsified** — daily beat monthly 3.8× (12.0% vs 3.1% CAGR), costs ~3% of capital; equal-weight benchmark 21.3% / Sharpe 1.15; excess Sharpe **−0.81** | DEAD |
| e020 | Diluted top-decile momentum | — | control reproduced e019's −0.81 exactly; 24.8% CAGR but excess Sharpe **+0.04** — the return is beta; top-bucket names die **1.87×** more often | DEAD |

**Five ways to lose, now enumerated.** (1) *The signal was fiction* — e001, e002, e005. (2) *The PnL was measured on an object that does not exist* — e011 and its three inheritors; this is new, and it hides inside the others because a wrong object still produces plausible-looking numbers. (3) *Real but untradeable on observable data* — e008. (4) *Real, tradeable, and unprofitable because the structure pays less than it costs* — e004, e010, e012, e018, e019. (5) *Real, tradeable, profitable — and entirely beta* — e020, the newest and the sneakiest, because the CAGR column looks like a triumph and only the benchmark column is a verdict.

Two of these twenty experiments were not losses. **e013 is the one surviving candidate** (its fills have never been observed on live data — the 0.0% fill feasibility in e008's artifacts is an ATM-omission artifact, not a refutation), and **e009 is the instrument** that would resolve it. Everything else is a pruning.

## 7. Where the search stands

- **Void (measurement, not merit):** e011, e015, e016, e017. The work is not wasted — the conviction, the fix, and the four tests that hold the fix shut are the most valuable artifacts in the repo — but not one rupee of their published PnL may be carried into any future model, sizing table, or pitch.
- **Dead, with evidence:** every strategy family tested — condors on any wall source, directional spreads, ML selection on any label, ML gating on clean labels, wall-flip timing on every observable data class, skew ratio spreads, VRP as a weekly condor *on a correct contract*, and long-only cash momentum at both top-20 and top-decile concentration. A new idea must name which of the five loss modes it escapes.
- **Where the next search should not go:** further long-only work on the same Indian midcap cross-section. E020's beta decomposition says the signal is spent; the live cells are market-neutral momentum (3.7% net, Sharpe 0.58 exists but needs a borrow arrangement this repo cannot model honestly) or a genuinely orthogonal signal. For volatility, the binding constraint is not the edge — the corrected VRP is real (mean 0.048) — it is the **credit-to-fee ratio**: 8 leg-orders of round-trip friction against 75 points of weekly credit, breakeven half-spread 0.51 pts. Longer holds (2–4 weeks) or per-contract vol products are where a real premium could survive its own transaction.
- **Surviving machinery, ready to be the base of the next experiment:** the contract-identity engine, the hold-to-expiry mark path, the arithmetic-impossibility audit, the free cash price store, point-in-time liquidity, corporate-action back-adjustment, the anti-beta gate, the death-rate diagnostic, and the control-reproduces-predecessor pattern. That is a research platform, and it is what twenty experiments of failures bought.
- **Running:** e009's capture collector (code done, tests green) — starts producing evidence the moment its scheduled task is registered; Phase B evaluation is pre-contracted, not open research.
- **User actions pending (not research):** (1) register the e009 schtasks task (one command in the e009 README); (2) execute the collateral pledge (15 minutes, [COLLATERAL_PLAYBOOK.md](COLLATERAL_PLAYBOOK.md)). Until done, the account earns savings rates and collects no capture data.
- **The only certified-positive cash flow:** collateral yield, ~₹885/mo gross at Oct-2026 rates. Expected monthly return of the whole program today: **₹885, alpha component ₹0.**

The sandbox spent three weeks buying the most expensive-sounding things in quant research — **two falsified favorites** — and paid in compute instead of capital. It then spent a further day proving the last "but what if" (e010) rather than leaving it to haunt the next search. That trade is repeatable only if this file stays true — and as of this entry, nothing in it is waiting on a result that has not been either recorded or pre-contracted.
