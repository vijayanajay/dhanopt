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
]

# e008 (if built) must register here BEFORE its first PnL number is committed:
# intraday flips -> info "day-t", live True ONLY with the t+1-fill rule implemented
# and stated in the module docstring.
