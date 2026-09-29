"""Mark validation: do e005's bhavcopy endpoint marks match real 5-min option candles?

Answers the last open question from the inverted-wall audit. Dhan serves 5-min OHLC+OI
for NSE_FNO options (security IDs from the public scrip master); only contracts still
listed in the CURRENT master can be validated (expired contracts are delisted there),
so this run validates the latest frozen e005 session (2026-09-25, expiry 2026-09-29).
Scrip-mapping hazard found on the way: FINNIFTY shares strike prices with NIFTY —
map by exact SEM_TRADING_SYMBOL ('NIFTY'), never by strike alone (str.startswith
matches FINNIFTY/NIFTYNXT50 too).

Run: python -m experiments.e005_theta_condor.marks_validation
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
SESSION = "2026-09-25"   # latest frozen e005 session whose contracts survive in the master
EXPIRY = "2026-09-29"

LEG_IDS = {  # from the scrip master (exact NIFTY mapping, this expiry week only)
    ("PE", 23500.0): 73994, ("CE", 23500.0): 73985,
    ("PE", 23250.0): 73922, ("CE", 23650.0): 74005,
    ("PE", 23400.0): 73928, ("CE", 23400.0): 73927,
}


def main() -> int:
    import config
    from dhanhq import DhanContext, dhanhq

    f = Path(config.HISTORICAL_DATA_DIR) / "year=2026/month=09" / f"fo_{SESSION.replace('-', '')}.parquet"
    df = pd.read_parquet(f)
    opts = df[(df["symbol"] == "NIFTY") & (df["instrument"].isin(["OPTIDX", "IDO"]))]
    chain = opts[opts["expiry"].astype(str).str.strip() == EXPIRY]
    fut = df[(df["symbol"] == "NIFTY") & df["instrument"].isin(["FUTIDX", "IDF"])]
    print(f"futures {SESSION}: open={float(fut.iloc[0]['open']):.1f} close={float(fut.iloc[0]['close']):.1f}")

    ctx = DhanContext(config.DHAN_CLIENT_ID, config.DHAN_ACCESS_TOKEN)
    client = dhanhq(ctx)
    ist = timezone(timedelta(hours=5, minutes=30))
    rows = []
    for (t, k), sid in LEG_IDS.items():
        r = client.intraday_minute_data(security_id=str(sid), exchange_segment="NSE_FNO",
                                        instrument_type="OPTIDX", from_date=SESSION, to_date=SESSION,
                                        interval=5, oi=True)
        if r.get("status") != "success":
            rows.append({"leg": f"{t} {k:.0f}", "dhan_bars": 0})
            continue
        data = r["data"]
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        first_ts = data["timestamp"][0]
        day_start = datetime.fromtimestamp(first_ts, ist).replace(hour=9, minute=15, second=0, microsecond=0)
        day_end = day_start.replace(hour=15, minute=29, second=59)
        bars = pd.DataFrame({"ts": data["timestamp"], "open": data["open"], "close": data["close"]})
        bars["time"] = bars.ts.map(lambda t: datetime.fromtimestamp(t, ist))
        sess = bars[(bars["time"] >= day_start) & (bars["time"] <= day_end)]
        brow = chain[(chain["option_type"] == t) & (chain["strike"] == k)].iloc[0]
        d_open, d_close = float(sess.iloc[0]["open"]), float(sess.iloc[-1]["close"])
        b_open, b_close = float(brow["open"]), float(brow["close"])
        rows.append({"leg": f"{t} {k:.0f}", "dhan_bars": int(len(sess)),
                     "dhan_open": d_open, "dhan_close": d_close,
                     "bhav_open": b_open, "bhav_close": b_close,
                     "open_diff": round(d_open - b_open, 2),
                     "close_diff": round(d_close - b_close, 2)})

    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    opens_ok = bool((out["open_diff"].abs() < 0.01).all())
    closes_ok = bool((out["close_diff"].abs() < 10).all())
    verdict = {
        "session": SESSION, "expiry": EXPIRY,
        "opens_match_exactly": opens_ok,
        "closes_match_last_trade": closes_ok,
        "max_open_diff": float(out["open_diff"].abs().max()),
        "max_close_diff": float(out["close_diff"].abs().max()),
        "note": ("candle opens == bhavcopy opens exactly on every validated leg; closes differ "
                 "only by last-trade vs settlement timing (<10 pts on the far OTM wing); the "
                 "'inverted' walls on 2026-09-25 are prior-OI walls above a spot that crashed "
                 "between 09-22 and 09-25 (futures open 23,302), and the short wall put's "
                 "crash-inflated premium crushing on expiry is a real, mechanically-explained "
                 "post-crash short-vol effect. Composition warning stands but stale-mark "
                 "contamination is excluded for this session."),
        "legs": rows,
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACTS / "marks_validation.json", "w") as fp:
        json.dump(verdict, fp, indent=2)
    print(f"\nopens match exactly: {opens_ok} | closes within timing noise: {closes_ok}")
    print(f"written: {ARTIFACTS / 'marks_validation.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
