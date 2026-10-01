# PREREG — e010: one frozen credit spread + a LightGBM when-to-trade gate

Pre-registered 2026-10-01, **before any gate code exists** (this file is the
first commit in `e010_ml_gate/`). Template: [../PRE_REGISTRATION_TEMPLATE.md](../PRE_REGISTRATION_TEMPLATE.md).
Status: **AWAITING OWNER REVIEW — do not run until approved.**

The question this answers: *"one strategy, frozen structure, ML decides only
whether to trade it — does a LightGBM when-gate produce a positive book at
2–3 trades/month?"* This is the program's one untested cell: e002 gated a
**multi-strategy selection** (which the leak hid inside); nothing so far has
gated a **single fixed structure with a leak-free label**.

## 1. Hypothesis

- **Claim:** conditional — IF days when a frozen bear credit spread wins are
  distinguishable from days it loses using only t-1 observables, THEN a
  LightGBM when-gate that trades ≤ 2–3×/month beats both the always-on book
  and zero.
- **Mechanism (why should this edge exist?):** premium crush is not IID —
  gap risk, IV level, and positioning (PCR/OI skew) vary measurably the day
  before; if the model can identify calm, high-theta days it should keep the
  crush and skip the gap days.
- **Why it might be an artifact:** three adjacent cells already died — e002
  (selection on leaky labels: +794k frozen → −141k honest), e003 (no
  per-trade discriminative signal exists: Brier ≈ base rate), e004 (the base
  structure itself loses: bull −₹314k / bear −₹147k). This time the label is
  wall-free so the e001-family leak has **no vector in** — the honest prior
  is still LOW.
- **Honest prior:** low. Expected outcome: dead, closing the program's last
  cell.

## 2. The frozen structure (NOT tuned — inherited from e004's tested config)

One archetype only: **BEAR credit spread** (the milder loser of the two
wall-free books; bull is reserved as a pre-registered mirror variant, run
only if BEAR dies for a *capacity* reason, never as a rescue sweep).

- **Legs** (`_legs_for` BEAR branch, [e004/replay_intraday.py](../e004_intraday_replay/replay_intraday.py)):
  BUY ATM put, SELL 150-pt lower put, strikes set from the **09:15 open**,
  rounded to the 50-point strike grid (the open is observable at entry; no
  wall input anywhere — this is the leak-proofing).
- **Pricing** (frozen): fixed single IV per day from the t-1 straddle
  (`_iv_from_straddle`), BS leg prices, `dte = max(days_to_expiry, 0.5)`.
  Accepting e004's known first-order limitation (no intraday vol response)
  in exchange for a label with zero reconstruction freedom.
- **Exits** (frozen `EXIT_RULES["BEAR"]` = (0.35, 0.70)): SL at 0.35× credit,
  target at 0.70× credit, else 15:30. Intra-bar conflict: STOP wins.
- **Costs** (frozen): `calculate_friction` (the same model whose 23×
  slippage breakeven is certified) — no net number is read before friction.
- **Entry**: first 5-min bar (09:15–09:20 open), the paper-trade-validated
  fill discipline.

Every number above was frozen in e004/v6 **before this PREREG**; none may be
edited by this experiment. Changing any of them post-hoc converts the run
into a sweep, which is forbidden by §4.

## 3. The frozen gate (the only thing this experiment builds)

- **Model:** LightGBM classifier (`lgbm`), exactly one.
- **Features (frozen list = e002's 16 `FEATURE_COLUMNS`, all test-pinned
  t-1 — [e002/features.py](../e002_regime_models/features.py)):**
  `fut_prev_ret, fut_prev_range_pct, fut_prev_gap_pct, gap_open_pct, mom5,
  mom10, range5_mean_pct, pcr_t1, pcr_t2, pcr_chg, delta_oi_skew,
  straddle_pct, straddle_pct_chg, wall_call_dist_pct, wall_put_dist_pct, dow`.
  (The two wall features are t-1 EOD — observable before 09:15, a different
  and honest source from the convicted day-t walls.)
- **Label:** the frozen structure's own daily net_pnl > 0 (1/0) — wall-free,
  path-simmed, friction-inclusive. No selection label from any other book.
- **Walkforward (frozen):** expanding window, **yearly refits**, first OOS
  year = the second year of data; 6+ OOS years expected. Params frozen:
  400 trees, lr 0.05, num_leaves 31, min_data_in_leaf 40 (e002 defaults;
  NO tuning, no early stopping on OOS, no feature selection).
- **Trade rule (frozen):** trade day t iff P(win) ≥ **0.55**. This threshold
  is chosen once, before the run, from the calibration property alone
  (predicted-vs-actual on a purged validation tail of the training window)
  — never from OOS PnL. Expected cadence ~2–3 trades/month; there is **no
  minimum-activity rescue**: a gate that trades less is simply a dead gate.

## 4. Kill criteria (fail-only; any one kills e010; no rescues)

| # | Bar | Value | Rationale |
|---|-----|-------|-----------|
| 1 | OOS net | **> ₹0** pooled across all OOS years, after friction | the only meaningful absolute bar |
| 2 | Edge | **PF ≥ 1.5** with **n ≥ 30 OOS trades** | the family bar; below n=30 the run is "unjudgeable", not "promising" |
| 3 | Signal exists | gate's OOS Brier **strictly better than the base rate** (always-predict-majority) | if the gate can't discriminate, a pass on 1–2 is luck |
| 4 | Beats lazy baselines | OOS net ≥ both (a) always-on bear book and (b) 2-per-month random trade days, same sizing | the gate must add value over not gating |
| 5 | Capacity sanity | OOS trade days ≥ 1/year | a gate that never trades is a refusal, not a strategy |

Sweeps are forbidden: no threshold tuning, no feature additions, no
alternative structures, no param variants. One run, as frozen.

## 5. Sanity bars (pre-declared)

- Any WR > 85% or PF > 10 → audit before belief (family rule).
- Results reported per-OOS-year (stability), plus pooled; a single year
  carrying the entire net is reported as such.
- n < 30 → verbatim "unjudgeable", no averaging into a story.
- Leak registry: `run_gate.py` registers `info: t-1 / live: True` **in its
  first commit**, before any PnL number is committed.

## 6. Cost & machinery

- **Reuse:** features (test-pinned t-1 builder), path sim, friction, lot
  table, walkforward template (e002/walkforward_dte.py), registry. New code
  is one gate script + README + tests — ~half a day.
- **Compute:** minutes on cached features; no fetches.
- **Self-terminating:** the kill bars decide; no human judgment call at the
  end.

## 7. Verdict protocol

README verdict-first with the §4 table; changelog v24 records PASS or FAIL
identically; a FAIL is a result and gets full documentation. If PASS: the
next step is the handoff's paper-trade gate on live fills — never straight
to orders.

## 8. Amendments

- 2026-10-01: initial pre-registration. No gate code exists.
- 2026-10-01 (pre-run correction, no results exist yet): the initial text was
  internally contradictory — it named the structure a "credit spread" (the
  owner's explicit request) but inherited e004's BEAR legs, which are BUY ATM
  put + SELL 150-pt-lower put = a **debit** spread. Resolved toward the
  owner's request: legs are **SELL ATM put + BUY ATM−150 put (net credit)**;
  the frozen exit fractions apply to the credit (SL 0.35×credit, target
  0.70×credit — the same convention e004 applies to abs(outlay), and the same
  fractions-of-credit convention e005 uses for its credit condor). The caveat
  that e004's exit fractions were themselves sweep-selected in v6 applies
  unchanged. Everything else (features, gate, walkforward, kill bars, no-
  sweep rule) is untouched. Label must be recomputed for the credit legs
  (e004's artifact holds debit-spread rows only); `simulate_day` is
  structure-agnostic and reused as-is.

## 9. Verdict

- *Empty by design. Fills only after the run.*
