# E007 — Opening-OI Walls (Gate 0: can the breach book live without the day-t look-ahead?)

**Question:** the frozen breach book (+₹940,697, 249 trades) reads walls from day-t **EOD** OI — 6 hours future-relative to its 09:15 entry (e005 Add. 8). Rebuilt on **opening-OI walls** — the max-OI strikes of the 09:15 chain, the only wall source observable at the open — does the book survive handoff §7's gate-0 bars: **PF ≥ 5, WR ≥ 85%, net ≥ 40% of frozen (+₹376,279), on ≥ 80% of the 249 days**?

**Method:** [fetch_open_oi.py](fetch_open_oi.py) pulls each breach day's opening chain from the Dhan Expired-Options API (per-bar `oi` is timestamped intraday OI — probed: PE 22850 on 2026-09-25 goes 3.43M @09:15 → 5.98M @12:00 — so the 09:15 bar's OI is true opening OI; ATM±10 × both sides, 20 req/session, checkpointed). [build_book.py](build_book.py) then re-runs the frozen book with walls swapped: same day-t real leg opens/exits (marks sweep-validated), same 2-leg pair, 1.4× SL / 100% target on the 5-min path, era lots. Days the opening gate stands down on contribute 0 — that is the live book's real behavior, not a data gap. Self-checks: `test_e007.py` (wall = argmax *opening* OI, not closest-to-spot; gate stands down on a frozen-breach day).

Run: `python -m experiments.e007_open_oi.fetch_open_oi` then `python -m experiments.e007_open_oi.build_book` → `artifacts/gate0.json`, `book_opening_walls.csv`.

## Verdict

**GATE 0: FAIL — the breach book's edge is the day-t wall update itself, and no pre-open-observable wall source replicates it.**

All 249 sessions fetched (100% coverage — no data excuse). The opening-OI book: **4 trades in 249 days** (244 stand-downs), net **−₹309**, WR 50.0%, PF 0.96, side agreement with the frozen book **1.2%**. Against the pre-registered bars: PF 0.96 < 5, WR 0.50 < 0.85, net −₹309 < ₹376,279 — fails every economic bar.

**Why this is the definitive answer, not a data artifact:**

1. **Opening walls are genuinely different walls.** They match t-1 EOD walls on only 63/249 breach days (74% differ) — OI migrates overnight, so this gate is not a stale copy of anything. It is the max-OI structure as a live trader could actually know it at 09:15.
2. **The frozen book's breach test almost never fires on the opening structure.** 244/249 days the opening walls are valid (spot between them) — the "gap over the wall" exists only against walls that moved INTO the way during day t. The signal is contemporaneous with the wall update, i.e. 6 h future-relative to the entry it is supposed to precede.
3. **Consistency with the independent t-1 harness** (e005 Add. 8: 57 trades, −₹27.5k): every observable wall source — t-1 EOD, opening OI — kills the book; only day-t EOD OI produces it. The +₹940,697 is a measurement identity, not an edge.

**Per handoff §7's own terms: the +₹940,697 is declared a look-ahead artifact; the breach-only book returns to research; §7's holdout protocol expires — its gate 0 was the entry condition and it failed.** What survives untouched: the marks validation (prices are real — sweep-validated to the paisa on covered legs), e005's exit/target comparisons as internal-consistency results, the friction/slippage machinery, and the shadow-runner instrumentation. What does not survive: the production handoff's headline, e006's compounded projection (inherits the signal), and every ML verdict resting on condor labels (e002 Add. 7: +₹793,906 → −₹140,520 on t-1 labels). The one live observation worth carrying forward: **OI walls move early and informatively during the session** — an intraday wall-flip response (reacting to real-time OI shifts after 09:15) is a genuinely different, testable strategy, and is the recommended next experiment. It is NOT this book and starts from zero.

Run: `python -m experiments.e007_open_oi.fetch_open_oi` (checkpointed, ~2.5 h) then `python -m experiments.e007_open_oi.build_book` → `artifacts/gate0.json`, `book_opening_walls.csv`.
