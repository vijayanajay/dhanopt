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
not a signal (PREREG §2). Capture is **resumable**: a restarted process reads the
seconds already on disk (`_existing_stamps`) and appends only newer ones.
Without that, a restart re-appends every snapshot it already wrote and the
duplicated timestamps silently corrupt `max_gap_secs` and `coverage_pct` — the
two numbers kill 1 is judged on. A truncated final line from a hard kill is
tolerated rather than crashing the restart. `ts` is stamped at capture and never
rewritten — Phase B's kill 4 (median wall-OI age ≤ 5 min) is judged on it.

## Running it (starting the clock)

Prereqs: `DHAN_ACCESS_TOKEN` **and** `DHAN_CLIENT_ID` in the environment (the
option-chain endpoint needs both; the Expired-API needed only the token). Both
are set on this machine and were verified live against `/v2/optionchain` on
2026-10-03 (HTTP 200, 244 strikes, two-sided quotes, front expiry resolving
correctly).

**Use the watchdog, not the collector directly.** The capture loop already
survives *request* failures (it writes an outage row and carries on, PREREG §2);
what it cannot survive is the *process* dying. One death at 11:00 truncates a
6.6-hour session below kill-1's 95% coverage bar and the whole day is lost.

```
.venv\Scripts\python.exe -m experiments.e009_wall_capture.watchdog
```

`run_capture.cmd` is the Windows launcher. Its `cd /d D:\Code\dhanopt` is
load-bearing, not decoration: Task Scheduler starts an action in
`C:\Windows\System32`, and `python -m experiments...` only resolves from the repo
root. It runs the watchdog, and appends to `capture.log`.

**Registered 2026-10-03.** `schtasks` task `e009 capture`, weekly MON–FRI 08:55
IST, action `run_capture.cmd`. Verified: `Next Run Time 10/5/2026 8:55:00 AM`,
Status `Ready`. The machine must be on and awake at 08:55 IST — the task runs
only while a user is logged in, and defaults are otherwise unchanged (the
process exits itself at 15:35).

Non-weekdays exit 3 with a message and write nothing. A day that produces zero
successful snapshots writes **no ledger row** — fail-closed means "no row", not
"a row recording 0% coverage", which would read as a failed session rather than
the absence of one.

Notes: the machine must be on and awake at 08:55 IST; the task runs ~6.7 h, so
leave `schtasks` defaults (it kills nothing mid-day; the process exits itself).
Per PREREG §4 the clock runs ≥ 6 months before Phase B reads kill 2/3 — kill 1
and kill 4 become checkable within the first weeks from the ledger.

Self-checks: `test_capture.py` (14 tests — strike-map shape/None-safety, the
coverage/gap AND-semantics of kill 1, append/outage-row semantics, and the two
rules crash-restart depends on: resume must not duplicate seconds, and a
session with no successful snapshots must leave no ledger row; no network).

## Phase B (not built, pre-contracted)

Evaluation reuses e008's signal walk (`_wall_of`/`_spread_at` carry over; walls
from snapshot OI, fills from t+1 snapshot bids/asks). Its first commit must add
the leak-registry row (`day-t` / `live=True` + t+1-fill rule) — the registry's
tail comment already spells this out. Kill bars: PREREG §4, unchanged.
