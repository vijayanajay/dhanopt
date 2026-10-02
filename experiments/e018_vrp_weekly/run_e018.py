"""E018 verdict script — the six frozen gates from PREREG §4, decided mechanically.

Fail-only. No bar can be reinterpreted after the fact. Criterion 4 (contract
identity) is a hard veto, not a score. Run this, get PASS or FAIL, done.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from experiments.e018_vrp_weekly.replay_weekly import run_replay, ARTIFACTS, SLIPPAGE_PTS

CAPITAL = 200_000.0
YEARS = 5.7


def slippage_curve(df: pd.DataFrame) -> list[dict]:
    """Exact reconstruction at other per-leg slippage: gross is slippage-free,
    friction is linear in p, so net(p) = net(1.5) - (p - 1.5) * 8 * lot."""
    out = []
    for p in (1.0, 1.5, 2.0, 2.5, 3.0):
        net = df["net"] - (p - SLIPPAGE_PTS) * 8 * df["lot"]
        gp = float(net[net > 0].sum())
        gl = abs(float(net[net < 0].sum()))
        out.append({
            "half_spread_pts": p,
            "total_net": round(float(net.sum()), 2),
            "net_ev": round(float(net.mean()), 2),
            "profit_factor": round(gp / gl, 2) if gl > 0 else None,
            "win_rate": round(float((net > 0).mean()), 4),
        })
    return out


def main() -> None:
    df, m = run_replay()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if not df.empty:
        df.to_csv(ARTIFACTS / "weekly_daily.csv", index=False)

    curve = slippage_curve(df)
    n = len(df)
    net_1x5 = float(df["net"].sum())
    breakeven = SLIPPAGE_PTS + net_1x5 / (8 * float(df["lot"].sum())) if n else None
    at_2x = next(c["total_net"] for c in curve if c["half_spread_pts"] == 2.0)

    gates = []

    # 1 — capacity
    gates.append({
        "n": 1, "name": "Capacity",
        "bar": ">= 30 trades",
        "observed": f"{n} trades ({n / YEARS:.1f}/yr)",
        "pass": bool(n >= 30),
    })

    # 2 — edge
    gates.append({
        "n": 2, "name": "Edge",
        "bar": "net EV/trade >= +400 AND PF >= 1.5, n >= 30",
        "observed": f"EV {m.get('net_ev')}, PF {m.get('profit_factor')}, n={n}",
        "pass": bool(m.get("net_ev", 0) >= 400 and (m.get("profit_factor") or 0) >= 1.5 and n >= 30),
    })

    # 3 — drawdown
    dd_pct = m.get("max_dd_pct", 100)
    gates.append({
        "n": 3, "name": "Drawdown",
        "bar": "<= 15% of 2,00,000 (30,000)",
        "observed": f"-{m.get('max_dd'):,.0f} ({dd_pct}%)",
        "pass": bool(dd_pct <= 15.0),
    })

    # 4 — contract identity (hard veto)
    viol = m.get("identity_violations", 1)
    gates.append({
        "n": 4, "name": "Contract identity",
        "bar": "0 mismatched expiries",
        "observed": f"{viol} violations across {n} trades",
        "pass": bool(viol == 0),
    })

    # 5 — friction resilience
    gates.append({
        "n": 5, "name": "Friction resilience",
        "bar": "net > 0 at 2.0x slippage",
        "observed": f"{at_2x:,.0f} at 2.0x; breakeven half-spread {breakeven:.2f} pts"
        if breakeven is not None else "n/a",
        "pass": bool(at_2x > 0),
    })

    # 6 — no roundness
    wr = m.get("win_rate", 1.0)
    gates.append({
        "n": 6, "name": "No roundness",
        "bar": "WR <= 85%",
        "observed": f"{wr:.1%}",
        "pass": bool(wr <= 0.85),
    })

    verdict = "PASS" if all(g["pass"] for g in gates) else "FAIL"
    failed = [g["n"] for g in gates if not g["pass"]]

    out = {
        "verdict": verdict,
        "failed_criteria": failed,
        "gates": gates,
        "metrics": m,
        "slippage_curve": curve,
        "breakeven_half_spread_pts": round(breakeven, 2) if breakeven is not None else None,
    }
    with open(ARTIFACTS / "verdict.json", "w") as f:
        json.dump(out, f, indent=2)

    print(f"\nE018 VERDICT: {verdict}  (failed: {failed or 'none'})\n")
    for g in gates:
        print(f"  [{'PASS' if g['pass'] else 'FAIL'}] {g['n']}. {g['name']:<20} "
              f"bar: {g['bar']:<42} got: {g['observed']}")
    print(f"\n  breakeven half-spread: {breakeven:.2f} pts/leg" if breakeven else "")
    return out


if __name__ == "__main__":
    main()
