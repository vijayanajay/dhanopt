"""Daily shadow-runner: evaluate the breach gate on the latest session's data and
append would-have-traded records to a CSV, so paper-trade evidence accumulates.

Idempotent by date: re-running after a data refresh rewrites that day's row instead
of duplicating it. Same gate, fills, drift, and stress as paper_trade.evaluate_day —
this wrapper owns only cadence and persistence.

Run (manually or scheduled each evening after the data download):
  python -m experiments.e005_theta_condor.shadow_runner [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from experiments.e005_theta_condor.paper_trade import (
    ROW_COLUMNS, evaluate_day, _partition_calendar, _prev_session_map)

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
LOG = ARTIFACTS / "shadow_log.csv"


def _append_row(new: dict) -> str:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if LOG.exists():
        log = pd.read_csv(LOG)
        log = log[log["date"] != new["date"]]  # idempotent: rewrite today, never duplicate
        log = pd.concat([log, pd.DataFrame([new])], ignore_index=True)
    else:
        log = pd.DataFrame([new])
    log = log.sort_values("date")
    log.to_csv(LOG, index=False)
    return f"{LOG} ({len(log)} rows)"


def main() -> int:
    import config

    ap = argparse.ArgumentParser(description="Breach-gate daily shadow-runner")
    ap.add_argument("--date", default=None, help="evaluate this session instead of the latest")
    args = ap.parse_args()

    cal = _partition_calendar(config.HISTORICAL_DATA_DIR)
    prev_map = _prev_session_map(cal.keys())
    d = pd.Timestamp(args.date).date() if args.date else max(prev_map)
    row = evaluate_day(d, cal, prev_map)
    full = {c: row.get(c) for c in ROW_COLUMNS + ["put_wall_t1", "call_wall_t1"]}

    print(f"{d}: signal={row['signal']} side={row.get('side')} wall={row.get('wall')} "
          f"spot_open={row.get('spot_open')} dte0={row.get('dte0')} "
          f"credit={row.get('credit_pts')} max_drift={row.get('max_leg_drift')} "
          f"exit={row.get('exit_reason')} net={row.get('net_pnl')} "
          f"net_stressed={row.get('net_pnl_stressed')}")
    print(f"appended -> {_append_row(full)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
