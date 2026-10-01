# E009 — Live Wall-Capture Collector (Phase A; the 6-month clock)

**Contract first:** [PREREG.md](PREREG.md) — frozen 2026-10-01 (changelog v22)
*before any code existed*, kill criteria included. Verdict there: **DORMANT —
do not build** on a 0-for-4 family with a n=8 best case, unless the 6-month
observation clock is worth starting. This collector starts that clock. It
captures; it does not signal, does not trade, produces no PnL. Phase B (the
flip evaluation on live data) is a separate, later build that must register
itself in [../common/leak_registry.py](../common/leak_registry.py) first.

## What it does

One snapshot of the **full live NIFTY OPTIDX chain** every 60 s (09:00–15:35 IST,
weekdays) via Dhan's `POST /v2/optionchain` (rate limit 1 req / 3 s — 20× headroom
at our cadence). Each strike keeps exactly what the PREREG needs: `oi`,
`top_bid_price`, `top_ask_price` (uniform shape, missing side = all-None, never
fabricated). Appends to `snapshots/YYYY-MM-DD.jsonl.gz` (~35–45 MB gz/month),
plus one row per day in `artifacts/coverage_ledger.json`:

- `coverage_pct` — covered seconds of 09:15–15:30 where the straddling gap
  ≤ 90 s (kill-1 bar A: ≥ 95%);
- `max_gap_secs` — largest gap in the evaluated window (kill-1 bar B: ≤ 90 s;
  kill 1 is the AND of both bars — a 7-min outage passes coverage but fails this);
- `evaluable` — the kill-1 verdict for the session, computed at capture time.

Outages are recorded as `{"ts":..., "err":...}` rows: a gap is a data outage,
not a signal (PREREG §2). Capture is resumable and idempotent (append-only jsonl,
one snapshot per second). `ts` is stamped at capture and never rewritten —
Phase B's kill 4 (median wall-OI age ≤ 5 min) is judged on it.

## Running it (starting the clock)

Prereqs: `DHAN_ACCESS_TOKEN` **and** `DHAN_CLIENT_ID` in the environment (the
option-chain endpoint needs both; the Expired-API needed only the token). Smoke
test the credentials any evening (market closed → the loop exits immediately):

```
.venv\Scripts\python.exe -m experiments.e009_wall_capture.capture_chains
```

Schedule on trading days (Windows, from the repo root — one process, self-terminating
at 15:35 IST):

```
schtasks /Create /TN "e009 capture" /SC WEEKLY /D MON,TUE,WED,THU,FRI ^
  /ST 08:55 /TR "D:\Code\dhanopt\.venv\Scripts\python.exe -m experiments.e009_wall_capture.capture_chains >> D:\Code\dhanopt\experiments\e009_wall_capture\capture.log 2>&1"
```

Notes: the machine must be on and awake at 08:55 IST; the task runs ~6.7 h, so
leave `schtasks` defaults (it kills nothing mid-day; the process exits itself).
Per PREREG §4 the clock runs ≥ 6 months before Phase B reads kill 2/3 — kill 1
and kill 4 become checkable within the first weeks from the ledger.

Self-checks: `test_capture.py` (8 tests — strike-map shape/None-safety, the
coverage/gap AND-semantics of kill 1, append/outage-row semantics; no network).

## Phase B (not built, pre-contracted)

Evaluation reuses e008's signal walk (`_wall_of`/`_spread_at` carry over; walls
from snapshot OI, fills from t+1 snapshot bids/asks). Its first commit must add
the leak-registry row (`day-t` / `live=True` + t+1-fill rule) — the registry's
tail comment already spells this out. Kill bars: PREREG §4, unchanged.
