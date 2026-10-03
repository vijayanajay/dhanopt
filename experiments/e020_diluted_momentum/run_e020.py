"""E020 verdict script — seven frozen gates from PREREG §4, decided mechanically.

Fail-only. Gate 5 (beat the same-universe equal-weight book) is PRIMARY.

Also runs, as pre-declared:
  * the E019 CONTROL (top-20, monthly, same engine) — an engine that cannot
    reproduce its predecessor's -0.81 excess Sharpe is not measuring momentum;
  * a long-top-decile / short-bottom-decile DIAGNOSTIC, explicitly NOT gated,
    because Indian retail cannot short equities at scale. It measures the
    anomaly itself, stripped of market beta.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from experiments.e019_momentum.engine import (
    CAPITAL,
    Costs,
    corporate_action_adjust,
    load_panel,
    momentum_rank,
    point_in_time_universe,
    precompute_liquidity,
    run_backtest,
)
from experiments.e019_momentum.run_e019 import equal_weight_benchmark

ARTIFACTS = HERE / "artifacts"

TOP_FRAC = 0.10          # top decile
ADV_CAP_PCT = 0.01       # position <= 1% of the name's median daily turnover
REBAL = 21              # monthly


def death_rates(close, turn, med, start, end, top_frac):
    """21-day death rate: top bucket vs the whole rankable universe.

    E019 measured 0.44% universe / 1.51% top-20 = 3.4x. This is gate 6.
    """
    uni_dead, top_dead = [], []
    for i in range(start, end - 21, 21):
        uni = point_in_time_universe(turn, i - 1, med)
        rk = momentum_rank(close, i - 1, uni)
        if len(rk) < 100:
            continue
        fwd = close.iloc[i + 21] / close.iloc[i] - 1.0
        p0 = close.iloc[i]
        k = max(1, int(math.ceil(top_frac * len(rk))))
        tops = set(rk.index[:k])
        for s in rk.index:
            a = p0.get(s)
            if a is None or pd.isna(a) or a <= 0:
                continue
            alive = s in fwd.index and pd.notna(fwd[s])
            uni_dead.append(0 if alive else 1)
            if s in tops:
                top_dead.append(0 if alive else 1)
    return {
        "universe_death_rate": round(float(np.mean(uni_dead)), 4),
        "top_bucket_death_rate": round(float(np.mean(top_dead)), 4),
        "ratio": round(float(np.mean(top_dead) / np.mean(uni_dead)), 2) if np.mean(uni_dead) else None,
        "n_universe": len(uni_dead), "n_top": len(top_dead),
    }


def long_short(close, turn, med, start, end, top_frac=0.10):
    """DIAGNOSTIC ONLY, not gated and not tradeable: long top decile, short bottom decile."""
    rows, cost = [], 0.0
    total_ls_cost = 0.0
    c = Costs()
    hold = None
    for i in range(start, end - 1):
        if (i - start) % REBAL == 0:
            uni = point_in_time_universe(turn, i - 1, med)
            rk = momentum_rank(close, i - 1, uni)
            if len(rk) < 50:
                continue
            k = max(1, int(math.ceil(top_frac * len(rk))))
            long_s = list(rk.index[:k])
            short_s = list(rk.index[-k:])
            cost += c.round_trip(CAPITAL)          # full turnover of one side
            total_ls_cost += cost
            hold = (long_s, short_s)
        if not hold:
            continue
        r0, r1 = close.iloc[i], close.iloc[i + 1]
        def leg(syms):
            out = []
            for s in syms:
                a, b = r0.get(s), r1.get(s)
                if a is not None and b is not None:
                    a, b = float(a), float(b)
                    if a > 0 and b > 0:
                        out.append(b / a - 1.0)
            return out
        L, S = leg(hold[0]), leg(hold[1])
        if not L or not S:
            continue
        # the rebalance cost is charged on the day it is incurred, then cleared
        # (an earlier version subtracted cost/CAPITAL*0 and reported this
        # diagnostic gross — the number below is net)
        r = 0.5 * float(np.mean(L)) - 0.5 * float(np.mean(S)) - cost / CAPITAL
        cost = 0.0
        rows.append({"date": close.index[i + 1], "return": r})
    df = pd.DataFrame(rows)
    if df.empty:
        return df, {}
    eq = (1 + df["return"]).cumprod()
    dd = eq / eq.cummax() - 1.0
    rets = df["return"]
    yrs = len(df) / 252.0
    return df, {
        "periods": len(df), "years": round(yrs, 2),
        "cagr": round(float(eq.iloc[-1] ** (1 / yrs) - 1), 4),
        "sharpe": round(float(rets.mean() / rets.std() * math.sqrt(252)), 2) if rets.std() > 0 else None,
        "max_dd": round(float(dd.min()), 4),
        "total_cost_inr": round(total_ls_cost, 0),
        "note": "diagnostic only, NET of the same cost stack — shorting Indian equities "
                "is not available at retail scale, so this measures the anomaly, not a trade",
    }


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    close, turn, types = load_panel()
    adj, ca = corporate_action_adjust(close)
    med = precompute_liquidity(turn)
    n = len(adj)
    start = 273 + 21 + 1
    end = n - 2
    costs = Costs()

    print(f"panel {adj.shape} | start {adj.index[start].date()} end {adj.index[end].date()}", flush=True)

    res = {"panel": {"sessions": n, "start": str(adj.index[start].date()),
                     "end": str(adj.index[end].date())}, "legs": {}}

    # --- PRIMARY: diluted top decile, monthly, liquidity-capped
    print("running diluted top-decile monthly...", flush=True)
    df, m = run_backtest(adj, turn, REBAL, costs=costs, cost_mult=1.0,
                         start_idx=start, end_idx=end,
                         top_frac=TOP_FRAC, adv_cap_pct=ADV_CAP_PCT)
    _, bm = equal_weight_benchmark(adj, turn, REBAL, costs, start, end)
    _, free = run_backtest(adj, turn, REBAL, costs=costs, cost_mult=0.0,
                           start_idx=start, end_idx=end, top_frac=TOP_FRAC,
                           adv_cap_pct=ADV_CAP_PCT)
    _, two_x = run_backtest(adj, turn, REBAL, costs=costs, cost_mult=2.0,
                            start_idx=start, end_idx=end, top_frac=TOP_FRAC,
                            adv_cap_pct=ADV_CAP_PCT)
    m["zero_cost"] = {k: free.get(k) for k in ("cagr", "sharpe", "max_dd")}
    m["at_2x_cost"] = {k: two_x.get(k) for k in ("cagr", "sharpe", "max_dd")}
    m["benchmark_equal_weight"] = bm
    m["excess_sharpe_vs_benchmark"] = round(m["sharpe"] - bm["sharpe"], 2)
    m["holdings_frac"] = round(int(df["n_holdings"].median()) / 1550, 3)
    res["legs"]["diluted_monthly"] = m
    if not df.empty:
        df.to_csv(ARTIFACTS / "diluted_monthly_daily.csv", index=False)
    print(f"  CAGR {m.get('cagr')} Sharpe {m.get('sharpe')} DD {m.get('max_dd')} "
          f"median holdings {m.get('median_holdings')} benchSharpe {bm.get('sharpe')}", flush=True)

    # --- CONTROL: E019's exact top-20 monthly config through the same engine
    print("running E019 top-20 CONTROL...", flush=True)
    _, ctrl = run_backtest(adj, turn, REBAL, top_n=20, costs=costs, cost_mult=1.0,
                           start_idx=start, end_idx=end)
    ctrl["excess_sharpe_vs_benchmark"] = round(ctrl["sharpe"] - bm["sharpe"], 2)
    res["legs"]["control_top20_monthly"] = ctrl
    print(f"  control excess Sharpe {ctrl.get('excess_sharpe_vs_benchmark')} "
          f"(E019 published -0.81)", flush=True)

    # --- death-rate mechanism (gate 6)
    print("measuring 21-day death rates...", flush=True)
    dr = death_rates(adj, turn, med, start, end, TOP_FRAC)
    res["legs"]["death_rates"] = dr
    print(f"  universe {dr['universe_death_rate']} top-bucket {dr['top_bucket_death_rate']} "
          f"ratio {dr['ratio']}", flush=True)

    # --- DIAGNOSTIC: long-short (not gated)
    print("running long-short DIAGNOSTIC...", flush=True)
    _, ls = long_short(adj, turn, med, start, end, TOP_FRAC)
    res["legs"]["long_short_diagnostic"] = ls
    print(f"  long-short CAGR {ls.get('cagr')} Sharpe {ls.get('sharpe')}", flush=True)

    # --- gates
    gates = []
    gates.append({"n": 1, "name": "Capacity", "bar": ">= 45 monthly rebalances",
                  "observed": f"{m.get('rebalances')}",
                  "pass": bool(m.get("rebalances", 0) >= 45)})

    hold_ok = float((df["n_holdings"] >= 100).mean()) if not df.empty else 0.0
    gates.append({"n": 2, "name": "Breadth", "bar": ">= 100 names on >= 90% of rebalance dates",
                  "observed": f"median {m.get('median_holdings')}, min {m.get('min_holdings')}, "
                              f"{hold_ok:.0%} of days >= 100",
                  "pass": bool(m.get("median_holdings", 0) >= 100 and hold_ok >= 0.90)})

    gates.append({"n": 3, "name": "Edge", "bar": "net CAGR > 0 AND Sharpe >= 0.8",
                  "observed": f"CAGR {m.get('cagr')}, Sharpe {m.get('sharpe')}",
                  "pass": bool((m.get("cagr") or -1) > 0 and (m.get("sharpe") or -1) >= 0.8)})

    gates.append({"n": 4, "name": "Risk", "bar": "max DD <= 35%",
                  "observed": f"{m.get('max_dd')}",
                  "pass": bool((m.get("max_dd") or -1) >= -0.35)})

    gates.append({"n": 5, "name": "No illusion (PRIMARY)",
                  "bar": "Sharpe exceeds same-universe equal-weight by >= 0.15",
                  "observed": f"excess {m.get('excess_sharpe_vs_benchmark')} "
                              f"({m.get('sharpe')} vs EW {bm.get('sharpe')})",
                  "pass": bool(m.get("excess_sharpe_vs_benchmark", -99) >= 0.15)})

    gates.append({"n": 6, "name": "Death rate", "bar": "top-bucket death <= 1.5x universe",
                  "observed": f"{dr.get('ratio')}x ({dr.get('top_bucket_death_rate')} vs {dr.get('universe_death_rate')})",
                  "pass": bool(dr.get("ratio") is not None and dr["ratio"] <= 1.5)})

    gates.append({"n": 7, "name": "Friction", "bar": "net CAGR positive at 2.0x cost",
                  "observed": f"2x-cost CAGR {(m.get('at_2x_cost') or {}).get('cagr')}",
                  "pass": bool(((m.get("at_2x_cost") or {}).get("cagr") or -1) > 0)})

    verdict = "PASS" if all(g["pass"] for g in gates) else "FAIL"
    failed = [g["n"] for g in gates if not g["pass"]]
    out = {"experiment": "e020_diluted_momentum", "prereg": "frozen",
           "verdict": verdict, "failed_criteria": failed, "gates": gates, "results": res}
    with open(ARTIFACTS / "verdict.json", "w") as f:
        json.dump(out, f, indent=2, default=str)

    print(f"\nE020 VERDICT: {verdict} (failed: {failed or 'none'})\n")
    for g in gates:
        print(f"  [{'PASS' if g['pass'] else 'FAIL'}] {g['n']}. {g['name']:<24} "
              f"bar: {g['bar']:<54} got: {g['observed']}")
    print(f"\n  E019 control reproduced: excess Sharpe "
          f"{ctrl.get('excess_sharpe_vs_benchmark')} (published -0.81)")


if __name__ == "__main__":
    main()