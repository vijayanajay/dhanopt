"""Leak audit, part 3: e001's open->close condor on t-1 walls.

e001's frozen rule book (+152,346 rule-selected) labels its condor on day-t EOD
walls — the same look-ahead the breach book died of (e005 Add. 8, e007 gate 0).
This closes the last unfalsified cell: same arithmetic as e001 (enter at day-t leg
opens, exit at day-t leg closes, real friction, era lots, credit>0 skip, e001's
t-1-momentum rule selection) but walls from the t-1 partition (paper_trade.csv's
stored t-1 walls — the observable source).

Run: python -m experiments.e002_regime_models.audit_e001_t1
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import pandas as pd

from experiments.e002_regime_models.audit_labels_t1 import t1_walls
from experiments.e005_theta_condor.paper_trade import _px_map
from experiments.e005_theta_condor.replay_theta import (
    _chain_view, _condor_legs_unconditional, _partition_calendar, _safe_exp)
from core.feeds.intraday import available_dates
from experiments.common.lots import lot_for_date

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts_t1labels"
LABELS = HERE.parent / "e001_leakfree_replay" / "artifacts" / "labels_daily.csv"
FROZEN_RULE_NET = 152_346.0


def main() -> int:
    import config
    from core.friction.zerodha import OptionLeg, calculate_friction

    walls = t1_walls()
    rule_days = set(pd.read_csv(LABELS, parse_dates=["date"])
                      .query("archetype == 'Iron Condor' and selected_by_rule")["date"].dt.date)
    cal = _partition_calendar(config.HISTORICAL_DATA_DIR)

    rows: List[dict] = []
    for d in available_dates():
        d_date = d.date() if hasattr(d, "date") else d
        w = walls.loc[d_date] if d_date in walls.index else None
        if w is None or pd.isna(w["put_wall_t1"]) or pd.isna(w["call_wall_t1"]):
            continue
        own_path = cal.get(d_date)
        if own_path is None:
            continue
        own_df = pd.read_parquet(own_path)
        nifty = own_df[(own_df["symbol"] == "NIFTY") & (own_df["instrument"].isin(["OPTIDX", "IDO"]))]
        exps = [x for x in (_safe_exp(e) for e in nifty["expiry"].unique()) if x and x >= d_date]
        if not exps:
            continue
        pe, ce = _chain_view(nifty, min(exps))
        if pe.empty or ce.empty:
            continue
        m = _px_map(pd.concat([pe, ce]), "open")
        x = _px_map(pd.concat([pe, ce]), "close")
        legs = _condor_legs_unconditional(float(w["put_wall_t1"]), float(w["call_wall_t1"]))
        entry = [m.get((float(l["strike"]), "CE" if l["is_call"] else "PE")) for l in legs]
        exits = [x.get((float(l["strike"]), "CE" if l["is_call"] else "PE")) for l in legs]
        if any(c is None or c <= 0 for c in entry) or any(c is None or c < 0 for c in exits):
            continue
        qty = lot_for_date(d_date)
        credit = sum(entry[i] * qty for i, l in enumerate(legs) if l["action"] == "SELL") \
            - sum(entry[i] * qty for i, l in enumerate(legs) if l["action"] == "BUY")
        if credit <= 0:
            continue
        gross = sum((entry[i] - exits[i]) * qty for i, l in enumerate(legs) if l["action"] == "SELL") \
            + sum((exits[i] - entry[i]) * qty for i, l in enumerate(legs) if l["action"] == "BUY")
        fric = calculate_friction([OptionLeg(strike=l["strike"], option_type="CE" if l["is_call"] else "PE",
                                             action=l["action"], entry_price=float(entry[i]), lot_size=qty)
                                   for i, l in enumerate(legs)])
        rows.append({"date": pd.Timestamp(d_date), "net_pnl": gross - fric.total_rupees,
                     "rule_day": d_date in rule_days})

    df = pd.DataFrame(rows)
    out = {
        "n_days": len(df),
        "net_all_days": round(float(df["net_pnl"].sum()), 0),
        "n_rule_days": int(df["rule_day"].sum()),
        "net_rule_selected": round(float(df.loc[df["rule_day"], "net_pnl"].sum()), 0),
        "frozen_rule_selected": FROZEN_RULE_NET,
        "wr_rule_selected": round(float((df.loc[df["rule_day"], "net_pnl"] > 0).mean()), 3),
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    df.to_csv(ARTIFACTS / "condor_e001_t1.csv", index=False)
    with open(ARTIFACTS / "e001_t1_audit.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"t-1-wall e001 condor: n={out['n_days']} days "
          f"(rule-selected {out['n_rule_days']})")
    print(f"rule-selected net: {out['net_rule_selected']:,.0f} "
          f"(frozen day-t-wall book: {FROZEN_RULE_NET:,.0f}) | wr {out['wr_rule_selected']}")
    print(f"all-days net: {out['net_all_days']:,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
