"""Marks sweep: validate EVERY breach-book session's entry marks (not 5 samples).

The handoff's last data-side pre-live gate: "sweep the remaining ~40 breach trades'
open marks before stage-1 go-live". This runs marks_validation_v2.validate_session
over all 249 breach_spread sessions (2021-01 → 2026-09) and judges the book at the
level that matters: does the trade's CREDIT built from Dhan candle opens match the
credit built from bhavcopy opens? A few points of stitching noise on a wing is noise;
a wrong credit is a wrong book.

Chunked + checkpointed: 20 API requests per session (ATM±10 × both sides) at the
v2 pacing (~0.55s + latency), so the full sweep takes ~1-3h. State lives in
artifacts/marks_sweep_checkpoint.json (one result per date, written after each
session); `--max N` caps new sessions per invocation, making the run resumable.

Run: python -m experiments.e005_theta_condor.marks_sweep [--max 40]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd
import requests

from experiments.e005_theta_condor.marks_validation_v2 import validate_session

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
CHECKPOINT = ARTIFACTS / "marks_sweep_checkpoint.json"
SUMMARY = ARTIFACTS / "marks_sweep.json"
BREACH_CSV = ARTIFACTS / "breach_spread_target_100.csv"


def _sessions() -> list[str]:
    bs = pd.read_csv(BREACH_CSV)
    return sorted(pd.to_datetime(bs["date"]).dt.strftime("%Y-%m-%d").unique())


def _load_checkpoint() -> dict:
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text())
    return {}


def _save_checkpoint(cp: dict) -> None:
    tmp = CHECKPOINT.with_suffix(".tmp")
    tmp.write_text(json.dumps(cp, indent=1, default=str))
    tmp.replace(CHECKPOINT)


def _trade_pair_credit(res: dict, wall: float | None, side: str) -> dict | None:
    """The breach trade's pair credit (dhan vs bhav) in premium points for one session.

    The trade IS the traded side's pair: SELL the breached wall, BUY the ±150 wing.
    Only legs on `side` with BOTH open marks count; the SELL sign comes from the CSV
    wall strike (PARTIAL legs carry no `action`, and on breach days the wing can
    out-price the wall, so premium sorting would mislabel legs). Returns None when
    the pair isn't fully covered — that session's credit stays uncertified.
    """
    legs = [l for l in res.get("legs") or [] if str(l.get("leg", "")).startswith(side)]
    if wall is None or len(legs) != 2:
        return None
    if any("dhan_open" not in l or "bhav_open" not in l for l in legs):
        return None
    dhan = bhav = 0.0
    for l in legs:
        sign = 1.0 if abs(float(str(l["leg"])[len(side):]) - float(wall)) < 0.5 else -1.0
        dhan += sign * float(l["dhan_open"])
        bhav += sign * float(l["bhav_open"])
    return {"dhan": round(dhan, 2), "bhav": round(bhav, 2), "diff": round(dhan - bhav, 2)}


def aggregate(cp: dict) -> dict:
    rows = []
    side_by_date, wall_by_date = {}, {}
    if BREACH_CSV.exists():
        bs = pd.read_csv(BREACH_CSV)
        d = pd.to_datetime(bs["date"]).dt.strftime("%Y-%m-%d")
        side_by_date = dict(zip(d, bs["side"]))
        wall_by_date = dict(zip(d, bs["wall"]))
    for date, res in sorted(cp.items()):
        status = res.get("status")
        entry = {"date": date, "status": status}
        if status == "VALIDATED":
            legs = res.get("legs") or []
            ok = [l for l in legs if l.get("status") == "OK"]
            partial = [l for l in legs if l.get("status") == "PARTIAL"]
            entry.update(
                n_legs_ok=len(ok), n_legs_partial=len(partial),
                max_open_diff=res.get("max_open_diff"),
                max_close_diff=res.get("max_close_diff"),
                opens_exact=res.get("opens_match_exactly"),
                credit_bhav=res.get("credit_bhav"),
            )
            info = _trade_pair_credit(res, wall_by_date.get(date),
                                      {"put": "PE", "call": "CE"}.get(str(side_by_date.get(date, ""))))
            if info:
                entry["pair_credit_dhan_pts"] = info["dhan"]
                entry["pair_credit_bhav_pts"] = info["bhav"]
                entry["credit_diff"] = info["diff"]
                entry["credit_diff_pct"] = round(100 * info["diff"] / info["bhav"], 2) if info["bhav"] else None
        rows.append(entry)
    ok_rows = [r for r in rows if r["status"] == "VALIDATED"]
    with_credit = [r for r in ok_rows if "credit_diff" in r]
    credit_diffs = [abs(r["credit_diff"]) for r in with_credit]
    opens_exact = [r for r in ok_rows if r.get("opens_exact")]
    summary = {
        "n_sessions": len(rows),
        "n_validated": len(ok_rows),
        "n_failed": len(rows) - len(ok_rows),
        "failures": {r["date"]: r["status"] for r in rows if r["status"] != "VALIDATED"},
        "n_traded_credit_covered": len(with_credit),
        "n_opens_exact_all_legs": len(opens_exact),
        "max_abs_open_diff": max((r["max_open_diff"] for r in ok_rows if r.get("max_open_diff") is not None), default=None),
        "max_abs_close_diff": max((r["max_close_diff"] for r in ok_rows if r.get("max_close_diff") is not None), default=None),
        "max_abs_credit_diff": max(credit_diffs) if credit_diffs else None,
        "p99_abs_credit_diff": sorted(credit_diffs)[int(0.99 * len(credit_diffs))] if credit_diffs else None,
        "n_credit_within_1pt": sum(d < 1.0 for d in credit_diffs),
        "n_credit_within_3pts": sum(d < 3.0 for d in credit_diffs),
        "worst_credit_trades": sorted(with_credit, key=lambda r: -abs(r["credit_diff"]))[:10],
        "note": ("Breach-book entry marks swept across all sessions via Dhan Expired-Options "
                 "API (rollingoption). credit_diff = the breach trade's traded-side pair "
                 "credit (SELL wall − BUY ±150 wing, 09:15-09:20 opens), Dhan minus bhavcopy, "
                 "in premium points; sessions whose traded-side legs lack an open mark are "
                 "not counted."),
    }
    return {"summary": summary, "sessions": rows}


def main() -> int:
    import config

    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=None, help="max NEW sessions this invocation")
    args = ap.parse_args()

    token = config.DHAN_ACCESS_TOKEN
    todo = _sessions()
    cp = _load_checkpoint()
    remaining = [d for d in todo if d not in cp]
    print(f"{len(todo)} breach sessions | {len(cp)} already swept | {len(remaining)} to go")

    done = 0
    for i, date in enumerate(remaining):
        if args.max is not None and done >= args.max:
            print(f"--max {args.max} reached; stopping (checkpoint keeps progress)")
            break
        for attempt in (1, 2, 3):
            try:
                res = validate_session(token, date)
                break
            except requests.RequestException as e:
                wait = 30 * attempt
                print(f"  {date}: network error ({e}); retry in {wait}s")
                time.sleep(wait)
                res = None
        if res is None:
            res = {"date": date, "status": "ERROR_NETWORK"}
        cp[date] = res
        _save_checkpoint(cp)
        done += 1
        flag = ""
        if res.get("status") == "VALIDATED":
            flag = (f" opens_exact={res['opens_match_exactly']}"
                    f" max_open={res['max_open_diff']:.2f} max_close={res['max_close_diff']:.2f}")
        print(f"[{len(cp)}/{len(todo)}] {date}: {res.get('status')}{flag}", flush=True)
        time.sleep(1.0)

    if all(d in cp for d in todo):
        out = aggregate(cp)
        SUMMARY.write_text(json.dumps(out, indent=1, default=str))
        s = out["summary"]
        print(f"\nSWEPT {s['n_sessions']} sessions: {s['n_validated']} validated, "
              f"{s['n_failed']} failed")
        print(f"traded-side credit covered: {s['n_traded_credit_covered']}/{s['n_validated']} | "
              f"opens exact everywhere: {s['n_opens_exact_all_legs']} | "
              f"max |credit diff| = {s['max_abs_credit_diff']}")
        print(f"written: {SUMMARY}")
    else:
        print(f"\ncheckpoint at {len(cp)}/{len(todo)}; re-run to continue")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
