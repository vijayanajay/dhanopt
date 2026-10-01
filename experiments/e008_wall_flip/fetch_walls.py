"""e008 Phase A: per-5-min opening-to-close OI chains for all dte<=1 sessions.

The scoped signal (experiment.md, e008 scope): intraday wall flips — when spot first
crosses a FRESH wall built from the chain OI as it stood at that bar — entered at the
NEXT bar's open (t+1-fill hard rule). Testing it honestly needs the walls at every
bar of every dte<=1 session, not just at 09:15 (e007's scope).

Endpoint: the Dhan Expired-Options API whose per-bar `oi` is timestamped intraday OI
(probed twice: marks sweeps for prices, e007 for opening OI). Ceiling, pre-registered
in the scope: a strike exists in the rolling response only while within ATM±10, so
walls forming beyond it mid-session are invisible -> the sim undercounts late flips;
build_signal reports the per-day visibility so the kill criteria are judged on
certified data only.

Storage: one JSON per session under artifacts/walls/ (small, independently
recoverable; a crash loses nothing). ~20 req/session, v2 pacing ~35-40 s/session,
~946 sessions -> ~10 h. Order is shuffled deterministically so a partial sweep is
a representative sample (spread across years), not just the front of the calendar.

Run: python -m experiments.e008_wall_flip.fetch_walls [--max 40]
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
WALLS_DIR = ARTIFACTS / "walls"
BREACH_CSV = HERE.parent / "e005_theta_condor" / "artifacts" / "breach_spread_target_100.csv"

ROLLING_URL = "https://api.dhan.co/v2/charts/rollingoption"
REQUIRED = ["open", "close", "oi", "strike", "spot"]
OFFSETS = [f"ATM-{k}" for k in range(10, 1, -1)] + [f"ATM+{k}" for k in range(2, 11)]


def _dte1_dates() -> list[str]:
    """All dte<=1 sim-able sessions: the breach book's own screening universe
    (breach_spread.py screened available_dates() for dte<=1 -> 946 + 249)."""
    from experiments.e005_theta_condor.replay_theta import _partition_calendar
    from experiments.e005_theta_condor.replay_theta import _safe_exp
    import config
    dates = []
    cal = _partition_calendar(config.HISTORICAL_DATA_DIR)
    for d in sorted(cal):
        df = pd.read_parquet(cal[d], columns=["symbol", "instrument", "expiry"])
        nifty = df[(df["symbol"] == "NIFTY") & (df["instrument"].isin(["OPTIDX", "IDO"]))]
        exps = [x for x in (_safe_exp(e) for e in nifty["expiry"].unique()) if x and x >= d]
        if exps and (min(exps) - d).days <= 1:
            dates.append(d.isoformat())
    return dates


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
        return {"date": date, "status": "NO_CANDLES", "bars": []}
    day = pd.concat(frames, ignore_index=True) \
            .drop_duplicates(subset=["timestamp", "strike", "option_type"], keep="first")
    day["dt"] = pd.to_datetime(day["timestamp"], unit="s") + pd.Timedelta(hours=5, minutes=30)
    day = day[day["dt"].dt.strftime("%Y-%m-%d") == date]
    if day.empty:
        return {"date": date, "status": "NO_CANDLES", "bars": []}
    bars = []
    for ts, g in day.groupby("timestamp"):
        bars.append({
            "ts": str(pd.to_datetime(ts, unit="s") + pd.Timedelta(hours=5, minutes=30)),
            "spot": float(g["spot"].dropna().iloc[0]) if g["spot"].notna().any() else None,
            "chain": [{"strike": float(r["strike"]), "side": r["option_type"],
                       "oi": float(r["oi"]) if pd.notna(r["oi"]) else None,
                       "open": float(r["open"]) if pd.notna(r["open"]) else None}
                      for _, r in g.iterrows()],
        })
    bars.sort(key=lambda b: b["ts"])
    return {"date": date, "status": "OK", "n_bars": len(bars),
            "n_strikes": day[["strike", "option_type"]].drop_duplicates().shape[0], "bars": bars}


def main() -> int:
    import config

    ap = argparse.ArgumentParser(description="e008 per-5-min wall fetch")
    ap.add_argument("--max", type=int, default=None, help="max NEW sessions this invocation")
    args = ap.parse_args()

    token = config.DHAN_ACCESS_TOKEN
    todo = _dte1_dates()
    rng = random.Random(42)  # deterministic shuffle -> partial sweeps are representative
    rng.shuffle(todo)
    WALLS_DIR.mkdir(parents=True, exist_ok=True)
    done = {p.stem for p in WALLS_DIR.glob("*.json")}
    remaining = [d for d in todo if d not in done]
    print(f"{len(todo)} dte<=1 sessions | {len(done)} already fetched | {len(remaining)} to go", flush=True)

    n = 0
    for date in remaining:
        if args.max is not None and n >= args.max:
            print(f"--max {args.max} reached; stopping", flush=True)
            break
        res = None
        for attempt in (1, 2, 3):
            try:
                res = fetch_session(token, date)
                break
            except requests.RequestException as e:
                wait = 30 * attempt
                print(f"  {date}: network error ({e}); retry in {wait}s", flush=True)
                time.sleep(wait)
        if res is None:
            res = {"date": date, "status": "ERROR_NETWORK", "bars": []}
        (WALLS_DIR / f"{date}.json").write_text(json.dumps(res, default=str))
        n += 1
        print(f"[{len(done) + n}/{len(todo)}] {date}: {res['status']}"
              + (f" bars={res.get('n_bars')} strikes={res.get('n_strikes')}" if res["status"] == "OK" else ""),
              flush=True)
        time.sleep(1.0)
    print(f"\n{len(done) + n}/{len(todo)} sessions on disk", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
