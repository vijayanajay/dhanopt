# E008 — Intraday Wall-Flip Response (the surviving lead, tested against pre-registered kill criteria)

**Question (from the scope in `experiment.md`):** walls move early and informatively *during* the session (74% of breach days: opening walls ≠ t-1 EOD walls — the one new fact the leak audit produced). Can a strategy that reacts to wall flips **as they happen** — fresh-wall cross at bar t, fill at bar t+1's open (the hard rule: no same-bar fills) — be a real book?

**Method:** [fetch_walls.py](fetch_walls.py) pulls per-5-min chains (OI + quotes) for all **576 dte ≤ 1 sessions** (the scope's "~946" estimate corrected; ~6 h, deterministic shuffle so partial sweeps are representative, one JSON per session). [build_signal.py](build_signal.py) walks each session: walls = max-OI per strike with carry-forward (each strike's freshest observation ≤ t), flip = first bar where spot crosses a fresh wall, fill at t+1 open with both leg quotes observable within **5 minutes** (still zero future information); flips on the session's last bar have no t+1 and count unfillable (the hard rule, no carry to t+1). Same frozen exits (1.4× SL / 100% target / EOD) on the first-order path sim. Kill criteria exactly as pre-registered in the scope.

Run: `python -m experiments.e008_wall_flip.fetch_walls` then `python -m experiments.e008_wall_flip.build_signal` → `artifacts/flip_signal.json`, `flip_trades.csv`. Self-checks: `test_e008.py` (carry-forward walls, t+1 fill, unfillable-flip counting).

## Verdict — FINAL (all 576 dte ≤ 1 sessions, full sweep): **FAIL on all three kill criteria**

| Kill criterion | Bar | Observed | Pass? |
|---|---|---:|---|
| 1. Capacity | ≥ 15 tradeable flips/yr | 638 flips → 111.9/yr (the signal exists) but **certified (fresh OI + fillable legs) 15 events → 1.4/yr** | ❌ |
| 2. Edge | PF ≥ 1.5 (n ≥ 10) | PF 2.06 on **n = 8** — unjudgeable by the bar's own terms (net +₹4,737 over 5.7 y, 7 EOD / 1 TARGET) | ❌ |
| 3. Composition | ≥ 50% of flips fillable at t+1 | **15 / 638 = 2.4% fillable** | ❌ **decisive** |

**The mechanism — the scope's pre-registered nightmare, confirmed at scale:** the rolling API serves each strike only *sporadically* (only while inside ATM±10 and sampled by overlapping offset responses). Median wall-OI age at the decision bar: **75 min** (p75: 140, p90: 220 — the 28-session sample's 42.5 min was luck); only 41 of 638 flips saw wall OI ≤ 5 min old, and in 623 of 638 the spread legs' quotes were unobservable within the 5-minute fill window. The flip is detectable only *after* the data needed to trade it has gone stale — a signal whose observability lags its occurrence is not a live signal; it is the day-t convention again, wearing per-bar clothes.

**Standing:** e008 is dead by its own pre-registered bars, and with it the wall family is exhausted on every observable data class: day-t EOD walls (the leak, +₹940k frozen), t-1 bhavcopy walls (−₹688,922 condor / −₹27.5k breach gate), opening-OI walls (4 trades / −₹309), intraday fresh flips (2.4% fillable). What dies is the *data class*, not the hypothesis: flips exist at 111.9/yr and walls move early — a future attempt needs live chain snapshots with per-minute freshness, i.e. different infrastructure, not a different backtest.

**Leak-registry declaration:** the signal itself is information-legitimate (bars ≤ t, t+1 fills — the family's first); it fails on *observability*, not on look-ahead. Registered `info: day-t / live: False` with this note.

## Data status — DOWNLOAD COMPLETE, no further fetching needed

The 576-session sweep finished 2026-10-01 (fetch.log ends `576/576 sessions on disk`). Persistence:

- Raw per-session JSONs: `artifacts/walls/<date>.json` (102 MB). The fetcher (`fetch_walls.py`) is **resume-safe by construction** — it lists files already on disk and fetches only the rest, so an interrupted run can always be relaunched with the same command and loses nothing but time.
- Compressed snapshot: `artifacts/walls_576.tar.gz` (13 MB, verified to contain all 576 files). Restore with `tar -xzf artifacts/walls_576.tar.gz -C artifacts` if the raw directory is ever deleted.
- The verdict is **re-derivable offline** from these files plus the existing 5-min candle store (`python -m experiments.e008_wall_flip.build_signal`) — no Dhan API access required. Nothing about e008 depends on fetching again.
