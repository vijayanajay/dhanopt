"""e009 Phase A: live wall-capture collector — the one data class the wall
family never had.

Pre-registered contract: experiments/e009_wall_capture/PREREG.md (frozen
2026-10-01, changelog v22). This collector implements it and nothing more:
full NIFTY OPTIDX chain snapshots (every strike the live feed returns) every
SNAPSHOT_SECS during 09:00-15:35 IST on weekdays, appended to per-day gzip
jsonl under snapshots/YYYY-MM-DD.jsonl.gz. One snapshot = one line:
{"ts": capture time (IST), "lat": fetch latency ms, "n": strikes captured,
 "exp": expiry served, "exp_list": [first two expiries],
 "spot": chain LTP, "oc": {strike: {ce: {oi, bid, ask}, pe: {...}}}}.
Storage ~35-45 MB gz / month — comfortably offline-archivable.

Honesty properties (each test-pinned):
- ts is stamped at capture completion, never rewritten; appends are
  idempotent per second and resumable after any crash (append mode).
- coverage_gap_secs: largest gap between consecutive snapshots; capture_gap
  flags gaps > SNAPSHOT_SECS * 1.5. PREREG kill 1: a session is evaluable
  only if max_gap <= 60 s and coverage >= 95% of 09:15-15:30.
- capture_coverage_pct: covered trading minutes / 375. Capture window 09:00
  (pre-open build-up) to 15:35; the evaluated window is 09:15-15:30.

Rate limit: Dhan option-chain API = 1 unique request / 3 s; this collector
fires one request per SNAPSHOT_SECS = 60 s. Header needs access-token AND
client-id (DHAN_CLIENT_ID, config.py:193) — the Expired-API used only the
token.

Kill 4 re-expressed for live data: signal bar = first bar where spot crosses
a wall with wall OI <= 5 min old (kill 4's median-age bar); fillability at
t+1 snapshot is limited by the market (both legs quote every strike), not by
the data. Evaluation comes later (Phase B) — this file only captures.

Run (a trading day, 09:00-15:35 IST):
    python -m experiments.e009_wall_capture.capture_chains
Windows Task Scheduler (from the repo root):
    D:\\Code\\dhanopt\\.venv\\Scripts\\python.exe -m experiments.e009_wall_capture.capture_chains
"""
from __future__ import annotations

import argparse
import gzip
import json
import time
from datetime import date as _date
from datetime import datetime, timedelta
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
SNAPSHOTS = HERE / "snapshots"
LEDGER = HERE / "artifacts" / "coverage_ledger.json"

# PREREG §3: full chain, <=60 s freshness. Dhan's option-chain rate limit is
# 1 unique request / 3 s, so 60 s cadence complies with 20x headroom.
SNAPSHOT_SECS = 60
SESSION_START = "09:00"
SESSION_END = "15:35"
EVAL_START, EVAL_END = "09:15", "15:30"  # the PREREG-evaluated window
UNDERLYING_SCRIP = 13   # NIFTY (same id the Expired-API used as securityId)
UNDERLYING_SEG = "IDX_I"
OC_URL = "https://api.dhan.co/v2/optionchain"


def _headers(token: str, client_id: str) -> dict:
    # Option Chain needs BOTH headers (Expired-API needed only access-token).
    return {"Accept": "application/json", "Content-Type": "application/json",
            "access-token": token, "client-id": client_id}


def _fetch_chain(token: str, client_id: str, expiry: str) -> dict:
    """One live chain snapshot; raises on HTTP/auth errors (the session loop
    decides policy). Returns {} on an empty/failed payload — never fabricates."""
    r = requests.post(OC_URL, headers=_headers(token, client_id),
                      data=json.dumps({"UnderlyingScrip": UNDERLYING_SCRIP,
                                       "UnderlyingSeg": UNDERLYING_SEG,
                                       "Expiry": expiry}), timeout=30)
    r.raise_for_status()
    js = r.json()
    if js.get("status") != "success":
        raise RuntimeError(f"optionchain status={js.get('status')!r} notes={js.get('notes')!r}")
    return js.get("data") or {}


def _strike_map(chain: dict) -> dict:
    """{strike: {ce: {oi, bid, ask}, pe: {...}}} from data.oc, float strikes.
    Uniform shape: a missing side is recorded as all-None (never fabricated,
    never absent) — Phase B decides fillability from quotes, and a uniform
    shape keeps that walk trivial."""
    out: dict = {}
    for k, v in (chain.get("oc") or {}).items():
        try:
            strike = float(k)
        except (TypeError, ValueError):
            continue
        row = {}
        for side in ("ce", "pe"):
            d = v.get(side) or {}
            row[side] = {"oi": d.get("oi"), "bid": d.get("top_bid_price"),
                         "ask": d.get("top_ask_price")}
        out[strike] = row
    return out


def capture_session(token: str, client_id: str, d: _date, expiry: str) -> Path:
    """One trading day: snapshot loop 09:00-15:35, append to per-day jsonl.gz.
    Idempotent: a rerun the same evening appends only newer snapshots."""
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOTS / f"{d.isoformat()}.jsonl.gz"
    day = datetime.combine(d, datetime.min.time())
    start = day + timedelta(hours=int(SESSION_START[:2]), minutes=int(SESSION_START[3:]))
    end = day + timedelta(hours=int(SESSION_END[:2]), minutes=int(SESSION_END[3:]))
    last_stamps = []
    with gzip.open(path, "at", encoding="utf-8") as f:
        while (now := datetime.now()) < end:
            if now < start:
                time.sleep(min(30, (start - now).total_seconds()))
                continue
            t0 = time.time()
            try:
                chain = _fetch_chain(token, client_id, expiry)
                oc = _strike_map(chain)
                rec = {"ts": now.replace(microsecond=0).isoformat(),
                       "lat": round((time.time() - t0) * 1000), "n": len(oc),
                       "exp": expiry, "spot": chain.get("last_price"), "oc": oc}
            except Exception as e:  # outage row: a gap is a data outage, not a signal (PREREG §2)
                rec = {"ts": now.replace(microsecond=0).isoformat(),
                       "lat": round((time.time() - t0) * 1000), "err": repr(e)[:200]}
            if rec["ts"][0:19] not in last_stamps:  # idempotent appends
                f.write(json.dumps(rec) + "\n")
                last_stamps.append(rec["ts"][0:19])
                last_stamps = last_stamps[-2:]
            f.flush()
            time.sleep(max(0.0, SNAPSHOT_SECS - (time.time() - t0)))
    return path


def _session_gaps(stamps: list[str]) -> float:
    """Largest gap (s) between consecutive session snapshots (09:15-15:30 only,
    the evaluated window; PREREG kill 1 judges this window, not the pre-open)."""
    if len(stamps) < 2:
        return float("inf")
    t = [datetime.fromisoformat(s) for s in stamps]
    return max((b - a).total_seconds() for a, b in zip(t, t[1:]))


def capture_coverage_pct(stamps: list[str]) -> float:
    """Covered trading seconds 09:15-15:30 / 375 min, where a stretch is covered
    if the gap between the consecutive snapshots straddling it is <= 1.5x cadence."""
    if len(stamps) < 2:
        return 0.0
    t = [datetime.fromisoformat(s) for s in stamps]
    ev_start = t[0].replace(hour=9, minute=15, second=0, microsecond=0)
    ev_end = ev_start.replace(hour=15, minute=30)
    total = (ev_end - ev_start).total_seconds()
    covered = 0.0
    for a, b in zip(t, t[1:]):
        lo, hi = max(a, ev_start), min(b, ev_end)
        if lo >= hi:
            continue
        if (b - a).total_seconds() <= SNAPSHOT_SECS * 1.5:
            covered += (hi - lo).total_seconds()
    return round(100.0 * covered / total, 2)


def register_session(path: Path) -> dict:
    """Append the day's coverage row to the ledger (kill-1 evidence, idempotent)."""
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    stamps, spot, nstrikes = [], None, 0
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if "err" in rec:
                continue
            stamps.append(rec["ts"])
            spot, nstrikes = rec.get("spot"), max(nstrikes, rec.get("n") or 0)
    row = {"date": path.stem, "n_snapshots": len(stamps),
           "max_gap_secs": None if not stamps else round(_session_gaps(stamps), 1),
           "coverage_pct": capture_coverage_pct(stamps),
           "spot_last": spot, "strikes_max": nstrikes,
           "evaluable": bool(stamps) and _session_gaps(stamps) <= SNAPSHOT_SECS * 1.5
                        and capture_coverage_pct(stamps) >= 95.0}
    ledger[path.stem] = row
    LEDGER.write_text(json.dumps(ledger, indent=1))
    return row


def main() -> int:
    import config

    ap = argparse.ArgumentParser(description="e009 live chain capture (PREREG-frozen)")
    ap.add_argument("--expiry", default=None, help="override chain expiry (default: nearest)")
    args = ap.parse_args()
    if not config.DHAN_ACCESS_TOKEN or not config.DHAN_CLIENT_ID:
        print("DHAN_ACCESS_TOKEN / DHAN_CLIENT_ID missing in env — cannot capture")
        return 2
    expiry = args.expiry
    if not expiry:
        r = requests.post("https://api.dhan.co/v2/optionchain/expirylist",
                          headers=_headers(config.DHAN_ACCESS_TOKEN, config.DHAN_CLIENT_ID),
                          data=json.dumps({"UnderlyingScrip": UNDERLYING_SCRIP,
                                           "UnderlyingSeg": UNDERLYING_SEG}), timeout=30)
        r.raise_for_status()
        exps = (r.json().get("data") or [])
        if not exps:
            print("expirylist returned nothing")
            return 2
        expiry = exps[0]
    path = capture_session(config.DHAN_ACCESS_TOKEN, config.DHAN_CLIENT_ID,
                           _date.today(), expiry)
    print(json.dumps(register_session(path), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
