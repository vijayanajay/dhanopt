"""E019 verdict script — the six frozen gates from PREREG §4, decided mechanically.

Fail-only. Gate 6 (beat the same-universe equal-weight benchmark) is PRIMARY:
a long-only book in a bull market can show a fine CAGR and Sharpe from beta
alone, so "did the signal earn anything" is a stricter question than "did the
book make money".

Also runs the friction-decay comparison the experiment exists to measure:
identical signal, universe and cost model, two rebalance frequencies.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from experiments.e019_momentum.engine import (
    ARTIFACTS,
    CAPITAL,
    COSTS_NOTE,
    Costs,
    TOP_N,
    corporate_action_adjust,
    load_panel,
    momentum_rank,
    point_in_time_universe,
    precompute_liquidity,
    run_backtest,
    run_etf_leg,
)

ETF = "NIFTYBEES"


def equal_weight_benchmark(close, turn, rebal_every, costs, start_idx, end_idx):
    """Same universe, same costs, no signal: hold the whole liquid universe.

    This is the anti-beta control. A momentum book only "worked" if it beats
    this by a margin, because a long-only book in a rising market beats cash by
    construction.
    """
    n = len(close)
    rows = []
    holdings = None
    med = precompute_liquidity(turn)
    for i in range(start_idx, end_idx):
        if (i - start_idx) % rebal_every == 0:
            uni = point_in_time_universe(turn, i - 1, med)
            holdings = [s for s in uni if s in close.columns]
        if not holdings:
            continue
        fwd = i + 1
        if fwd > end_idx:
            break
        r0, r1 = close.iloc[i], close.iloc[fwd]
        rets = []
        for s in holdings:
            a, b = r0.get(s), r1.get(s)
            if a is not None and b is not None:
                a, b = float(a), float(b)
                if a > 0 and b > 0:
                    rets.append(b / a - 1.0)
        if not rets:
            continue
        rows.append({"date": close.index[fwd], "return": float(np.mean(rets))})
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
    }


import math  # noqa: E402  (used by equal_weight_benchmark)


def main() -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    close, turn, types = load_panel()
    adj, ca_stats = corporate_action_adjust(close)
    n = len(adj)
    start = 273 + 21 + 1          # 12-1 momentum needs a full year of history
    end = n - 2
    costs = Costs()

    print(f"panel {adj.shape} | corporate actions adjusted: {ca_stats}", flush=True)

    results = {"corporate_actions": ca_stats, "panel": {
        "sessions": n, "symbols": int(adj.shape[1]),
        "start": str(adj.index[start].date()), "end": str(adj.index[end].date()),
    }, "cost_model": COSTS_NOTE, "legs": {}}

    # --- cross-sectional momentum, monthly vs daily
    for label, every in (("monthly", 21), ("daily", 1)):
        print(f"running {label} cross-sectional leg...", flush=True)
        # NOTE: keyword args only. run_backtest's 6th positional is cost_mult,
        # and passing start/end positionally silently becomes a 295x cost
        # multiplier over a one-iteration window.
        df, m = run_backtest(adj, turn, every, top_n=TOP_N, costs=costs,
                             cost_mult=1.0, start_idx=start, end_idx=end)
        bdf, bm = equal_weight_benchmark(adj, turn, every, costs, start, end)
        _, m2 = run_backtest(adj, turn, every, top_n=TOP_N, costs=Costs(),
                             cost_mult=0.0, start_idx=start, end_idx=end)
        _, m2x = run_backtest(adj, turn, every, top_n=TOP_N, costs=costs,
                              cost_mult=2.0, start_idx=start, end_idx=end)
        m["zero_cost"] = {k: m2.get(k) for k in ("cagr", "sharpe", "max_dd", "total_return")}
        m["at_2x_cost"] = {k: m2x.get(k) for k in ("cagr", "sharpe", "max_dd")}
        m["benchmark_equal_weight"] = bm
        m["excess_sharpe_vs_benchmark"] = (
            round(m["sharpe"] - bm["sharpe"], 2) if m.get("sharpe") and bm.get("sharpe") else None
        )
        results["legs"][f"cross_{label}"] = m
        if not df.empty:
            df.to_csv(ARTIFACTS / f"cross_{label}_daily.csv", index=False)
        print(f"  {label}: CAGR {m.get('cagr')} Sharpe {m.get('sharpe')} "
              f"DD {m.get('max_dd')} benchSharpe {bm.get('sharpe')}", flush=True)

    # --- ETF time-series leg
    print("running ETF leg...", flush=True)
    edf, em = run_etf_leg(adj, turn, ETF, 21, costs)
    results["legs"]["etf_monthly"] = em
    print(f"  ETF: {em}", flush=True)

    # --- gates
    m_m = results["legs"]["cross_monthly"]
    m_d = results["legs"]["cross_daily"]
    uni = [len(point_in_time_universe(turn, i, precompute_liquidity(turn)))
           for i in range(start, end, 21)]
    gates = []

    gates.append({
        "n": 1, "name": "Universe",
        "bar": ">= 100 symbols on >= 90% of rebalance dates",
        "observed": f"median {int(np.median(uni))}, min {int(np.min(uni))} liquid names",
        "pass": bool(np.median(uni) >= 100 and np.mean([u >= 100 for u in uni]) >= 0.90),
    })

    gates.append({
        "n": 2, "name": "Capacity",
        "bar": ">= 60 rebalances per leg",
        "observed": f"monthly {m_m.get('rebalances')}, daily {m_d.get('rebalances')}",
        "pass": bool(m_m.get("rebalances", 0) >= 60 and m_d.get("rebalances", 0) >= 60),
    })

    gates.append({
        "n": 3, "name": "Edge (monthly, primary)",
        "bar": "net CAGR > 15% AND Sharpe >= 0.8 AND max DD <= 30%",
        "observed": f"CAGR {m_m.get('cagr')}, Sharpe {m_m.get('sharpe')}, DD {m_m.get('max_dd')}",
        "pass": bool((m_m.get("cagr") or -1) > 0.15 and (m_m.get("sharpe") or -1) >= 0.8
                     and (m_m.get("max_dd") or -1) >= -0.30),
    })

    gates.append({
        "n": 4, "name": "Edge (daily, descriptive)",
        "bar": "reported, not gated",
        "observed": f"CAGR {m_d.get('cagr')}, Sharpe {m_d.get('sharpe')}, DD {m_d.get('max_dd')}",
        "pass": True,
    })

    at2 = (m_m.get("at_2x_cost") or {}).get("cagr")
    gates.append({
        "n": 5, "name": "Friction resilience (monthly)",
        "bar": "net positive at 2.0x cost",
        "observed": f"2x-cost CAGR {at2}",
        "pass": bool((at2 or -1) > 0),
    })

    exc = m_m.get("excess_sharpe_vs_benchmark")
    gates.append({
        "n": 6, "name": "No illusion (PRIMARY)",
        "bar": "monthly Sharpe exceeds same-universe equal-weight by >= 0.2",
        "observed": f"excess Sharpe {exc} (momentum {m_m.get('sharpe')} vs EW {(m_m.get('benchmark_equal_weight') or {}).get('sharpe')})",
        "pass": bool((exc or -99) >= 0.2),
    })

    verdict = "PASS" if all(g["pass"] for g in gates) else "FAIL"
    failed = [g["n"] for g in gates if not g["pass"]]
    out = {"verdict": verdict, "failed_criteria": failed, "gates": gates, "results": results}
    with open(ARTIFACTS / "verdict.json", "w") as f:
        json.dump(out, f, indent=2, default=str)

    print(f"\nE019 VERDICT: {verdict} (failed: {failed or 'none'})\n")
    for g in gates:
        print(f"  [{'PASS' if g['pass'] else 'FAIL'}] {g['n']}. {g['name']:<26} "
              f"bar: {g['bar']:<58} got: {g['observed']}")


if __name__ == "__main__":
    main()
