"""E011 Slippage Cliff: Stress-tests delta-neutral VRP replay under elevated slippage.

Evaluates Kill Criterion 3:
Retains positive net expectancy at >= 2.5x modeled slippage.
"""

import json
from pathlib import Path
import sys
from typing import Dict, List

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from experiments.e011_vrp_delta_hedge.replay_vrp import run_vrp_replay

ARTIFACTS = HERE / "artifacts"


def sweep_slippage() -> List[Dict]:
    multipliers = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
    results = []
    cache: Dict = {}
    for m in multipliers:
        _, metrics = run_vrp_replay(slippage_mult=m, candle_cache=cache)
        results.append(metrics)
        print(f"Slippage {m:.1f}x: Net Rs. {metrics['total_net_pnl']:,.2f} | PF: {metrics['profit_factor']} | Sharpe: {metrics['sharpe_ratio']} | Max DD: Rs. {metrics['max_drawdown_inr']:,.2f}")

    with open(ARTIFACTS / "slippage_cliff.json", "w") as f:
        json.dump(results, f, indent=2)

    return results


if __name__ == "__main__":
    sweep_slippage()
