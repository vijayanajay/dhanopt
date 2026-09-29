# E004 — Intraday 5-Minute Path Replay (SL / Target / EOD)

**Question:** What do the 3 archetypes earn when exits follow the documented intraday rules (35% debit SL / +70% for spreads; 1.4× credit SL / +50% for condor) instead of e001's open→close proxy?

**Status: simulator complete and validated; full run blocked on data backfill.**

- Needs `data/intraday/` partitions: `python download_intraday.py --start 2026-09-01 --end 2026-09-26` (DhanHQ 5-min history has limited depth — check how far back it goes before planning anything long-horizon).
- Then: `python -m experiments.e004_intraday_replay.replay_intraday` → `artifacts/intraday_replay.csv`.

## Verdict

**What works (validated on deterministic synthetic paths, 7 tests green):**
1. Path simulator prices legs with the same closed-form BS approximation as the live engine (reused from `core.feeds.dhan`, not copied), walks the 5-min frame bar by bar, and fires STOP / TARGET / EOD with the conservative rule (SL wins inside one bar).
2. Exit semantics verified: clean +350pt trend → bull TARGET; rally-then-collapse at 3 DTE with deep floor → bull STOP (gross ≤ 0); flat day inside wide walls → condor EOD; inverted walls → condor skipped (`NOSIM`).
3. No-look-ahead construction: walls, IV proxy (Brenner-Subrahmanyam from prior-day ATM straddle), and DTE all come from the *prior* day's bhavcopy partition; only the entry-time ATM strike uses the day's open (observable at entry).

**What does not work / not yet known:**
1. **No verdict on real PnL yet** — zero intraday partitions on disk at time of writing. The e001 open→close numbers remain the only honest daily baseline until this runs.
2. **DTE sensitivity discovered during testing:** at 1 DTE the BS re-price is near-intrinsic, so a +120pt morning rally reaches a debit spread's +70% target almost immediately — the fixed-IV model *overstates* late-week debit-spread profitability (no theta-decay path, no vol crush). Direction of bias per archetype: condor optimistic (no intraday SL-out despite the modeled rule), debit spreads PnL-timing optimistic but win/loss direction roughly right, credit spreads optimistic via theta (BS without theta drift).
3. Friction uses real entry prices but modeled exits (last-path MTM), same as e001's convention.

**Handoff:** when partitions exist, run and update this Verdict with the three real rows (n / WR / PF / exit mix) next to e001's open→close rows; that comparison is the actual deliverable — it decides whether e002's gating numbers survive intraday exits.
