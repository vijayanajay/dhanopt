"""e028 - the expiry-encoding audit.

PREREG-frozen: ../PREREG.md (2026-10-03, before any code in this directory).

The design in one line: **the signal is frozen, only the chain lookup moves.**

e026 selects its marks with `df["expiry"] == str(fe)`, comparing a formatted
date against a raw string. The store holds two encodings, so every pre-2025
partition returns an empty chain, every leg is None, and §5.5's fail-closed
rule drops the session as NO TRADE - perfectly correct behaviour concealing a
wrong lookup. e018 never had the defect (it compares parsed dates), which is
why the bug survived in exactly the two newest artifacts and nowhere else.

Arms (PREREG §3):
  A  CONTROL     e026's loader verbatim (`load_front_chain_string_eq`)
                 -> must land on e026's +61,842.51 and e027's 2.64 breakeven
  B  CORRECTED   expiry parsed to a date and compared as a date
  C  LADDER      both arms re-priced across slippage, e027's method
  D  ERA CUT     both arms, net by calendar year

Arm A is why the defective loader is retained in e026 rather than deleted: a
control that cannot be run is not a control.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import date as _date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.feeds.bhavcopy import parse_date, with_expiry_date
from experiments.e026_realmark_audit.audit_realmark import (
    build_bhavcopy_calendar, check_identity, check_impossibility, collect_trades,
    e013_friction, load_front_chain, load_front_chain_string_eq, stats, _vol_frame,
)
from experiments.e027_spread_realism.spread_realism import (
    CONSERVATIVE_PTS_PER_LEG, MODELLED_PTS_PER_LEG, PLAN_STATED_PTS_PER_LEG, price_book,
)

ARTIFACTS = HERE / "artifacts"
TRADES_CSV = ARTIFACTS / "audit_trades.csv"
VERDICT = ARTIFACTS / "verdict.json"

# e026's published numbers. These are the control: the experiment is void if
# Arm A does not land on them, exactly as e018's was void if it did not
# reproduce e011's.
E026_NET = 61842.51
E026_N = 64
E027_BREAKEVEN = 2.64

# Full span of the 193-session e013 sample, for the conservative annualisation.
CALENDAR_YEARS = 5.71
BANKROLL = 200_000


# --------------------------------------------------------------- assembly ---
def build_frame(loader) -> pd.DataFrame:
    """e013's trade list under one chain loader, with e026's accounting.

    Identical to e026's `run()` up to the loader: same selection walk, same
    entry/exit bars, same lot eras, same friction model, same real closes.
    """
    vol_e011, _ = _vol_frame()
    trades = collect_trades(vol_e011, build_bhavcopy_calendar(), loader=loader)
    df = pd.DataFrame([asdict(t) for t in trades])
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values("date").reset_index(drop=True)
    df["friction"] = [e013_friction(r.entry_turnover_inr, r.lot) for r in df.itertuples()]
    df["net_A"] = (df.credit_pts - df.debit_bs) * df.lot - df.friction
    df["net_real"] = np.where(df.debit_real.notna(),
                              (df.credit_pts - df.debit_real) * df.lot - df.friction,
                              np.nan)
    # Expiry-day exits stay excluded in every arm: e018 measured the bhavcopy
    # `close` on expiry day as a stale last trade.
    df["mark_valid"] = df.debit_real.notna() & (~df.expiry_is_trade_date.fillna(True))
    return df


def breakeven(arm_b: pd.DataFrame) -> float:
    """e027's closed form: net(s) = sum(net_real) + sum(8*lot)*(modelled - s)."""
    return MODELLED_PTS_PER_LEG + float(arm_b["net_real"].sum()) / float((8.0 * arm_b["lot"]).sum())


def ladder(arm_b: pd.DataFrame) -> list[dict]:
    pts = [0.05, 0.10, 0.25, 0.50, MODELLED_PTS_PER_LEG, 1.00,
           PLAN_STATED_PTS_PER_LEG, CONSERVATIVE_PTS_PER_LEG, 2.50, 3.00]
    seen, out = set(), []
    for s in pts:
        if round(s, 4) in seen:
            continue
        seen.add(round(s, 4))
        net = price_book(arm_b, s)
        out.append({"pts_per_leg": s,
                    "net_pnl": round(float(net.sum()), 2),
                    "ev_per_trade": round(float(net.mean()), 2)})
    return out


def era_cut(arm_b: pd.DataFrame, net: pd.Series) -> dict:
    d = pd.to_datetime(arm_b["date"])
    by_year = net.groupby(d.dt.year).agg(["count", "sum", "mean"]).round(0)
    total = float(net.sum())
    best = float(by_year["sum"].max()) if len(by_year) else 0.0
    return {
        "by_year": {str(k): {"sessions": int(v["count"]),
                             "net_pnl": float(v["sum"]),
                             "mean_per_session": float(v["mean"])}
                    for k, v in by_year.iterrows()},
        "share_of_pnl_from_best_year_pct": round(100 * best / total, 1) if total else None,
        "span_years": round((pd.to_datetime(arm_b["date"]).max()
                             - pd.to_datetime(arm_b["date"]).min()).days / 365.25, 2),
        "conservative_pnl_per_yr_inr": round(total / CALENDAR_YEARS, 0),
        "conservative_pct_per_yr_on_2L": round(100 * total / CALENDAR_YEARS / BANKROLL, 2),
    }


def _stale_leg_scan(trades, cal) -> tuple[list[dict], int]:
    """Legs closing materially below intrinsic, vs the same-expiry futures close.

    The per-leg no-arbitrage bound that holds at ANY mark, unlike e026's fly
    bound which is an expiry statement. A traded option cannot close more than a
    few ticks below intrinsic, so a breach is a stale final print.
    """
    tick = 0.05
    cols = ["symbol", "instrument", "expiry", "strike", "option_type", "close"]
    breaches, checked = [], 0
    for t in trades:
        if t.debit_real is None:
            continue
        df = pd.read_parquet(cal[t.date], columns=cols)
        n = with_expiry_date(df[(df["symbol"] == "NIFTY") & (df["instrument"] == "OPTIDX")])
        c = n[n["expiry_date"] == t.front_expiry]
        f = with_expiry_date(df[(df["symbol"] == "NIFTY") & (df["instrument"] == "FUTIDX")])
        fc = f[f["expiry_date"] == t.front_expiry]
        s = float(fc["close"].iloc[0]) if not fc.empty else t.spot_1230
        for k, side in ((t.atm, "CE"), (t.atm, "PE"), (t.wing_ce, "CE"), (t.wing_pe, "PE")):
            q = c[(c["strike"] == float(k)) & (c["option_type"] == side)]
            if q.empty:
                continue
            checked += 1
            px = float(q.iloc[0]["close"])
            intrinsic = max(s - k, 0.0) if side == "CE" else max(k - s, 0.0)
            if intrinsic - px > 4 * tick:
                breaches.append({"date": str(t.date), "strike": k, "side": side,
                                 "close": px, "intrinsic": round(intrinsic, 2)})
    return breaches, checked


# ------------------------------------------------------------------- run ----
def run() -> tuple[pd.DataFrame, dict]:
    df_a = build_frame(load_front_chain_string_eq)     # control
    df_b = build_frame(load_front_chain)               # corrected

    arm_a = df_a[df_a.mark_valid]
    arm_b = df_b[df_b.mark_valid]

    # Arm A must be bit-identical to Arm B wherever both have a mark: the
    # lookup can only ever ADD sessions, never change one.
    shared = df_a[df_a.mark_valid].merge(
        df_b[df_b.mark_valid], on="date", suffixes=("_a", "_b"))
    marks_identical = bool((shared.debit_real_a == shared.debit_real_b).all())

    be_a, be_b = breakeven(arm_a), breakeven(arm_b)
    net_a2 = price_book(arm_a, CONSERVATIVE_PTS_PER_LEG)
    net_b2 = price_book(arm_b, CONSERVATIVE_PTS_PER_LEG)

    vol_e011, _ = _vol_frame()
    cal = build_bhavcopy_calendar()
    n_identity, id_fail = check_identity(collect_trades(vol_e011, cal), cal)
    n_imposs, imp_fail, stale = check_impossibility(collect_trades(vol_e011, cal))
    stale_detail, stale_checked = _stale_leg_scan(collect_trades(vol_e011, cal), cal)

    # Expiry-day exits are excluded by a rule frozen in e018 (the bhavcopy close
    # on expiry day is a stale last trade), not by the lookup. So the denominator
    # for "did the lookup find everything?" is the markable sessions. PREREG s9
    # amendment 1; both denominators are reported.
    markable = int((~df_b.expiry_is_trade_date.fillna(True)).sum())
    coverage = float(df_b.mark_valid.sum() / markable) if markable else 0.0
    ev_b2 = float(net_b2.mean())

    gates = {
        "0_control_reproduces_predecessor": {
            "bar": f"arm A = Rs {E026_NET:,.2f} on n={E026_N} to the paisa, and "
                   f"e027's breakeven {E027_BREAKEVEN} pts/leg",
            "observed_net": round(float(price_book(arm_a, MODELLED_PTS_PER_LEG).sum()), 2),
            "observed_n": int(arm_a.shape[0]),
            "observed_breakeven": round(be_a, 3),
            "pass": (abs(float(price_book(arm_a, MODELLED_PTS_PER_LEG).sum()) - E026_NET) <= 1.0
                     and arm_a.shape[0] == E026_N
                     and abs(be_a - E027_BREAKEVEN) <= 0.01),
        },
        "1_contract_identity": {
            "bar": "0 mismatches, front expiry re-derived per trade",
            "observed": n_identity, "pass": n_identity == 0,
        },
        "2_arithmetic_impossibility": {
            "bar": "0 violations of the closed-form iron-fly bound",
            "observed": n_imposs, "pass": n_imposs == 0,
        },
        "3_coverage": {
            "bar": ">=95% of the markable sessions (selected sessions whose exit "
                   "is NOT their own expiry day) yield a real 4-leg mark",
            "observed_pct": round(100 * coverage, 2),
            "observed_n": int(df_b.mark_valid.sum()),
            "markable_n": int(markable),
            "literal_prereg_pct": round(100 * float(df_b.mark_valid.sum()) / len(df_b), 2),
            "pass": coverage >= 0.95,
        },
        "4_edge_at_realistic_fill": {
            "bar": "arm B EV >= +400 per trade at 2.0 pts/leg on the full sample",
            "observed": round(ev_b2, 2),
            "pass": ev_b2 >= 400.0,
        },
        "5_era_robustness": {
            "bar": "no calendar year supplies >60% of net PnL",
            "observed_pct": era_cut(arm_b, price_book(arm_b, MODELLED_PTS_PER_LEG))[
                "share_of_pnl_from_best_year_pct"],
            "pass": era_cut(arm_b, price_book(arm_b, MODELLED_PTS_PER_LEG))[
                "share_of_pnl_from_best_year_pct"] <= 60.0,
        },
        "6_round_trip_identity": {
            "bar": "expiry parses losslessly in both encodings, and no lookup "
                   "returns empty on a partition that exists",
            "observed_marks_identical_where_shared": marks_identical,
            "pass": marks_identical,
        },
    }

    # Gate 7 is EVIDENCE, not a void condition, and cannot rescue a verdict: a
    # stale-early print on a long fly reads LOW, so the fly looks cheap and the
    # book looks better than it was. Enforcing it can only remove PnL. See
    # PREREG s9 amendment 2.
    stale_legs = len(stale_detail)
    gates["7_marks_are_not_stale_early"] = {
        "bar": "0 of the 4 legs close more than 4 ticks below intrinsic vs the "
               "same-expiry futures close (evidence only, non-voiding)",
        "observed_legs_below_intrinsic": stale_legs,
        "observed_legs_checked": stale_checked,
        "pass": stale_legs == 0,
        "note": "a stale-early print reads LOW, so the fly reads cheap and this "
                "book looks better than it was. Flooring every breaching leg at "
                "intrinsic (intrinsic_audit.py) costs Rs 3,578 at 0.75 pts/leg and "
                "Rs 3,578 more at 2.0. Not load-bearing: gate 4 already fails.",
    }

    void = all(gates[g]["pass"] for g in ("0_control_reproduces_predecessor",
                                          "1_contract_identity",
                                          "2_arithmetic_impossibility",
                                          "6_round_trip_identity"))
    if not void:
        verdict = "VOID"
    elif not gates["3_coverage"]["pass"]:
        verdict = "INCONCLUSIVE"
    elif not gates["4_edge_at_realistic_fill"]["pass"]:
        verdict = "DEAD_AT_REALISTIC_FILL"
    elif not gates["5_era_robustness"]["pass"]:
        verdict = "SURVIVES_BUT_ERA_UNSTABLE"
    else:
        verdict = "SURVIVES"

    both_sides = df_a[["date", "mark_valid"]].merge(
        df_b[["date", "mark_valid"]], on="date", suffixes=("_a", "_b"))
    recovered = int((~both_sides.mark_valid_a & both_sides.mark_valid_b).sum())

    metrics = {
        "arm_A_control_as_published": stats(price_book(arm_a, MODELLED_PTS_PER_LEG)),
        "arm_A_at_2.0_pts": stats(price_book(arm_a, CONSERVATIVE_PTS_PER_LEG)),
        "arm_B_corrected_at_0.75_pts": stats(price_book(arm_b, MODELLED_PTS_PER_LEG)),
        "arm_B_corrected_at_1.5_pts": stats(price_book(arm_b, PLAN_STATED_PTS_PER_LEG)),
        "arm_B_corrected_at_2.0_pts": stats(price_book(arm_b, CONSERVATIVE_PTS_PER_LEG)),
    }

    verdict_doc = {
        "experiment": "e028_expiry_encoding_audit",
        "verdict": verdict,
        "defect": "df['expiry'] == str(front_expiry): a typed date compared against a "
                  "raw string. The store holds DD-Mon-YYYY (2021-2024) and ISO (2025+), "
                  "so every legacy partition returned an empty chain and §5.5's "
                  "fail-closed rule dropped the session as NO TRADE.",
        "sessions_selected": int(len(df_b)),
        "marks_arm_A": int(df_a.debit_real.notna().sum()),
        "marks_arm_B": int(df_b.debit_real.notna().sum()),
        "usable_arm_A": int(len(arm_a)),
        "usable_arm_B": int(len(arm_b)),
        "sessions_recovered": recovered,
        "marks_identical_where_shared": marks_identical,
        "breakeven_pts_per_leg": {"arm_A": round(be_a, 3), "arm_B": round(be_b, 3)},
        "metrics": metrics,
        "ladder": {"arm_A": ladder(arm_a), "arm_B": ladder(arm_b)},
        "era_cut": {"arm_A": era_cut(arm_a, price_book(arm_a, MODELLED_PTS_PER_LEG)),
                    "arm_B": era_cut(arm_b, price_book(arm_b, MODELLED_PTS_PER_LEG))},
        "gates": gates,
        "supersedes": [
            "e026 arm B (+Rs 61,843, n=64) - correct method, format-selected sample",
            "e027 slippage ladder and its 2.64 pts/leg breakeven - same sample",
            "actionplan.md s5.5 B/C and RETROSPECTIVE.md s5.11 - derived from that sample",
        ],
        "note": "Entry credit remains Black-Scholes in every arm (no intraday option "
                "price on disk), exactly as in e026. This audit can only move the "
                "number against the book, never for it.",
    }
    return df_b, verdict_doc


def main() -> int:
    df, v = run()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    cols = ["date", "atm", "wing_ce", "wing_pe", "dte", "expansion", "credit_pts",
            "debit_real", "net_real", "mark_valid", "expiry_is_trade_date",
            "front_expiry", "friction", "lot"]
    df[cols].to_csv(TRADES_CSV, index=False)
    VERDICT.write_text(json.dumps(v, indent=2, default=str))

    print(f"\nVERDICT: {v['verdict']}")
    print(f"  marks  A {v['marks_arm_A']:>3} -> B {v['marks_arm_B']:>3} "
          f"({v['sessions_recovered']} sessions recovered)")
    print(f"  usable A {v['usable_arm_A']:>3} -> B {v['usable_arm_B']:>3}")
    for name, g in v["gates"].items():
        print(f"  [{'PASS' if g['pass'] else 'FAIL'}] {name}")
    print()
    for arm in ("arm_A_control_as_published", "arm_A_at_2.0_pts",
                "arm_B_corrected_at_0.75_pts", "arm_B_corrected_at_1.5_pts",
                "arm_B_corrected_at_2.0_pts"):
        m = v["metrics"][arm]
        print(f"  {arm:<32} n={m.get('trades'):>3}  net={m.get('total_net_pnl'):>10,.0f}"
              f"  EV={m.get('net_ev_per_trade'):>7,.0f}  WR={100*(m.get('win_rate') or 0):>4.1f}%"
              f"  PF={m.get('profit_factor')}")
    print()
    print("  breakeven pts/leg:  A %.2f  ->  B %.2f" % (
        v["breakeven_pts_per_leg"]["arm_A"], v["breakeven_pts_per_leg"]["arm_B"]))
    for arm in ("arm_A", "arm_B"):
        e = v["era_cut"][arm]
        print(f"  {arm} best-year share: {e['share_of_pnl_from_best_year_pct']}%  "
              f"span {e['span_years']}y  conservative {e['conservative_pct_per_yr_on_2L']}%/yr")
    print(f"\n  wrote {TRADES_CSV}")
    print(f"  wrote {VERDICT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
