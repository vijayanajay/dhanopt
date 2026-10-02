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
     "note": "data fetch: free NSE daily cash bhavcopy, 1420 sessions x 6475 symbols, "
             "idempotent, dual-URL (pre/post Aug-2024 archive cutover)"},
    # e020 — E019's diluted follow-up: top DECILE (~135 names) instead of top-20.
    # Same store, same point-in-time universe, same t-1 fill rule, same cost model.
    {"module": "experiments/e020_diluted_momentum/run_e020.py", "info": "t-1", "live": True,
     "note": "diluted 12-1 momentum, top decile monthly. FAILED gates 5/6: CAGR 24.8% but "
             "excess Sharpe vs same-universe equal-weight only +0.04 (the return IS beta), and "
             "top-bucket names still die 1.87x more often. Control reproduced e019's -0.81 exactly"},
]

# e009 Phase B (if built) must register here BEFORE its first PnL number is committed:
# live-chain flips -> info "day-t", live True ONLY with the t+1-fill rule implemented
# and stated in the module docstring; kill 4 (median wall-OI age <= 5 min at decision)
# judged on capture.ts, never reconstructed.
