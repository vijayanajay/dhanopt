"""e032 — the mirror calendar re-checked under a corrected gate set.

PREREG-frozen: ./PREREG.md (2026-10-03, before any code in this directory).

e032 re-implements nothing. It re-runs e031's exact configuration (invariant
s5.10), compares the fresh figures against e031's *recorded* artifact, and then
evaluates a gate set in which every bar is valid when frozen and explicitly
classified as either CARRIED (frozen in e031's PREREG before e031's full run)
or NEW (written for e032 with e031's numbers already in view, and therefore
void-only -- see the constraint in the PREREG).

e031's gate 4 tested a property of the INSTRUMENT (spot-independence) rather
than a property of the MEASUREMENT, and could not have been passed by any run.
e032's replacement bars 4a and 4b each ask only "did we fetch the right leg?".
Whether the trade makes money is gate 5's question alone, and gate 5's bar is
carried unchanged and sign-only -- so no threshold introduced here can move the
verdict from DEAD to ELIGIBLE.

Shared components are imported, never copied:
  experiments.e031_mirror_calendar.mirror_calendar  -- the whole measurement
  experiments.e031_mirror_calendar.mirror_calendar._spearman
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.e031_mirror_calendar import mirror_calendar as e031
from experiments.e031_mirror_calendar.mirror_calendar import (  # noqa: F401
    CONTROL_TOL,
    COVER_BAR,
    TOL,
)

ARTIFACTS = HERE / "artifacts"
E031_VERDICT = ROOT / "experiments" / "e031_mirror_calendar" / "artifacts" / "verdict.json"

# ---- bars -----------------------------------------------------------------
# CARRIED (from e031's PREREG, frozen before e031's full run):
#   CONTROL_TOL 1e-9   gate 0   control reproduces the predecessor
#   identity mismatches 0      gate 1   contract identity
#   COVER_BAR 90.0             gate 2   coverage of eligible, per year
#   TOL 1e-6                   gate 3   arithmetic identity, TV1 >= 0
#   median net > 0             gate 5   sign only, no threshold to tune
#
# NEW (written with e031's results in view -- therefore void-only):
WRONG_LEG_BAR = 0.20   # 4a |rho(moneyness, credit)| < 0.20; data-informed
TV_SIGN_BAR = 0.0      # 4b rho(moneyness, TV1) < 0; theory-imposed sign

EXIT_IDENTITY_REASONS = frozenset(
    {"exit_front_identity_mismatch", "exit_back_identity_mismatch"})

# The gates that decide VOID vs not-VOID. Gate 5 is deliberately absent: it is
# the only gate that can turn DEAD into ELIGIBLE, and separating the two sets is
# what makes "a NEW bar may only void, never validate" a property of the code
# rather than an assertion in the PREREG.
AUDIT_KEYS = (
    "0_control_reproduces_predecessor",
    "1_contract_identity",
    "2_coverage_per_year",
    "3_arithmetic_impossibility",
    "4a_wrong_leg_detector",
    "4b_time_value_sign",
)


def _verdict(gates: dict, audit_keys: tuple[str, ...] = AUDIT_KEYS) -> str:
    """Map a gate dict to a verdict, with no interpretive step in between.

    No override clause, deliberately. e031's verdict field carried a 400-character
    argument for why its own frozen kill bar should be read as something other
    than what it says; this function is why this experiment does not need one.
    An audit-gate failure returns AUDIT VOID unconditionally, and the choice
    between DEAD and ELIGIBLE is made by gate 5 alone.
    """
    failed = [k for k in audit_keys if not gates.get(k, {}).get("pass")]
    if failed:
        return ("AUDIT VOID — failed audit gate(s): " + ", ".join(failed)
                + "; no number in this file may be quoted")
    if gates["5_edge_survives_friction"]["pass"]:
        return ("ELIGIBLE, NOT VALIDATED — clears friction unconditionally; a "
                "baseline without a signal, not a book")
    return ("LEAD DEAD — the entry credit is real but the back leg's residual "
            "time value consumes it, and friction finishes it. Gates all pass "
            "as frozen; no PREREG amendment was needed or applied.")


def _pinned(m: dict) -> dict:
    """The figures that must reproduce the predecessor exactly (PREREG gate 0).

    30 values spanning every gate and every distribution in e031's verdict.
    Chosen to cover each gate's *observed* quantity, not merely its pass flag --
    a gate that still passes while its observation drifts would otherwise slip
    through.
    """
    g = m["gates"]
    p = m["net_after_friction"]
    return {
        "gates_failed": m["gates_failed"],
        "g0_n": g["0_control_vs_e030"]["n"],
        "g0_max_abs_diff": g["0_control_vs_e030"]["max_abs_diff"],
        "g1_resolved": g["1_contract_identity"]["n_resolved"],
        "g1_considered": g["1_contract_identity"]["n_considered"],
        "g1_front_equals_next": g["1_contract_identity"]["front_equals_next"],
        "g1_exit_mismatches": g["1_contract_identity"]["exit_identity_mismatches"],
        "g2_overall_pct": g["2_coverage_published_first"]["overall_pct"],
        "g2_eligibility_pct": g["2_coverage_published_first"]["eligibility_pct"],
        "g2_eligible_sessions": g["2_coverage_published_first"]["eligible_sessions"],
        "g2_sessions_total": g["2_coverage_published_first"]["sessions_total"],
        "g3_identity_max_error": g["3_arithmetic_impossibility"]["identity_max_error"],
        "g3_raw_mark_flags": g["3_arithmetic_impossibility"]["raw_mark_flags_before_exclusion"],
        "g3_violations": g["3_arithmetic_impossibility"]["violations_remaining_in_result"],
        "g4_spearman_rho": g["4_spot_independence"]["spearman_rho"],
        "g4_rho_move_credit": g["4_spot_independence"]["diagnostic_rho_move_vs_credit"],
        "g4_rho_move_tv1": g["4_spot_independence"]["diagnostic_rho_move_vs_tv1"],
        "g5_median_net": g["5_edge_survives_friction"]["median_net"],
        "g5_median_net_2x": g["5_edge_survives_friction"]["median_net_2x"],
        "pnl_median_gross": m["pnl_distribution"]["median_gross"],
        "pnl_mean_gross": m["pnl_distribution"]["mean_gross"],
        "pnl_min_gross": m["pnl_distribution"]["min_gross"],
        "pnl_max_gross": m["pnl_distribution"]["max_gross"],
        "pnl_frac_positive": m["pnl_distribution"]["frac_gross_positive"],
        "credit_median": m["credit_vs_residual_time_value"]["median_credit"],
        "tv1_median": m["credit_vs_residual_time_value"]["median_tv1"],
        "credit_frac_exceeds_tv1": m["credit_vs_residual_time_value"]["frac_credit_exceeds_tv1"],
        "net_total": p["total"],
        "net_ev_per_trade": p["ev_per_trade"],
        "net_median": p["median"],
        "net_win_rate": p["win_rate"],
        "net_profit_factor": p["profit_factor"],
        "net_max_drawdown_inr": p["max_drawdown_inr"],
        "net_min_single_trade": p["min_single_trade"],
        "net2x_ev_per_trade": m["net_at_2x_slippage"]["ev_per_trade"],
        "net2x_median": m["net_at_2x_slippage"]["median"],
    }


def _coverage(df: pd.DataFrame) -> list[dict]:
    """Coverage of eligible sessions, recomputed per year from the rows.

    Recomputed here rather than lifted from e031's gate dict: gate 2's bar is
    per year, and re-deriving it is what makes this an audit rather than a
    copy of the answer being audited.
    """
    out = []
    for y, g in df.groupby("year"):
        elig = g[g["eligible"]]
        resolved = int(elig["ok"].sum()) if len(elig) else 0
        out.append({
            "year": int(y),
            "sessions": int(len(g)),
            "eligible": int(len(elig)),
            "eligibility_pct": round(100 * len(elig) / len(g), 2),
            "resolved": resolved,
            "coverage_pct": round(100 * resolved / len(elig), 2) if len(elig) else 0.0,
            "ineligible_reasons": {str(k): int(v) for k, v in
                                   g.loc[~g["eligible"], "reason"].value_counts().items()},
            "data_failures": {str(k): int(v) for k, v in
                              elig.loc[~elig["ok"], "reason"].value_counts().items()},
        })
    return out


def run() -> tuple[pd.DataFrame, dict]:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    # Read the predecessor's RECORD before re-running it: run() overwrites that
    # record, so reading afterwards would compare the artifact to itself and the
    # control would prove nothing.
    prev = None
    if E031_VERDICT.exists():
        prev = json.loads(E031_VERDICT.read_text(encoding="utf-8"))

    df, m31 = e031.run()

    # ---- gate 0: reproduce the predecessor --------------------------------
    fresh = _pinned(m31)
    if prev is None:
        drift = {"<recorded artifact missing>": (None, None)}
    else:
        prev_pinned = _pinned(prev)
        drift = {k: (prev_pinned[k], fresh[k])
                 for k in fresh if prev_pinned[k] != fresh[k]}
    chain_ok = bool(prev is not None
                    and prev["gates"]["0_control_vs_e030"]["pass"]
                    and prev["gates"]["0_control_vs_e030"]["max_abs_diff"] < CONTROL_TOL)
    g0 = {
        "bar": "fresh e031.run() equals e031's recorded verdict.json exactly on all "
               f"{len(fresh)} pinned figures, AND e031's control vs e030 passed at 1e-9",
        "provenance": "CARRIED (s5.10 control-reproduces-predecessor)",
        "pinned_figures": len(fresh),
        "drifted": {k: {"recorded": a, "fresh": b} for k, (a, b) in drift.items()},
        "chain_e031_vs_e030": chain_ok,
        "pass": bool(not drift and chain_ok),
    }

    good = df[df["eligible"] & df["ok"]].copy()  # noqa: E712
    n_total = int(len(df))

    # ---- gate 1: contract identity ---------------------------------------
    front_eq_next = int((good["front"] == good["next"]).sum()) if len(good) else 0
    exit_mismatch = int(df["reason"].isin(EXIT_IDENTITY_REASONS).sum())
    inherited = bool(m31["gates"]["1_contract_identity"]["pass"])
    g1 = {
        "bar": "front != next on every resolved session; zero exit-identity mismatch "
               "rows across all sessions",
        "provenance": "CARRIED",
        "n_resolved": int(len(good)),
        "n_considered": n_total,
        "front_equals_next": front_eq_next,
        "exit_identity_mismatches": exit_mismatch,
        "inherited_exit_path_check_from_e031": inherited,
        "note": "the exit partition is read inside e031's session walk; e032 re-derives "
                "what the rows support and marks the rest as inherited rather than "
                "claiming to have repeated it",
        "pass": bool(front_eq_next == 0 and exit_mismatch == 0
                     and inherited and len(good) > 0),
    }

    # ---- gate 2: coverage, per year --------------------------------------
    cov = _coverage(df)
    years = [r["year"] for r in cov]
    per_year_ok = all(r["coverage_pct"] >= COVER_BAR for r in cov)
    worst = min((r["coverage_pct"] for r in cov), default=0.0)
    n_elig = sum(r["eligible"] for r in cov)
    n_res = sum(r["resolved"] for r in cov)
    overall = round(100 * n_res / n_elig, 2) if n_elig else 0.0
    g2 = {
        "bar": f">= {COVER_BAR:g}% of ELIGIBLE sessions resolve, per year, every year",
        "provenance": "CARRIED (bar restated by e031 before its full run, unchanged)",
        "overall_pct": overall,
        "eligible_sessions": n_elig,
        "sessions_total": n_total,
        "worst_year_coverage_pct": worst,
        "per_year": cov,
        "pass": bool(overall >= COVER_BAR and per_year_ok and years),
    }

    # ---- gate 3: arithmetic-impossibility --------------------------------
    if len(good):
        ident = float((good["credit"].astype(float) - good["tv1"].astype(float)
                       - good["gross"].astype(float)).abs().max())
        tv_min = float(good["tv1"].astype(float).min())
        viol = int((good["gross"].astype(float)
                    > good["credit"].astype(float) + TOL).sum())
    else:
        ident, tv_min, viol = float("inf"), float("inf"), 0
    raw_flags = int((df["reason"] == "exit_mark_inconsistent").sum())
    survivors_flagged = int(((df["reason"] == "exit_mark_inconsistent")
                             & (df["ok"] == True)).sum())  # noqa: E712
    g3 = {
        "bar": f"credit - TV1 == PnL to {TOL:g} on every survivor; TV1 >= -{TOL:g} on "
               "survivors; every inconsistent mark excluded AND counted",
        "provenance": "CARRIED",
        "identity_max_error": ident,
        "tv1_min_on_survivors": tv_min,
        "raw_mark_flags_before_exclusion": raw_flags,
        "violations_remaining_in_result": viol,
        "excluded_mark_still_marked_ok": survivors_flagged,
        "pass": bool(ident < TOL and tv_min >= -TOL and viol == 0
                     and survivors_flagged == 0 and len(good) > 0),
    }

    # ---- gate 4a: wrong-leg detector (NEW, void-only) --------------------
    if len(good):
        move = good["spot_entry_expiry_move"].astype(float)
        rho_credit = e031._spearman(move, good["credit"].astype(float))
        rho_tv1 = e031._spearman(move, good["tv1"].astype(float))
        rho_gross = e031._spearman(move, good["gross"].astype(float))
    else:
        rho_credit = rho_tv1 = rho_gross = 0.0
    g4a = {
        "bar": f"|spearman rho(|S1-K|, credit)| < {WRONG_LEG_BAR}",
        "provenance": "NEW with e031's rho=0.0978 in view; VOID-ONLY by the PREREG "
                      "constraint (a data-informed bar may not produce a positive verdict)",
        "spearman_rho": round(rho_credit, 5),
        "why": "the entry credit is fixed at entry, before the move exists, so it "
               "cannot be caused by it; a large rho means an entry or exit leg came "
               "from the wrong contract -- the question gate 1 asks structurally",
        "pass": bool(abs(rho_credit) < WRONG_LEG_BAR),
    }

    # ---- gate 4b: time-value sign (NEW, theory-imposed) ------------------
    g4b = {
        "bar": f"spearman rho(|S1-K|, TV1) < {TV_SIGN_BAR:g}  (a sign, not a magnitude)",
        "provenance": "NEW; the SIGN is imposed by option theory and contains no "
                      "threshold that could have been adjusted after the fact",
        "spearman_rho": round(rho_tv1, 5),
        "why": "a straddle's time value falls with moneyness, so a positive rho means "
               "the quantity called TV1 is not a residual time value and B1 or F1 "
               "came from the wrong contract",
        "pass": bool(rho_tv1 < TV_SIGN_BAR),
    }

    # ---- gate 5: edge survives friction (CARRIED, sign-only) -------------
    net = good["net"].astype(float) if len(good) else pd.Series(dtype=float)
    net2x = good["net2x"].astype(float) if len(good) else pd.Series(dtype=float)
    med, med2x = (float(net.median()) if len(net) else 0.0), \
                 (float(net2x.median()) if len(net2x) else 0.0)
    g5 = {
        "bar": "median net > 0 AND median net at 2x slippage > 0",
        "provenance": "CARRIED; sign-only -- there is no threshold in this bar to tune",
        "median_net": round(med, 2),
        "median_net_2x": round(med2x, 2),
        "pass": bool(med > 0 and med2x > 0),
    }

    gates = {
        "0_control_reproduces_predecessor": g0,
        "1_contract_identity": g1,
        "2_coverage_per_year": g2,
        "3_arithmetic_impossibility": g3,
        "4a_wrong_leg_detector": g4a,
        "4b_time_value_sign": g4b,
        "5_edge_survives_friction": g5,
    }
    audit_keys = list(AUDIT_KEYS)
    verdict = _verdict(gates)

    wins = net[net > 0]
    losses = net[net < 0]
    cum = net.cumsum()

    metrics = {
        "experiment": "e032_mirror_calendar_recheck",
        "prereg": "PREREG.md (2026-10-03, frozen before any code in this directory)",
        "verdict": verdict,
        "gates": gates,
        "gates_failed": sum(1 for v in gates.values() if not v["pass"]),
        "audit_gates": audit_keys,
        "prereg_status": {
            "amendments_needed": 0,
            "override_clause_used": False,
            "sample_already_seen": True,
            "produces_new_evidence": False,
            "what_it_produces": "a verdict label whose gates were all defensible when "
                                "frozen, with every bar classified CARRIED or NEW",
            "constraint": "no NEW bar can produce a positive verdict; gate 5 alone "
                          "decides DEAD vs ELIGIBLE and its bar is carried and "
                          "sign-only, so the verdict is invariant to every threshold "
                          "introduced in the PREREG",
        },
        "coverage": {"overall_pct": overall, "eligible_sessions": n_elig,
                     "sessions_total": n_total, "per_year": cov,
                     "excluded": int((~df["ok"]).sum())},
        "pnl_distribution": {
            "median_gross": round(float(good["gross"].median()), 4) if len(good) else None,
            "mean_gross": round(float(good["gross"].mean()), 4) if len(good) else None,
            "min_gross": round(float(good["gross"].min()), 4) if len(good) else None,
            "max_gross": round(float(good["gross"].max()), 4) if len(good) else None,
            "frac_gross_positive": round(float((good["gross"] > 0).mean()), 4) if len(good) else None,
        },
        "credit_vs_residual_time_value": {
            "median_credit": round(float(good["credit"].median()), 4) if len(good) else None,
            "median_tv1": round(float(good["tv1"].median()), 4) if len(good) else None,
            "frac_credit_exceeds_tv1": round(float((good["tv1"] < good["credit"]).mean()), 4) if len(good) else None,
            "rho_move_vs_credit": round(rho_credit, 5),
            "rho_move_vs_tv1": round(rho_tv1, 5),
            "rho_move_vs_gross": round(rho_gross, 5),
        },
        "net_after_friction": {
            "total": round(float(net.sum()), 2),
            "ev_per_trade": round(float(net.mean()), 2) if len(net) else None,
            "median": round(med, 2),
            "win_rate": round(float((net > 0).mean()), 4) if len(net) else None,
            "profit_factor": round(float(wins.sum() / abs(losses.sum())), 4) if len(losses) else None,
            "max_drawdown_inr": round(float((cum - cum.cummax()).min()), 2) if len(cum) else None,
            "min_single_trade": round(float(net.min()), 2) if len(net) else None,
        },
        "net_at_2x_slippage": {
            "ev_per_trade": round(float(net2x.mean()), 2) if len(net2x) else None,
            "median": round(med2x, 2),
        },
        "inherited_from": {
            "measurement": "experiments/e031_mirror_calendar/mirror_calendar.run()",
            "e031_gate0_vs_e030": chain_ok,
            "chain": "e032 -> e031 -> e030, every link checked",
        },
    }

    df.to_csv(ARTIFACTS / "session_pnl.csv", index=False)
    (ARTIFACTS / "verdict.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    return df, metrics


if __name__ == "__main__":
    _, m = run()
    print(json.dumps(m, indent=2, ensure_ascii=False))
