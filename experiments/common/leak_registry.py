"""Cross-experiment leak registry (the v20 invariant).

The sandbox's defining failure: a day-t information convention survived six
experiments because each one inherited it silently and calibration could not see
label leaks. This registry is the structural answer: every module that produces a
net-PnL number someone could act on must DECLARE its decision information set and
whether its numbers are live-replicable. `test_leak_registry.py` enforces:

  1. completeness — every registry entry below covers a real module path;
  2. the invariant — a module declared to use day-t information must NOT be
     flagged live-replicable (that combination is how the +940,697 happened).

Static proof of shift-ness stays with the per-experiment tests (e.g.
test_day_t_feature_row_never_sees_day_t); the registry is the cross-experiment
invariant, not a parser. New experiments add a row here in their own PR — a PnL
number without a registry row is itself a test failure.
"""
from __future__ import annotations

# Information sets:
#   "t-1"   — decision inputs observable before day-t's open (shift-1 discipline)
#   "day-t" — decision inputs include day-t session data (intraday flips are a
#             SEPARATE declaration: t+1-fill rule must be stated in the module)
#   "none"  — descriptive/audit machinery, produces no actionable PnL claim
REGISTRY: list[dict] = [
    # e001 — frozen rule book; labels built on day-t EOD walls (inherited from the
    # original engine's convention; convicted by audit_e001_t1: -232,823 on t-1 walls).
    {"module": "experiments/e001_leakfree_replay/replay.py", "info": "day-t", "live": False,
     "note": "condor walls from day-t EOD OI; bull/bear legs wall-free (those verdicts stand)"},
    # e002 — features strictly t-1 (test-pinned); condor LABELS inherited e001's day-t walls.
    {"module": "experiments/e002_regime_models/features.py", "info": "t-1", "live": False,
     "note": "feature rows are shift-1 clean; labels joined from e001 carry the leak (Add. 7)"},
    {"module": "experiments/e002_regime_models/walkforward_dte.py", "info": "day-t", "live": False,
     "note": "predicts e001's leaky condor labels: +793,906 frozen -> -140,520 on t-1 labels"},
    {"module": "experiments/e002_regime_models/audit_labels_t1.py", "info": "t-1", "live": True,
     "note": "the audit itself: rebuilds labels on the observable wall source"},
    {"module": "experiments/e002_regime_models/audit_e001_t1.py", "info": "t-1", "live": True,
     "note": "e001 arithmetic on t-1 walls: rule-selected -232,823 (frozen +152,346)"},
    # e003 — meta-labeling on e001's labels; verdict was 'dominated' and stays moot.
    {"module": "experiments/e003_meta_labeling/meta_labeling.py", "info": "day-t", "live": False,
     "note": "inherits e001's condor labels"},
    # e004 — spread books wall-free (valid verdicts); condor column was a pricing artifact.
    {"module": "experiments/e004_intraday_replay/replay_intraday.py", "info": "day-t", "live": False,
     "note": "spreads: wall-free, verdict stands; condor column invalid (fixed-IV, pre-e005)"},
    # e005 — the endpoint-anchored replay and everything downstream of its walls.
    {"module": "experiments/e005_theta_condor/replay_theta.py", "info": "day-t", "live": False,
     "note": "prepare_day walls from day-t own-partition EOD OI (flagged as follow-up, now convicted)"},
    {"module": "experiments/e005_theta_condor/breach_spread.py", "info": "day-t", "live": False,
     "note": "the +940,697 headline: breach test reads day-t EOD walls = 6h look-ahead"},
    {"module": "experiments/e005_theta_condor/paper_trade.py", "info": "t-1", "live": True,
     "note": "the honest harness: t-1 walls, t+1-fill stress; found the collapse (57 trades, -27.5k)"},
    {"module": "experiments/e005_theta_condor/marks_validation_v2.py", "info": "none", "live": True,
     "note": "price validation only — verdict survives regardless of signal validity"},
    {"module": "experiments/e005_theta_condor/marks_sweep.py", "info": "none", "live": True,
     "note": "full-book price certification; survives"},
    # e006 — compounded projection of the breach book; inherits its signal.
    {"module": "experiments/e006_compound_sim/compound_sim.py", "info": "day-t", "live": False,
     "note": "simulator semantics valid and tested; the trade list it compounds is not"},
    # e007 — gate 0: the certification that killed the book.
    {"module": "experiments/e007_open_oi/fetch_open_oi.py", "info": "none", "live": True,
     "note": "data fetch: per-bar OI probe + 249 opening chains"},
    {"module": "experiments/e007_open_oi/build_book.py", "info": "t-1", "live": True,
     "note": "opening-OI walls are observable at 09:15 (bar-OI is timestamped intraday OI)"},
    # e008 — the first signal built UNDER the registry: information-legitimate
    # (bars <= t, t+1 fills) but killed on OBSERVABILITY — the rolling API serves
    # each strike sporadically, so flips are detectable only after their fill window
    # closes (0/34 fillable). day-t intraday signal, not live-replicable on this
    # data class; a live chain-snapshot feed would be a new declaration.
    {"module": "experiments/e008_wall_flip/fetch_walls.py", "info": "none", "live": True,
     "note": "data fetch: per-5-min chains for all 576 dte<=1 sessions"},
    {"module": "experiments/e008_wall_flip/build_signal.py", "info": "day-t", "live": False,
     "note": "intraday flips with t+1 fills (the hard rule) — dead on data observability, not look-ahead"},
    # e009 — the live capture the family was waiting for; PREREG-frozen before code (v22).
    {"module": "experiments/e009_wall_capture/capture_chains.py", "info": "none", "live": True,
     "note": "collector only: full-chain snapshots, no signal, no PnL; evaluation (Phase B) must register"
             " info day-t / live True with the t+1-fill rule before its first number"},
    # e010 — frozen single-structure gate; PREREG (with pre-run amendment 2) committed before any code.
    {"module": "experiments/e010_ml_gate/run_gate.py", "info": "t-1", "live": True,
     "note": "one LightGBM when-gate on e002's shift(1)-pinned features; label = frozen wall-free"
             " credit spread's own net_pnl (no day-t OI anywhere); fills at the traded day's 09:15 open"},
    {"module": "experiments/e010_ml_gate/label_spread.py", "info": "t-1", "live": True,
     "note": "label builder: ATM from the day's own 09:15 open (observable at entry), IV/dte from the"
             " prior-day partition exactly as e004; no wall input in the structure"},
    # e011 — True Variance Risk Premium (VRP) & Dynamic Delta-Hedging.
    # CONVICTED 2026-10-02 of a CONTRACT-IDENTITY defect: the signal inverted the
    # ATM straddle of the expiry nearest to t-1 and priced the t trade with that
    # expiry's tenor. The contract tradable on t is the expiry nearest to t; when
    # t-1 was an expiry day they differ, and the inverted "IV" was a bisection
    # artifact (mean 0.476, max 1.929; 35 sessions > 1.00). Published +7,43,572 is
    # void; e015/e016/e017 inherit it and are void-pending. Corrected by e018.
    {"module": "experiments/e011_vrp_delta_hedge/replay_vrp.py", "info": "t-1", "live": True,
     "note": "CONTRACT-IDENTITY BUG: priced todays contract with yesterdays tenor. "
             "Published net PnL is void; see e018_vrp_weekly for the corrected engine"},
    # e012 — Volatility Skew & Asymmetric Ratio Architecture.
    {"module": "experiments/e012_skew_ratio/replay_skew.py", "info": "t-1", "live": True,
     "note": "gated by t-1 25-delta skew >= 90th percentile; 1x2 ratio spread with path exits; killed (PF 0.13, -98.8k)"},
    # e013 — 0DTE Expiry Microstructure & Pin Dynamics.
    {"module": "experiments/e013_0dte_pin/pin_replay.py", "info": "day-t", "live": False,
     "note": "evaluated at 12:30 IST, fills at 12:35 Open; Pin Iron Fly Net +414k / PF 9.41; requires e009 live chain for execution"},
    # e018 — the CONTRACT-IDENTITY-CORRECT rebuild of the VRP book. Signal IV is
    # inverted from the ATM straddle of the expiry nearest to the TRADE date
    # (read out of t's own partition, so identity is a fact not an inference),
    # observed in t-1's partition; entry at day-t EOD close, held to the expiry
    # date's EOD close. Contract identity is re-derived and asserted per trade.
    {"module": "experiments/e018_vrp_weekly/replay_weekly.py", "info": "t-1", "live": True,
     "note": "gated by t-1 VRP >= p80 on the correct contract; 3-7 DTE defined-risk condor "
             "held to expiry; FAILED gates 2/3/5 (EV -435, PF 0.82, DD 48%) — the VRP does not "
             "survive correct contract identity at the weekly horizon"},
    {"module": "experiments/e018_vrp_weekly/volatility_fixed.py", "info": "t-1", "live": True,
     "note": "contract-identity-correct IV/VRP signal builder; front expiry resolved from the "
             "trade date's own partition, straddle read from t-1"},
    # e026 — the REAL-PRICE RE-AUDIT of e013's surviving candidate. Not a
    # strategy: the signal is frozen at e013's values and only the exit MARK
    # moves, from Black-Scholes to real bhavcopy option closes. Declared
    # day-t / live False because it does NOT improve e013's information set —
    # the real mark is a day-t EOD close, i.e. a price observed AFTER the 15:15
    # decision. Reading arm B as live-replicable would be a fresh leak.
    {"module": "experiments/e026_realmark_audit/audit_realmark.py", "info": "day-t", "live": False,
     "note": "e013 re-marked to real bhavcopy closes. Control reproduces published "
             "+414,721 / PF 9.41 exactly (gate 0). Real marks (valid sample, n=64): "
             "+61,842, EV +966, PF 16.67 — SURVIVES real marks but the published "
             "+4,14,721 is struck and must be restated. e013 is also NOT a 0DTE book: "
             "132/193 sessions are dte>=2 and carry 76% of the PnL. SUPERSEDED BY e028: "
             "that n=64 was half the tradeable sample (expiry-encoding defect, below); "
             "the corrected n=129 books -29,082 at 2.0 pts/leg"},
    # e027 — REALIZED SLIPPAGE on the restated e013 pin fly. Not a strategy and
    # not a signal: it characterises the COST of trading a signal that already
    # exists, so it declares info "none" / live True. Verdict UNRESOLVABLE —
    # breakeven is exactly 2.64 pts/leg, but no data on disk can measure the
    # real spread (Corwin-Schultz fails its own sanity gate at 1.71x the
    # option's price). Also records that the engine charges 0.75 pts/leg while
    # the actionplan has always stated 1.5.
    {"module": "experiments/e027_spread_realism/spread_realism.py", "info": "none", "live": True,
     "note": "slippage measurement only; no signal, no forward PnL claim. Control "
             "reproduces e026's +61,842.51 on n=64. Breakeven 2.64 pts/leg; book is "
             "+37,303 even at the plan's stated 1.5 pts/leg. CS estimator UNUSABLE here "
             "(reports spread > instrument price; 69% unmeasurable) — verdict is "
             "UNRESOLVABLE, and a broken upper bound is explicitly NOT read as a pass. "
             "SUPERSEDED BY e028: the n=64 sample was format-selected by the expiry-"
             "encoding defect, so 2.64 is not this book's breakeven"},
    # e019 — cash-equity momentum on free NSE EOD. Universe is the union of every
    # trading symbol (no index-membership list applied backwards => survivorship-
    # safe by construction); liquidity filter is a trailing-252 median turnover
    # ending t-1; signal is 12-1 momentum ranked on t-1; fills at the t close.
    {"module": "experiments/e019_momentum/engine.py", "info": "t-1", "live": True,
     "note": "cross-sectional 12-1 momentum on point-in-time liquid NSE cash names; FAILED "
             "gates 2/3/6 — net CAGR 3.1% monthly vs 21.3% for the same-universe equal-weight "
             "benchmark (excess Sharpe -0.81). Friction decay premise FALSIFIED: daily beat "
             "monthly 3.8x and costs were ~3% of capital"},
    {"module": "experiments/e019_momentum/download_cash.py", "info": "none", "live": True,
     "note": "data fetch: free NSE daily cash bhavcopy, 1420 sessions, union of 6475 trading "
             "symbols (~1.8k present per session), idempotent, dual-URL (pre/post Aug-2024 "
             "archive cutover)"},
    # e020 — E019's diluted follow-up: top DECILE (~135 names) instead of top-20.
    # Same store, same point-in-time universe, same t-1 fill rule, same cost model.
    {"module": "experiments/e020_diluted_momentum/run_e020.py", "info": "t-1", "live": True,
     "note": "diluted 12-1 momentum, top decile monthly. FAILED gates 5/6: CAGR 24.8% but "
             "excess Sharpe vs same-universe equal-weight only +0.04 (the return IS beta), and "
             "top-bucket names still die 1.87x more often. Control reproduced e019's -0.81 exactly"},
    # e028 — the EXPIRY-ENCODING AUDIT: the fourth conviction, and the first one
    # about an INPUT rather than an information set. `df["expiry"] == str(front_expiry)`
    # compared a datetime.date to a raw string; the bhavcopy store holds DD-Mon-YYYY
    # (2021-2024) and ISO (2025+), so 356 of 576 wall sessions returned an EMPTY
    # chain and actionplan s5.5's fail-closed rule dropped each as NO TRADE. The
    # guard was correct; the lookup beneath it was wrong, and nothing could tell.
    # Fixed at core/feeds/bhavcopy.py (with_expiry_date + ISO write at the boundary),
    # not in the experiment, so a fifth consumer cannot inherit it. Declared day-t /
    # live False for the same reason as e026: it moves no signal, only which
    # sessions exist. VERDICT DEAD_AT_REALISTIC_FILL — the recovered sessions are
    # worse than the ones the bug kept.
    {"module": "experiments/e028_expiry_encoding_audit/audit_encoding.py", "info": "day-t", "live": False,
     "note": "expiry-encoding defect (date-vs-string) hid 4 years of marks. Control reproduces "
             "e026's +61,842.51 on n=64 to the paisa. Corrected: n=129, +45,568 @0.75 pts/leg but "
             "-29,082 @2.0 (EV -225, PF 0.54); breakeven 2.64 -> 1.51 pts/leg; 93.0% of PnL from "
             "2025. FAILED gates 4 and 5. Retrospectively STRICTER than e026 on an unrelated bound: "
             "52/772 legs close >4 ticks below intrinsic (stale final prints), and flooring them "
             "costs a further 3,578"},
    # e029 — the ERA-SLICE audit: does any structural subset of e013 survive the
    # 2021-2023 era that e028's expiry fix finally un-hid? NOT a strategy: no
    # signal moves, sessions are only removed, and the entry credit stays
    # Black-Scholes as in e026/e028. Declared day-t / live False for that
    # reason. The design point is the HOLDOUT: selection reads 2021-2023 and the
    # verdict reads 2024-2026, never overlapping, because the early era loses
    # money and any filter would otherwise "find" a book before touching the
    # data. VERDICT NO SLICE — all five structural filters are negative in
    # sample, and the early era is negative at the engine's own 0.75-pt fill, so
    # this is a signal failure and not a cost one. The 2024-2026 era IS
    # positive at every fill (+245 EV at 2.0 pts); that is a regime observation
    # with no holdout and is deliberately NOT offered as a slice.
    {"module": "experiments/e029_era_slices/eras.py", "info": "day-t", "live": False,
     "note": "era-slice holdout on e013's corrected n=129 book. Control reproduces "
             "e028 exactly. NO SLICE: 5/5 structural filters negative on the 2021-2023 "
             "selection era. Selection era loses at 0.75, 1.5 AND 2.0 pts/leg, so no "
             "execution assumption rescues it. Gates 2/3 (EV>0, and EV > p95 of 500 "
             "same-size random subsets) are implemented and tested for the next "
             "candidate. 2024-2026 is positive at every fill — regime, not a book"},
]

# INVENTORY AUDIT (2026-10-03) — a data claim is a testable assertion, exactly like a
# PnL claim. actionplan.md §2 asserted a `data/participant_oi/` store that does not exist
# and an e009 capture directory that has never been written; both were load-bearing for
# Phase 6 and Test 5. Re-run `python -m experiments.common.audit_inventory` before any
# roadmap item is scheduled against a data partition. §2.1 of the plan is the result.

# e009 Phase B (if built) must register here BEFORE its first PnL number is committed:
# live-chain flips -> info "day-t", live True ONLY with the t+1-fill rule implemented
# and stated in the module docstring; kill 4 (median wall-OI age <= 5 min at decision)
# judged on capture.ts, never reconstructed.
