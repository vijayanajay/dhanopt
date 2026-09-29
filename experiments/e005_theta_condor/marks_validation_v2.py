"""Mark validation v2: extend the e005 bhavcopy mark check BACKWARD to expired contracts.

v1 (marks_validation.py) validated one session (2026-09-25) — the only week whose
contracts survive in the current scrip master. This version uses Dhan's Expired-Options
API (POST /v2/charts/rollingoption, minute-level expired data "last 5 years") to
validate sampled sessions across the full frozen window (2021 → 2026), i.e. every
era the e001/e002/e005/e011 numbers rest on.

API facts settled by probing (2026-09-29):
- strikes are SPOT-RELATIVE ('ATM', 'ATM+1', ... 'ATM+10' near expiry); the response
  carries the actual strike + spot per bar, so fixed-strike legs are recovered by
  filtering bars on strike == the leg's strike.
- expiryCode: 0 is rejected by the endpoint's falsy-zero parse; 1 = nearest expiry
  (community consensus), which for an expiry week is that week's contract.
- 'rolling' is literal: the series rolls to hold ATM+k as spot moves intraday, so the
  union of offset series covers the day; the per-bar strike field makes it exact.

Verdict semantics (inherited from v1): candle open == bhavcopy open to the paisa;
close allowed to differ by last-trade-vs-settlement timing (<10 pts on far wings).

Run: python -m experiments.e005_theta_condor.marks_validation_v2
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"

# Sessions sampled across the whole window and both expiry eras (Thu- and Tue-expiry).
# 2025-09-02: Tue-era expiry day (the era the production book trades).
# 2025-09-04: Tue-era non-expiry day (dte=2, nearest expiry = 09-09? — API nearest wins,
#             so this session validates the 09-09 contract's premium against bhavcopy).
# 2022-06-10 / 2021-01-05: depth corners of the frozen window (Thu era, lots 25).
SESSIONS = ["2021-01-05", "2022-06-10", "2025-09-02", "2025-09-04", "2026-09-25"]

WING = 150  # e001/e005 WING_OFFSET

ROLLING_URL = "https://api.dhan.co/v2/charts/rollingoption"
IST = timezone(timedelta(hours=5, minutes=30))
REQUIRED = ["open", "high", "low", "close", "iv", "volume", "strike", "oi", "spot"]
OFFSETS = [f"ATM-{k}" for k in range(10, 1, -1)] + [f"ATM+{k}" for k in range(2, 11)]  # doc max: ATM±10 near expiry


def _rolling(client_token: str, strike: str, drv: str, from_date: str, to_date: str) -> pd.DataFrame:
    body = {"exchangeSegment": "NSE_FNO", "interval": "5", "securityId": "13",
            "instrument": "OPTIDX", "expiryFlag": "WEEK", "expiryCode": 1,
            "strike": strike, "drvOptionType": drv,
            "requiredData": REQUIRED, "fromDate": from_date, "toDate": to_date}
    r = requests.post(ROLLING_URL, headers={"Accept": "application/json",
                                            "Content-Type": "application/json",
                                            "access-token": client_token},
                      data=json.dumps(body), timeout=120)
    r.raise_for_status()
    payload = r.json().get("data") or {}
    side = "ce" if drv == "CALL" else "pe"  # drvOptionType selects the side (probed)
    d = payload.get(side)
    if not d or not d.get("open"):
        return pd.DataFrame()
    df = pd.DataFrame({k: pd.Series(v) for k, v in d.items()})
    df["option_type"] = side.upper()
    df["dt"] = pd.to_datetime(df["timestamp"], unit="s") + pd.Timedelta(hours=5, minutes=30)
    return df


def _session_candles(token: str, date: str) -> pd.DataFrame:
    """Union of ATM±k series (both option sides) for the expiry week containing `date`."""
    exp = pd.Timestamp(date)
    frames = []
    for drv in ("CALL", "PUT"):
        for off in OFFSETS:
            df = _rolling(token, off, drv, str(exp.date()), str((exp + pd.Timedelta(days=1)).date()))
            if not df.empty:
                frames.append(df)
            time.sleep(0.55)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    # overlapping offset series serve the same contract; dedupe on (ts, strike, side)
    return out.drop_duplicates(subset=["timestamp", "strike", "option_type"], keep="first")


def validate_session(token: str, date: str) -> dict:
    from experiments.e005_theta_condor.replay_theta import _partition_calendar, prepare_day
    import config
    from experiments.common.lots import lot_for_date

    cal = _partition_calendar(config.HISTORICAL_DATA_DIR)
    ts = pd.Timestamp(date)
    prep = prepare_day(ts.date(), cal, set())  # lot_for_date compares datetime.date eras
    if prep is None or "exit_reason" in prep:
        return {"date": date, "status": prep.get("exit_reason", "NODATA") if prep else "NODATA"}

    candles = _session_candles(token, date)
    if candles.empty:
        return {"date": date, "status": "NO_CANDLES"}

    qty = lot_for_date(ts.date())
    legs = prep["legs"]
    rows = []
    for i, (leg, entry_mark) in enumerate(zip(legs, prep["entry"])):
        ot = "CE" if leg["is_call"] else "PE"
        strike = float(leg["strike"])
        sub = candles[(candles.option_type == ot)
                      & (pd.to_numeric(candles.strike, errors="coerce") == strike)
                      & (candles.dt.dt.date == ts.date())]
        if sub.empty:
            rows.append({"leg": f"{ot}{strike:.0f}", "status": "NO_BARS"})
            continue
        sub = sub.sort_values("dt")
        bhav_close = float(prep["exit"][i])
        # Open mark must come from the 09:15-09:20 slot; a strike the rolling series
        # only reaches later in the day has no observable open -> PARTIAL, excluded
        # from the opens_exact verdict.
        slot = sub[sub["dt"].dt.strftime("%H:%M") < "09:20"]
        # Close mark likewise needs an end-of-day bar: the rolling series only touches
        # a given strike while it is within ATM±k, so the last bar of a partial leg is
        # mid-day, NOT the settlement-time print.
        eod = sub[sub["dt"].dt.strftime("%H:%M") >= "15:20"]
        if slot.empty or eod.empty:
            row = {"leg": f"{ot}{strike:.0f}", "status": "PARTIAL",
                   "first_bar": str(sub.iloc[0]["dt"]), "last_bar": str(sub.iloc[-1]["dt"]),
                   "n_bars": int(len(sub))}
            if not slot.empty:
                row.update({"dhan_open": float(slot.iloc[0]["open"]),
                            "bhav_open": float(entry_mark),
                            "open_diff": round(float(slot.iloc[0]["open"]) - float(entry_mark), 2)})
            if not eod.empty:
                row.update({"dhan_close": float(eod.iloc[-1]["close"]),
                            "bhav_close": bhav_close,
                            "close_diff": round(float(eod.iloc[-1]["close"]) - bhav_close, 2)})
            rows.append(row)
            continue
        d_open = float(slot.iloc[0]["open"])
        d_close = float(eod.iloc[-1]["close"])
        rows.append({"leg": f"{ot}{strike:.0f}", "status": "OK",
                     "dhan_open": d_open, "bhav_open": float(entry_mark),
                     "open_diff": round(d_open - float(entry_mark), 2),
                     "dhan_close": d_close, "bhav_close": bhav_close,
                     "close_diff": round(d_close - bhav_close, 2),
                     "action": leg["action"], "dhan_bars": int(len(sub))})
    ok = [r for r in rows if r.get("status") == "OK"]
    partial = [r for r in rows if r.get("status") == "PARTIAL"]
    if not ok:
        return {"date": date, "status": "PARTIAL_ONLY" if partial else "ALL_LEGS_MISSING",
                "legs": rows}
    opens_exact = all(abs(r["open_diff"]) < 0.01 for r in ok)
    close_rows = [r for r in rows if "close_diff" in r]
    closes_ok = all(abs(r["close_diff"]) < 10.0 for r in close_rows)
    return {"date": date, "status": "VALIDATED", "legs": rows,
            "n_legs_ok": len(ok), "n_legs_partial": len(partial),
            "opens_match_exactly": opens_exact, "closes_match_last_trade": closes_ok,
            "max_open_diff": max(abs(r["open_diff"]) for r in ok),
            "max_close_diff": max((abs(r["close_diff"]) for r in close_rows), default=0.0),
            "credit_bhav": float(prep["credit"]), "lot": qty,
            "expiry": prep["expiry"]}


def main() -> int:
    import config
    token = config.DHAN_ACCESS_TOKEN
    results = []
    for date in SESSIONS:
        print(f"validating {date} ...")
        try:
            res = validate_session(token, date)
        except Exception as e:  # noqa: BLE001 — probe: API failures are findings
            res = {"date": date, "status": f"ERROR: {e}"}
        print(f"  -> {res.get('status')}"
              + (f" | opens_exact={res.get('opens_match_exactly')} "
                 f"max_open_diff={res.get('max_open_diff')} "
                 f"max_close_diff={res.get('max_close_diff')}"
                 if res.get("status") == "VALIDATED" else ""))
        results.append(res)

    validated = [r for r in results if r.get("status") == "VALIDATED"]
    summary = {
        "sessions": results,
        "n_validated": len(validated),
        "n_requested": len(SESSIONS),
        "all_opens_exact": all(r["opens_match_exactly"] for r in validated) if validated else False,
        "all_closes_within_timing": all(r["closes_match_last_trade"] for r in validated) if validated else False,
        "note": ("Expired-Options API (rollingoption) recovers fixed-strike legs for expired "
                 "contracts back to 2021-01; open marks must match bhavcopy to the paisa. "
                 "Closes are last-trade prints vs bhavcopy settlement marks (timing noise)."),
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACTS / "marks_validation_v2.json", "w") as fp:
        json.dump(summary, fp, indent=2, default=str)
    print(f"\nvalidated {len(validated)}/{len(SESSIONS)} sessions | "
          f"opens exact everywhere: {summary['all_opens_exact']}")
    print(f"written: {ARTIFACTS / 'marks_validation_v2.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
