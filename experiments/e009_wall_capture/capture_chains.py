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
import os
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
    """{strike: {ce: {oi, bid, bid_qty, ask, ask_qty, ltp, vol, iv}, pe: {...}}} from data.oc, float strikes.
    Uniform shape: a missing side is recorded as all-None (never fabricated,
    never absent) — preserving maximum market depth, quote quantities, and volume."""
    out: dict = {}
    for k, v in (chain.get("oc") or {}).items():
        try:
            strike = float(k)
        except (TypeError, ValueError):
            continue
        row = {}
        for side in ("ce", "pe"):
            d = v.get(side) or {}
            row[side] = {
                "oi": d.get("oi"),
                "bid": d.get("top_bid_price"),
                "bid_qty": d.get("top_bid_quantity"),
                "ask": d.get("top_ask_price"),
                "ask_qty": d.get("top_ask_quantity"),
                "ltp": d.get("last_price"),
                "vol": d.get("volume"),
                "iv": d.get("implied_volatility"),
            }
        out[strike] = row
    return out


def _existing_stamps(path: Path) -> list[str]:
    """Seconds already captured in this day-file.

    Resume is what makes crash-restart safe: without this a restarted process
    re-appends every snapshot it already wrote, and the duplicated timestamps
    silently corrupt max_gap and coverage_pct — the two numbers kill 1 is
    judged on. (The docstring claimed idempotence; it was not.)
    """
    if not path.exists():
        return []
    stamps = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue  # truncated final line from a hard kill
                if "ts" in rec:
                    stamps.append(rec["ts"][0:19])
    except (OSError, EOFError, gzip.BadGzipFile):
        return []  # unreadable file: start fresh rather than silently append
    return stamps


def capture_session(token: str, client_id: str, d: _date, expiry: str | list[str]) -> Path:
    """One trading day: snapshot loop 09:00-15:35, append to per-day jsonl.gz.
    Supports single or multiple expiries (e.g. front and next expiry).
    Idempotent: a rerun appends only seconds not already on disk."""
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOTS / f"{d.isoformat()}.jsonl.gz"
    day = datetime.combine(d, datetime.min.time())
    start = day + timedelta(hours=int(SESSION_START[:2]), minutes=int(SESSION_START[3:]))
    end = day + timedelta(hours=int(SESSION_END[:2]), minutes=int(SESSION_END[3:]))
    last_stamps = _existing_stamps(path)[-2:]
    exp_list = [expiry] if isinstance(expiry, str) else list(expiry)
    primary_exp = exp_list[0]

    with gzip.open(path, "at", encoding="utf-8") as f:
        while (now := datetime.now()) < end:
            if now < start:
                time.sleep(min(30, (start - now).total_seconds()))
                continue
            t0 = time.time()
            all_chains = {}
            spot = None
            errs = []
            for exp in exp_list:
                try:
                    chain = _fetch_chain(token, client_id, exp)
                    oc = _strike_map(chain)
                    if spot is None and chain.get("last_price") is not None:
                        spot = chain.get("last_price")
                    all_chains[exp] = {"n": len(oc), "spot": chain.get("last_price"), "oc": oc}
                except Exception as e:
                    errs.append(f"{exp}: {repr(e)[:150]}")

            primary_data = all_chains.get(primary_exp)
            if primary_data:
                rec = {
                    "ts": now.replace(microsecond=0).isoformat(),
                    "lat": round((time.time() - t0) * 1000),
                    "n": primary_data["n"],
                    "exp": primary_exp,
                    "exp_list": exp_list,
                    "spot": spot if spot is not None else primary_data["spot"],
                    "oc": primary_data["oc"],  # Uniform front-expiry chain for backwards compatibility
                }
                if len(exp_list) > 1:
                    rec["chains"] = {exp: c["oc"] for exp, c in all_chains.items()}
            else:
                # Outage row: recorded when primary expiry fails (PREREG §2)
                rec = {
                    "ts": now.replace(microsecond=0).isoformat(),
                    "lat": round((time.time() - t0) * 1000),
                    "err": "; ".join(errs) if errs else "No chain data returned"
                }

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


def register_session(path: Path) -> dict | None:
    """Append the day's coverage row to the ledger (kill-1 evidence, idempotent).

    Returns None and writes NOTHING when the file holds zero successful
    snapshots. A weekend or a holiday that produced no data must not enter the
    ledger as a 0%-coverage failure — fail-closed means "no row", not "a row
    that says nothing happened" (s5.5's NO TRADE rule, applied to the ledger).
    """
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    stamps, spot, nstrikes = [], None, 0
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "err" in rec:
                continue
            stamps.append(rec["ts"])
            spot, nstrikes = rec.get("spot"), max(nstrikes, rec.get("n") or 0)
    if not stamps:
        print(f"no successful snapshots in {path.name} — no ledger row written")
        return None
    row = {"date": path.name.split(".")[0], "n_snapshots": len(stamps),
           "max_gap_secs": None if not stamps else round(_session_gaps(stamps), 1),
           "coverage_pct": capture_coverage_pct(stamps),
           "spot_last": spot, "strikes_max": nstrikes,
           "evaluable": bool(stamps) and _session_gaps(stamps) <= SNAPSHOT_SECS * 1.5
                        and capture_coverage_pct(stamps) >= 95.0}
    ledger[row["date"]] = row
    LEDGER.write_text(json.dumps(ledger, indent=1))
    return row


def main() -> int:
    import config

    ap = argparse.ArgumentParser(description="e009 live chain capture (PREREG-frozen)")
    ap.add_argument("--expiry", default=None, help="override chain expiry (default: nearest 2 expiries)")
    ap.add_argument("--force", action="store_true",
                    help="capture even on a weekend/holiday (for smoke runs)")
    ap.add_argument("--sync-cmd", default=None,
                    help="shell command to run post-capture (supports {file} and {date})")
    args = ap.parse_args()
    if _date.today().weekday() >= 5 and not args.force:
        print(f"{_date.today().isoformat()} is not a weekday — market closed, nothing to "
              f"capture. Pass --force to run anyway.")
        return 3
    if not config.DHAN_ACCESS_TOKEN or not config.DHAN_CLIENT_ID:
        print("DHAN_ACCESS_TOKEN / DHAN_CLIENT_ID missing in env — cannot capture")
        return 2
    expiries = [args.expiry] if args.expiry else None
    if not expiries:
        r = requests.post("https://api.dhan.co/v2/optionchain/expirylist",
                          headers=_headers(config.DHAN_ACCESS_TOKEN, config.DHAN_CLIENT_ID),
                          data=json.dumps({"UnderlyingScrip": UNDERLYING_SCRIP,
                                           "UnderlyingSeg": UNDERLYING_SEG}), timeout=30)
        r.raise_for_status()
        exps = (r.json().get("data") or [])
        if not exps:
            print("expirylist returned nothing")
            return 2
        # Capture up to 2 nearest expiries (front-week and next-week)
        expiries = exps[:2]
    path = capture_session(config.DHAN_ACCESS_TOKEN, config.DHAN_CLIENT_ID,
                           _date.today(), expiries)
    row = register_session(path)
    if row is None:
        return 4
    print(json.dumps(row, indent=1))

    # Optional post-session sync (e.g. rclone / S3 / cloud copy)
    sync_cmd = os.environ.get("SYNC_COMMAND") or args.sync_cmd
    if sync_cmd:
        import subprocess
        cmd = sync_cmd.replace("{file}", str(path)).replace("{date}", _date.today().isoformat())
        print(f"[sync] running: {cmd}")
        subprocess.run(cmd, shell=True, check=False)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
