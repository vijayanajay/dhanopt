# e030 — Calendar-Spread Credit-to-Fee Pre-Check

**PREREG-frozen: 2026-10-03, BEFORE any code in this directory.**
Machine-checkable copy: `test_e030.py::test_prereg_is_frozen_before_the_gates_exist`.

## The question

Phase 7.3 (`e023_vol_surface`) is the **only** item on the roadmap that is not
blocked on missing data — everything else in Phase 7 needs a partition the repo
does not have (§2.1). Its proposed structure is:

> Short front-week ATM straddle; long next-week ATM straddle. Hold to front
> expiry. Trigger when `Slope_term = IV_front − IV_next > P90`.

The repo has already written down, twice, a mechanism that predicts this dies
before any PnL is computed:

- **§5.5 D:** "the drawdown floor is the flat per-order fee treadmill, not
  convexity… *The credit-to-fee ratio, not the position size, is the binding
  constraint.*"
- **§2.2:** every Phase 7 test needing absent data "is a data project wearing a
  research project's clothes."

**This experiment never computes PnL.** It is a zero-leg arithmetic pre-check:
does the calendar spread's gross credit even clear its own transaction costs?
If it does not, Phase 7.3 is struck in an hour instead of a month of code, and
the plan's next unblocked item is named honestly.

This is **invariant 5.14 applied as a pre-registration gate** rather than a
post-mortem lesson. It is the cheapest possible test of the hypothesis, and it
runs on data already on disk.

## What is NOT being claimed

- **No expectancy, no Sharpe, no PnL, no direction.** A positive credit
  distribution says only that the spread is *financially possible*. Whether the
  trade has an edge is a separate question this experiment does not ask.
- **No implied vol is computed.** The trigger in §7.3 is defined on
  `IV_front − IV_next`. This experiment measures the **premium** difference
  directly, which is the quantity that actually pays the bill and requires no
  model. Premium is the input; IV is a derived opinion about it.
- **No live fill claim.** Bhavcopy closes are not executable (§4.3 standing
  caveat). Friction includes the modelled slippage buffer, so this is a floor.

## The structure being costed

Four legs, one lot, ATM strike `K` chosen as the strike nearest the settlement
spot inferred from the front ATM straddle (§Method 3):

| # | Expiry | Type | Action |
|---|---|---|---|
| 1 | front | CE | SELL |
| 2 | front | PE | SELL |
| 3 | next | CE | BUY |
| 4 | next | PE | BUY |

Gross credit in index points:

    credit_pts = (front_CE + front_PE) − (next_CE + next_PE)

A calendar pays only when this is positive, i.e. when the front carries a higher
premium than the back — the inverted term structure §7.3 proposes to sell. **On
a normal upward-sloping Indian index term structure this is negative on most
sessions, and that is a result, not a failure to load data.**

Round-trip friction comes from the shared engine
`core/friction/zerodha.calculate_friction` with `config.SLIPPAGE_POINTS_PER_LEG`
— **not a copy.** Two copies of a cost model is how e026 and e027 each carried
the same chain-loader bug (invariant 5.14 corollary). Brokerage, STT, exchange,
SEBI, stamp and GST are all that engine's; this experiment does not restate
them.

## Method

1. **Sample.** Every session in `data/historical/` (1,415 partitions).
2. **Expiry resolution — per session, from that session's own partition**
   (`core.feeds.bhavcopy.front_expiry` on the typed `expiry_date` column from
   `with_expiry_date`). Front = first expiry ≥ trade date; next = the expiry
   after it. Both must exist. **Never a string compare** — that is e028.
3. **Spot.** Inferred from the front ATM straddle, not from an external series,
   so the strike ladder and the spot used to pick it cannot disagree. Fail-closed:
   if no straddle bracket exists the session is excluded and counted.
4. **ATM strike.** The listed strike nearest the inferred spot.
5. **Legs.** `close` for all four legs, era-correct lot from
   `experiments/common/lots.lot_for_date`. **A session missing any leg is
   EXCLUDED, never interpolated.**
6. **Coverage is published before any result** (invariant 5.14): sessions
   considered / excluded, broken out **per year**, before the credit
   distribution is quoted. A coverage number in aggregate would hide exactly
   the shape that betrays an encoding — the e028 failure.

## Gates

Failing any gate below is a valid, reportable outcome. **The bars are frozen
now and will not be moved after the numbers are seen.**

| # | Gate | Bar |
|---|---|---|
| **0** | **Control: friction engine** | `calculate_friction` on a hand-computed 4-leg case reproduces the arithmetic exactly, and e018's measured 0.51 pts/leg condor breakeven is reproducible from the same engine. |
| **1** | **Contract identity** | 0 mismatches. Front/next expiry re-derived per session; 0 sessions where front == next; ATM strike present in the listed ladder. |
| **2** | **Input coverage, published first** | ≥ 90% of sessions resolve all four legs, **reported per year**. Below that, stop — a coverage failure is the answer and no credit number is quoted. |
| **3** | **The kill gate — credit clears costs** | Median `credit_pts > 0` **and** fraction of sessions with `credit_pts > friction_pts` **> 50%**. |
| **4** | **Edge per trade at a realistic hit rate** | `median(credit_pts) ≥ 3 × median(friction_pts)`. |

### Reading the verdict

- **Gates 3 or 4 fail → Phase 7.3 is STRUCK before code.** The structure cannot
  pay its own transaction costs, so no signal, no surface fit and no exit study
  can rescue it. This is the expected outcome and the reason the check exists.
- **Gate 3 passes but 4 fails → MARGINAL.** Report the credit distribution and
  state that it clears costs on a majority of sessions but leaves under 3×
  cover, which is inside the roundness band of §5.4. Still not a book.
- **All pass → NOT VALIDATED.** It becomes *eligible* for a real PnL
  experiment with its own PREREG. "Clears friction" is a precondition, never a
  result.

## Kill consequence

A strike here **removes the only unblocked item on the Phase 7 roadmap.** That
is the point, not a loss. The honest outcome of that removal is that Phase 7 is
entirely data-blocked and the program has one certified-positive flow: the
collateral yield of §Phase 1.

## Artifacts

`artifacts/verdict.json` — every gate, coverage per year, the credit
distribution, and the friction breakdown at the median session.
`artifacts/session_credit.csv` — one row per resolved session.
