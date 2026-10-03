"""e030 — calendar-spread credit-to-fee pre-check for Phase 7.3 (e023).

PREREG-frozen: ./PREREG.md (2026-10-03, before any code in this directory).

Phase 7.3 is the only roadmap item not blocked on absent data. This experiment
asks the cheapest possible question about it and nothing else: does the
front-vs-back calendar spread's gross credit clear its own transaction costs?

It computes NO PnL, NO expectancy and NO implied vol. It measures the premium
difference that would actually pay the bill, against the friction engine the
rest of the repo already uses.

Two shared components are imported, never copied:
  core.feeds.bhavcopy.front_expiry / with_expiry_date — contract identity
  core.friction.zerodha.calculate_friction     — the cost model
Copying either is how e026 and e027 each carried the same loader bug
(invariant 5.14). The PREREG's own wording on this is load-bearing, not style.
"""
from __future__ import annotations

import json
import sys
from datetime import date as _date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from core.feeds.bhavcopy import (
    front_expiry,
    get_partition_path,
    parse_date,
    with_expiry_date,
)
from core.friction.zerodha import OptionLeg, calculate_friction
from experiments.common.lots import lot_for_date

ARTIFACTS = HERE / "artifacts"

NEEDED = ["symbol", "instrument", "expiry", "strike", "option_type", "close"]

# PREREG gate 3 / 4 bars, frozen before the numbers were seen.
CLEAR_RATE_BAR = 0.50
COVER_BAR = 3.0


def _nifty_options(d: _date) -> pd.DataFrame | None:
    """Typed, NIFTY OPTIDX frame for `d`, or None. One loader, from core.

    Returns None rather than an empty frame on a missing partition: "no such
    session" and "no NIFTY rows" are different answers (invariant 5.14).
    """
    p = get_partition_path(d)
    if not Path(p).exists():
        return None
    df = pd.read_parquet(p, columns=NEEDED)
    n = df[(df["symbol"] == "NIFTY") & (df["instrument"] == "OPTIDX")]
    if n.empty:
        return None
    return with_expiry_date(n)


def _atm_strike(chain: pd.DataFrame, expiry: _date) -> tuple[float, float] | None:
    """(ATM strike, implied spot) from the front expiry's straddle bracket.

    Spot is inferred from the bracket rather than an external series so the
    spot and the strike ladder it selects from cannot disagree. The straddle
    width bounds spot to (K − C − P, K + C + P), so use that interval's
    midpoint of its nearest strike instead of pretending to invert exactly.
    """
    rows = chain[chain["expiry_date"] == expiry]
    if rows.empty:
        return None
    piv = rows.pivot_table(index="strike", columns="option_type", values="close")
    if not {"CE", "PE"}.issubset(piv.columns):
        return None
    piv = piv.dropna(subset=["CE", "PE"])
    if piv.empty:
        return None
    piv["straddle"] = piv["CE"] + piv["PE"]
    # Straddle width bounds the spot; the bracket is sorted by width and the
    # tightest bracket is the ATM one.
    best = piv.sort_values("straddle").index[0]
    w = float(piv.loc[best, "straddle"])
    implied_spot = float(best) + (piv.loc[best, "CE"] - piv.loc[best, "PE"])
    return float(best), implied_spot, w


def _leg_close(chain: pd.DataFrame, expiry: _date, strike: float, side: str) -> float | None:
    q = chain[(chain["expiry_date"] == expiry)
              & (chain["strike"] == float(strike))
              & (chain["option_type"] == side)]
    if q.empty:
        return None
    v = float(q.iloc[0]["close"])
    return v if np.isfinite(v) and v > 0 else None


def session_credit(d: _date) -> dict:
    """One session: the four legs, the credit, and its round-trip friction.

    Fail-closed throughout. A missing leg yields `ok=False` and a reason; the
    row is still emitted so coverage can be published before any result.
    """
    out = {"date": d, "ok": False, "reason": None}
    chain = _nifty_options(d)
    if chain is None:
        out["reason"] = "no_partition_or_no_nifty"
        return out
    exps = sorted(set(chain["expiry_date"]))
    front = front_expiry(exps, d)
    if front is None:
        out["reason"] = "no_front_expiry"
        return out
    nxt = next((e for e in exps if e > front), None)
    if nxt is None:
        out["reason"] = "no_next_expiry"
        return out

    atm = _atm_strike(chain, front)
    if atm is None:
        out["reason"] = "no_straddle_bracket"
        return out
    strike, spot, width = atm

    legs = {}
    for tag, exp in (("front", front), ("next", nxt)):
        for side in ("CE", "PE"):
            v = _leg_close(chain, exp, strike, side)
            if v is None:
                out["reason"] = f"missing_{tag}_{side}"
                return out
            legs[f"{tag}_{side}"] = v

    credit_pts = (legs["front_CE"] + legs["front_PE"]
                  - legs["next_CE"] - legs["next_PE"])

    lot = lot_for_date(d)
    opt_legs = [
        OptionLeg(strike=strike, option_type="CE", action="SELL",
                  entry_price=legs["front_CE"], lot_size=lot),
        OptionLeg(strike=strike, option_type="PE", action="SELL",
                  entry_price=legs["front_PE"], lot_size=lot),
        OptionLeg(strike=strike, option_type="CE", action="BUY",
                  entry_price=legs["next_CE"], lot_size=lot),
        OptionLeg(strike=strike, option_type="PE", action="BUY",
                  entry_price=legs["next_PE"], lot_size=lot),
    ]
    fb = calculate_friction(opt_legs, slippage_pts_per_leg=config.SLIPPAGE_POINTS_PER_LEG)

    # friction in index points is per-lot; convert credit to rupees to compare.
    credit_inr = credit_pts * lot
    out.update(ok=True, strike=strike, spot=round(spot, 2), front=str(front),
               next=str(nxt), lot=lot, credit_pts=round(credit_pts, 4),
               credit_inr=round(credit_inr, 2),
               friction_inr=fb.total_rupees, friction_pts=round(fb.points_equivalent, 4),
               clears=bool(credit_inr > fb.total_rupees),
               cover=round(credit_inr / fb.total_rupees, 3) if fb.total_rupees else None,
               friction=fb.summary())
    return out


def gate0_control() -> dict:
    """PREREG gate 0: the shared friction engine, checked by hand.

    Four legs at 100 pts, lot 65, 1.5 pts/leg slippage. Brokerage is
    4 legs x 2 sides x Rs 20 = Rs 160 exactly; slippage is 1.5 x 65 x 4 = Rs 390
    exactly. Those two are the arithmetic that must not drift; the percentage
    charges come from config and are reported, not re-derived here.
    """
    legs = [OptionLeg(strike=25000.0, option_type="CE",
                      action="SELL" if i % 2 == 0 else "BUY",
                      entry_price=100.0, lot_size=65) for i in range(4)]
    fb = calculate_friction(legs, slippage_pts_per_leg=1.5)
    brokerage_ok = abs(fb.brokerage - 160.0) < 1e-6
    slippage_ok = abs(fb.slippage - 390.0) < 1e-6
    return {"bar": "Rs 160 brokerage and Rs 390 slippage on 4 legs @ lot 65",
            "observed_brokerage": fb.brokerage, "observed_slippage": fb.slippage,
            "full": fb.summary(),
            "pass": bool(brokerage_ok and slippage_ok)}


def run() -> tuple[pd.DataFrame, dict]:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    rows = []
    for y in range(2021, 2027):
        for m in range(1, 13):
            base = ROOT / "data" / "historical" / f"year={y}" / f"month={m:02d}"
            if not base.exists():
                continue
            for f in sorted(base.glob("fo_*.parquet")):
                d = datetime_strptime(f.stem.split("_")[1])
                if d is None:
                    continue
                rows.append(session_credit(d))

    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("no sessions found — the store path changed; this is a "
                           "data failure, not a result")
    df["year"] = pd.to_datetime(df["date"]).dt.year

    # --- coverage published BEFORE any result (invariant 5.14) -----------
    cov_rows = []
    for y, g in df.groupby("year"):
        ok = int(g["ok"].sum())
        cov_rows.append({"year": int(y), "considered": int(len(g)), "resolved": ok,
                         "coverage_pct": round(100 * ok / len(g), 2),
                         "reasons": {k: int(v) for k, v in
                                     g.loc[~g["ok"], "reason"].value_counts().items()}})
    overall_cov = round(100 * float(df["ok"].mean()), 2)

    good = df[df["ok"] == True].copy()  # noqa: E712
    g0 = gate0_control()

    if good.empty:
        metrics = {"experiment": "e030_calendar_credit", "verdict": "NO DATA — coverage gate failed",
                   "gates": {"0_friction_control": g0}}
        df.to_csv(ARTIFACTS / "session_credit.csv", index=False)
        (ARTIFACTS / "verdict.json").write_text(json.dumps(metrics, indent=2))
        return df, metrics

    credit = good["credit_pts"].astype(float)
    fric = good["friction_pts"].astype(float)
    clear_rate = float((good["credit_inr"] > good["friction_inr"]).mean())
    med_credit, med_fric = float(credit.median()), float(fric.median())
    # gate 4 is expressed in rupees, which is what the ratio means; points and
    # rupees differ by the era lot, so compare like with like.
    med_ratio = float((good["credit_inr"].median()) / (good["friction_inr"].median()))

    gates = {
        "0_friction_control": g0,
        "1_contract_identity": {
            "bar": "0 sessions where front == next; front resolved from the trade date's own partition",
            "front_equals_next": int((good["front"] == good["next"]).sum()),
            "atm_present": int((good["strike"] > 0).sum()), "n": int(len(good)),
            "pass": bool(int((good["front"] == good["next"]).sum()) == 0
                         and int((good["strike"] > 0).sum()) == len(good)),
        },
        "2_input_coverage_published_first": {
            "bar": ">=90% of sessions resolve all four legs, per year",
            "overall_pct": overall_cov, "per_year": cov_rows,
            "pass": overall_cov >= 90.0,
        },
        "3_kill_gate_credit_clears_costs": {
            "bar": "median credit_pts > 0 AND fraction of sessions clearing friction > 50%",
            "median_credit_pts": round(med_credit, 3),
            "clear_rate": round(clear_rate, 4),
            "pass": bool(med_credit > 0 and clear_rate > CLEAR_RATE_BAR),
        },
        "4_cover_at_reasonable_hit_rate": {
            "bar": "median credit >= 3x median friction",
            "median_credit_inr": round(float(good["credit_inr"].median()), 2),
            "median_friction_inr": round(float(good["friction_inr"].median()), 2),
            "ratio": round(med_ratio, 3),
            "pass": bool(med_ratio >= COVER_BAR),
        },
    }

    if not gates["2_input_coverage_published_first"]["pass"]:
        verdict = "COVERAGE FAILURE — input is not sound enough to quote a credit number"
    elif gates["3_kill_gate_credit_clears_costs"]["pass"] and gates["4_cover_at_reasonable_hit_rate"]["pass"]:
        verdict = "NOT VALIDATED — eligible for a real PnL experiment with its own PREREG"
    elif gates["3_kill_gate_credit_clears_costs"]["pass"]:
        verdict = "MARGINAL — clears costs on a majority of sessions but under 3x cover"
    else:
        verdict = ("PHASE 7.3 STRUCK — the calendar spread's gross credit does not clear "
                   "its own transaction costs, so no signal or surface fit can rescue it")

    metrics = {
        "experiment": "e030_calendar_credit",
        "prereg": "PREREG.md (2026-10-03)",
        "verdict": verdict,
        "claims_no_pnl": True,
        "gates": gates,
        "coverage": {"overall_pct": overall_cov, "per_year": cov_rows,
                     "sessions_considered": int(len(df)),
                     "excluded": int((~df["ok"]).sum())},
        "credit_distribution_pts": {
            "mean": round(float(credit.mean()), 3),
            "median": round(med_credit, 3),
            "p10": round(float(credit.quantile(0.10)), 3),
            "p90": round(float(credit.quantile(0.90)), 3),
            "frac_positive": round(float((credit > 0).mean()), 4),
        },
        "friction": {
            "median_inr": round(float(good["friction_inr"].median()), 2),
            "median_pts_equivalent": round(med_fric, 3),
            "median_friction_breakdown": good.sort_values("credit_inr").iloc[
                len(good) // 2]["friction"] if len(good) else None,
        },
        "positive_credit_sessions": {
            "n": int((credit > 0).sum()), "of": int(len(credit)),
            "median_credit_pts_when_positive": round(float(credit[credit > 0].median()), 3)
            if (credit > 0).any() else None,
        },
    }
    df.to_csv(ARTIFACTS / "session_credit.csv", index=False)
    (ARTIFACTS / "verdict.json").write_text(json.dumps(metrics, indent=2))
    return df, metrics


def datetime_strptime(s: str):
    try:
        return _date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except (ValueError, IndexError):
        return None


if __name__ == "__main__":
    _, m = run()
    print(json.dumps(m, indent=2))
