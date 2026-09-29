# E004 — Intraday 5-Minute Path Replay (SL / Target / EOD)

**Question:** What do the 3 archetypes earn when exits follow the documented intraday rules (35% debit SL / +70% for spreads; 1.4× credit SL / +50% for condor) instead of e001's open→close proxy?

**Status: simulator complete and validated; full run blocked on data backfill.**

- Needs `data/intraday/` partitions. **Depth probe (2026-09-29): Dhan serves 5-min NIFTY back to at least 2021-01-04** (75 bars/day verified at 2021/2022/2023/2024 probes), so a full-window backfill matching e001 (~1,415 trading days) is feasible. Backfill DONE (1,409/1,415 e001 days; the 6 gaps are real NSE holidays with no 5-min data). Run: `python -m experiments.e004_intraday_replay.replay_intraday` → `artifacts/intraday_replay.csv` (chunk-checkpointed; resume-safe).
- First-run integration bug found and fixed (2026-09-29): `_load_prior_partition` parsed bhavcopy stems with `parse_date` (ISO/dash formats only), so every file failed to parse and all days were silently skipped — now parses the real `%Y%m%d` stem format with an indexed cache. e001/e002 were never affected (different loader).
- Then: `python -m experiments.e004_intraday_replay.replay_intraday` → `artifacts/intraday_replay.csv`.

## Verdict

**Real run complete (2026-09-29): 1,410 sessions, 2021-01 → 2026-09, full window.** Per-archetype vs e001 (open→close proxy):

| Archetype | n | WR | Net ₹ | Avg/day | Exits | Max DD ₹ | e001 WR / Net |
|---|---|---|---:|---:|---|---:|---|
| Bull Call Spread | 1,410 | 37.2% | −313,851 | −223 | EOD 637 / STOP 574 / TGT 199 | 314,588 | 32.4% / −473,988 |
| Bear Put Spread | 1,410 | 42.6% | −146,502 | −104 | EOD 656 / STOP 453 / TGT 301 | 160,690 | 44.3% / −179,152 |
| Iron Condor | 1,005 | 4.1% | −547,744 | −545 | EOD 614 / STOP 251 / TGT 140 | 547,810 | 47.5% / +731,746 |

Rule-selected subset: n=1,265, net −₹385,273, WR 29.8% (bull −114k / bear −91k / condor −181k).

**What works (real, trustworthy):**
1. **The spread verdict is now confirmed by two independent pricings.** Path exits barely move the bear book (−179k → −147k) and *improve* the bull book (−474k → −314k — the 35% debit SL caps 574 tail days that open→close had to eat). Both books stay decisively net-negative. e002's recommendation to retire/redistribute away from directional spreads is robust.
2. Simulator validated on real data end-to-end: signals match e001 day-by-day, exit mix is sane (bull stops 41% of days ≈ its 32–37% loss rate), friction real.

**What does not work — the condor column is a pricing artifact, not a kill:**
1. Condor −₹548k at 4.1% WR is **structurally impossible under the entry/exit rules**: even the EOD-only subset (no SL/target interference, same 09:15→15:25 endpoints as e001) shows −₹328k at 3.2% WR on days where e001 earned +₹313k at 46.8% — correlation between the two pricings is **−0.25**. Fixed-IV BS repricing removes the intraday theta decay / premium crush that IS the condor's income; the model charges the short legs full gamma-time value all day and never credits the decay.
2. The expiry-day effect e001 found (+₹2,028/day Thu era, +₹5,588/day Tue era) vanishes under fixed-IV (Thu expiry days −₹555/day, Tue expiry days −₹1,068/day) — same mechanism, same artifact.
3. **Condor verdict under path exits: resolved by e005** (`experiments/e005_theta_condor/`) — with endpoint-anchored theta-aware pricing the condor edge survives intraday exits (+₹286k as documented, +₹757k without the +50% profit cap). e004's collapse is fully attributed to fixed-IV pricing.

**Ceilings (now measured, not theoretical):** the `ponytail` fixed-IV note is quantified above — direction of bias is *catastrophic* for credit structures, mild-favorable for debit spreads (SL cap). One usable real number even so: the 1.4× credit SL fired on 25% of condor days — a live-sizing risk input that open→close could never produce.

**Handoff:** done — e005 settled the condor; see `experiments/e005_theta_condor/README.md` and the updated `collated_results.md`.
