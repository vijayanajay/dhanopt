"""Inverted-wall audit: how much of e001's frozen condor edge came from selling ITM calls?

e001's label builder has no put_wall < spot < call_wall guard, so days where the max-OI
wall sits on the wrong side of the open get traded anyway (a short ITM call is a delta
bet, not a premium-crush bet). This audit recovers the walls per day (e005.prepare_day,
e001's exact chain convention), classifies each e001 condor day, and splits the frozen
edge: valid structure vs inverted call wall vs inverted put wall.

Run: python -m experiments.e005_theta_condor.audit_inverted_walls
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from experiments.e005_theta_condor.replay_theta import HERE, _partition_calendar, prepare_day

ARTIFACTS = HERE / "artifacts"
E1 = HERE.parent / "e001_leakfree_replay" / "artifacts" / "labels_daily.csv"


def stats(sub: pd.DataFrame) -> dict:
    gp = sub.loc[sub.net_pnl > 0, "net_pnl"].sum()
    gl = abs(sub.loc[sub.net_pnl <= 0, "net_pnl"].sum())
    return {"n": len(sub), "wr": round(float((sub.net_pnl > 0).mean()), 3) if len(sub) else None,
            "net": round(float(sub.net_pnl.sum()), 0),
            "pf": round(float(gp / gl), 2) if gl else None}


def main() -> int:
    import config
    from core.feeds.intraday import available_dates

    labels = pd.read_csv(E1)
    labels["date"] = labels["date"].astype(str)
    condor = labels[(labels["archetype"] == "Iron Condor") & (labels["simulated"] == True)].copy()
    rule_days = set(labels[(labels["archetype"] == "Iron Condor") & (labels["selected_by_rule"] == True)]["date"])

    walls = {}
    for d in available_dates():
        prep = prepare_day(d, _partition_calendar(config.HISTORICAL_DATA_DIR), rule_days)
        if prep and "exit_reason" not in prep:
            walls[prep["date"][:10]] = {"put_wall": prep["put_wall"], "call_wall": prep["call_wall"],
                                        "spot_open": prep["spot_open"]}
    print(f"wall days recovered: {len(walls)}")

    w = pd.DataFrame(walls).T.reset_index().rename(columns={"index": "date"})
    m = condor.merge(w, on="date", how="inner")
    m["structure"] = "valid"
    m.loc[m.call_wall <= m.spot_open, "structure"] = "inverted_call"
    m.loc[m.put_wall >= m.spot_open, "structure"] = "inverted_put"
    m.loc[(m.call_wall <= m.spot_open) & (m.put_wall >= m.spot_open), "structure"] = "inverted_both"

    out = {"all_days": stats(m), "valid": {}, "by_structure": {}}
    valid = m[m.structure == "valid"]
    out["valid"] = stats(valid)
    out["valid_rule_selected"] = stats(valid[valid.selected_by_rule == True])
    out["all_rule_selected"] = stats(m[m.selected_by_rule == True])
    for s, sub in m.groupby("structure"):
        out["by_structure"][s] = {**stats(sub), "rule_selected": stats(sub[sub.selected_by_rule == True])}

    total_edge = out["all_days"]["net"]
    inv_edge = total_edge - out["valid"]["net"]
    print(f"\ne001 condor book, all simulated days: n={out['all_days']['n']} net={total_edge:,.0f} "
          f"pf={out['all_days']['pf']}")
    print(f"valid structure only:                 n={out['valid']['n']} net={out['valid']['net']:,.0f} "
          f"pf={out['valid']['pf']}")
    print(f"edge from inverted-wall days: {inv_edge:,.0f} "
          f"({inv_edge / total_edge * 100:.1f}% of the frozen edge)")
    print(f"rule-selected subset: all={out['all_rule_selected']['net']:,.0f} -> "
          f"valid-only={out['valid_rule_selected']['net']:,.0f}")
    for s, r in out["by_structure"].items():
        print(f"  {s:<15} n={r['n']:>4} net={r['net']:>10,.0f} pf={r['pf']} "
              f"| rule-sel n={r['rule_selected']['n']:>3} net={r['rule_selected']['net']:>10,.0f}")

    with open(ARTIFACTS / "inverted_wall_audit.json", "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nwritten: {ARTIFACTS / 'inverted_wall_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
