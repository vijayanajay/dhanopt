# Experiment pre-registration — copy this file before writing any code

Copy into the new experiment folder (e.g. `e009_<name>/PREREG.md`) and fill
every field **before** writing fetch/model/backtest code. A blank field at
code time means the experiment does not start. Amend only by appending a
dated line at the bottom — never edit a filled section after results are
seen. The rules encoded here are the ones this sandbox paid for; rationale
in [../RETROSPECTIVE.md](../RETROSPECTIVE.md), invariant enforcement in
[common/leak_registry.py](common/leak_registry.py).

---

## 1. Hypothesis (one paragraph, falsifiable)

- **Claim:** `<e.g. "walls move early and informatively during the session; a strategy reacting to X beats costs">`
- **Mechanism (why should this edge exist?):** `<the economic story, not the backtest story>`
- **Why it might be an artifact:** `<name the leak, the survivorship, the convention that faked it before>`
- **Honest prior:** `<low/medium/high and why — the family's prior failures count against it>`

## 2. Information set (the leak question, answered first)

- **What does the decision at bar t actually see?** `t-1 | day-t | bars<=t | live-chain`
- **Fill rule:** signal at t, fill at **t+1 open or later** — no same-bar fills, ever.
- **Leak-registry entry to add:** module, `info` set, `live` replicable (yes/no + note).
- **If day-t anything:** it is a research instrument, not a strategy. Say so here and stop pretending.

## 3. Data class (match the data's clock to the signal's clock)

- **Source + freshness:** `<what timestamp does each field carry, and how stale can it be at decision time?>`
- **Completeness ceiling:** `<what can this source NOT see — e.g. rolling-window strikes beyond ATM±10, delisted contracts>`
- **Observability-vs-fill check (the e008 kill):** what fraction of signals will have their required inputs observable *within the fill window*? If you cannot estimate this before the run, the run starts with measuring it.
- **Marks validation plan:** how will you prove the prices are real before trusting any PnL? (bhavcopy cross-check, marks sweep, or prior certified validation you reuse.)

## 4. Kill criteria (numeric, one-sided, written now)

Any one of these failing kills the experiment. Fail-only — no criterion can be
reinterpreted as a pass after results. Estimate each bar's value from data you
already have, not from the run you are about to do.

| # | Bar | Value | Why this number |
|---|-----|-------|-----------------|
| 1 | Capacity | `<e.g. >= 15 tradeable events/yr>` | `<e.g. below this the book cannot pay its fixed costs>` |
| 2 | Edge | `<e.g. PF >= 1.5 net of friction, with n >= 10>` | `<...>` |
| 3 | Composition / observability | `<e.g. >= 50% of signals fillable at t+1>` | `<...>` |

**Verdict protocol:** README written verdict-first with the table above; the
changelog entry reports PASS or FAIL either way; a fail is a *result*, not an
embarrassment, and gets the same documentation as a pass.

## 5. Sanity bars (run on every result, pre-declared here)

- Any WR > 85% on a credit book is **presumptively broken** until the information-set audit clears it.
- Suspicion scales with roundness: PF > 10, "worst day positive", smooth equity — each earns a specific audit before belief.
- Friction and slippage measured, not assumed: state the per-leg cost model and the breakeven multiple (this sandbox's was 23×) before reading net PnL.
- Lot-era table from NSE circulars, not memory; decision labels shifted by the calendar rules in effect that era.
- n < 10 means unjudgeable — report it as unjudgeable, do not average your way to a story.

## 6. Cost & machinery (the lazy-senior check)

- **Does this need to be built at all?** `<which rung of the reuse ladder fails before new code>`
- **Reuse inventory:** `<fetchers, sims, friction, shadow runner, gating that already exist>`
- **Incremental cost:** `<hours/days; if the fetch alone is > one day, justify why the prior warrants it>`
- **Self-terminating?** `<the experiment must die by its own criteria without a human deciding to stop>`

## 7. Amendments (append-only, dated)

- `<none yet>`

## 8. Verdict (filled after the run; never before)

- **Result:** `<PASS | FAIL on criterion N>` with the numbers against each bar.
- **What died / what survived:** `<the data class dies, not necessarily the hypothesis — name what a future attempt would need>`
