"""e007 Phase A: fetch OPENING-OI option chains for the 249 breach days.

The frozen breach book's walls come from day-t EOD OI (6h of look-ahead relative to
the 09:15 entry — see paper_trade Add. 8). Gate 0 (handoff §7) needs the walls as
they stood AT the open. Probed (2026-10-01): the Expired-Options API's per-bar `oi`
is timestamped intraday OI (PE 22850 on 2026-09-25: 3.43M @09:15 -> 5.98M @12:00),
so the 09:15-09:20 bar's OI is the true opening OI.

Per session: ATM±10 x CALL/PUT (20 requests, v2 pacing) -> dedupe on
(timestamp, strike, side) -> keep each strike's OPENING bar (first bar < 09:20):
strike, side, oi, open, bar time, plus API spot at the open. Checkpointed like
marks_sweep; ~40 s/session (~2.5-3 h for 249).

Strikes whose first bar is later than 09:20 are stored with `oi_open=None` + their
earliest bar — the opening chain is then incomplete that day (rolling-window edge);
build_book decides how to treat those days.

Run: python -m experiments.e007_open_oi.fetch_open_oi [--max 40]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
CHECKPOINT = ARTIFACTS / "e007_open_oi.json"
BREACH_CSV = HERE.parent / "e005_theta_condor" / "artifacts" / "breach_spread_target_100.csv"

ROLLING_URL = "https://api.dhan.co/v2/charts/rollingoption"
REQUIRED = ["open", "close", "oi", "strike", "spot"]
OFFSETS = [f"ATM-{k}" for k in range(10, 1, -1)] + [f"ATM+{k}" for k in range(2, 11)]


def _breach_dates() -> list[str]:
    bs = pd.read_csv(BREACH_CSV)
    return sorted(pd.to_datetime(bs["date"]).dt.strftime("%Y-%m-%d").unique())


def _rolling(token: str, strike: str, drv: str, d: str) -> pd.DataFrame:
    body = {"exchangeSegment": "NSE_FNO", "interval": "5", "securityId": "13",
            "instrument": "OPTIDX", "expiryFlag": "WEEK", "expiryCode": 1,
            "strike": strike, "drvOptionType": drv,
            "requiredData": REQUIRED, "fromDate": d, "toDate": d}
    r = requests.post(ROLLING_URL, headers={"Accept": "application/json",
                                            "Content-Type": "application/json",
                                            "access-token": token},
                      data=json.dumps(body), timeout=120)
    r.raise_for_status()
    side = "ce" if drv == "CALL" else "pe"
    payload = (r.json().get("data") or {}).get(side) or {}
    if not payload.get("open"):
        return pd.DataFrame()
    df = pd.DataFrame({k: pd.Series(v) for k, v in payload.items()})
    df["option_type"] = side.upper()
    df["dt"] = pd.to_datetime(df["timestamp"], unit="s") + pd.Timedelta(hours=5, minutes=30)
    return df


def fetch_session(token: str, date: str) -> dict:
    frames = []
    for drv in ("CALL", "PUT"):
        for off in OFFSETS:
            df = _rolling(token, off, drv, date)
            if not df.empty:
                frames.append(df)
            time.sleep(0.55)
    if not frames:
        return {"date": date, "status": "NO_CANDLES", "opening": []}
    day = pd.concat(frames, ignore_index=True) \
            .drop_duplicates(subset=["timestamp", "strike", "option_type"], keep="first")
    day = day[pd.to_datetime(day["dt"]).dt.strftime("%Y-%m-%d") == date]
    if day.empty:
        return {"date": date, "status": "NO_CANDLES", "opening": []}

    day["hm"] = pd.to_datetime(day["dt"]).dt.strftime("%H:%M")
    rows = []
    spot_open = None
    for (strike, ot), g in day.groupby(["strike", "option_type"]):
        g = g.sort_values("dt")
        opening = g[g["hm"] < "09:20"]
        if opening.empty:
            first = g.iloc[0]
            rows.append({"strike": float(strike), "side": ot, "oi_open": None,
                         "open_price": None, "first_hm": str(first["hm"]),
                         "oi_first": float(first["oi"]) if pd.notna(first["oi"]) else None})
            continue
        b = opening.iloc[0]
        if spot_open is None:
            spot_open = float(b["spot"]) if pd.notna(b["spot"]) else None
        rows.append({"strike": float(strike), "side": ot,
                     "oi_open": float(b["oi"]) if pd.notna(b["oi"]) else None,
                     "open_price": float(b["open"]) if pd.notna(b["open"]) else None,
                     "first_hm": str(b["hm"]), "oi_first": None})
    rows.sort(key=lambda r: (r["side"], r["strike"]))
    return {"date": date, "status": "OK", "spot_open_api": spot_open, "opening": rows}


def main() -> int:
    import config

    ap = argparse.ArgumentParser(description="e007 opening-OI chain fetch")
    ap.add_argument("--max", type=int, default=None, help="max NEW sessions this invocation")
    args = ap.parse_args()

    token = config.DHAN_ACCESS_TOKEN
    todo = _breach_dates()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    cp = json.loads(CHECKPOINT.read_text()) if CHECKPOINT.exists() else {}
    remaining = [d for d in todo if d not in cp]
    print(f"{len(todo)} breach sessions | {len(cp)} already fetched | {len(remaining)} to go", flush=True)

    import requests as rq
    done = 0
    for date in remaining:
        if args.max is not None and done >= args.max:
            print(f"--max {args.max} reached; stopping (checkpoint keeps progress)", flush=True)
            break
        res = None
        for attempt in (1, 2, 3):
            try:
                res = fetch_session(token, date)
                break
            except rq.RequestException as e:
                wait = 30 * attempt
                print(f"  {date}: network error ({e}); retry in {wait}s", flush=True)
                time.sleep(wait)
        if res is None:
            res = {"date": date, "status": "ERROR_NETWORK", "opening": []}
        cp[date] = res
        tmp = CHECKPOINT.with_suffix(".tmp")
        tmp.write_text(json.dumps(cp, indent=1, default=str))
        tmp.replace(CHECKPOINT)
        done += 1
        n_open = sum(1 for r in res["opening"] if r.get("oi_open") is not None)
        print(f"[{len(cp)}/{len(todo)}] {date}: {res['status']} "
              f"strikes={len(res['opening'])} with_open_oi={n_open}", flush=True)
        time.sleep(1.0)

    print(f"\ncheckpoint at {len(cp)}/{len(todo)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
