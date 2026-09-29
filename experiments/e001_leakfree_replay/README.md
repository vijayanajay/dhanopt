# E001 — Leak-Free Daily Replay (Phase 0)

**Question:** What do the 3 strategy archetypes actually earn when the decision uses only prior-day information, all 3 are replayed every day, and lot sizes follow the real NSE era table?**

**Method:** `replay.py` — decision signal = prior-day futures open→close % (t-1), entry at day-t open, exit at day-t close, all 3 archetypes simulated independently every day, era-correct lots (75 → 50 @ 2021-07 → 25 @ 2024-04-26 → 75 @ 2024-11-20 → 65 @ 2025-12-30 per NSE FAOP47854 / FAOP67372 / FAOP70616 and core config pins), real Zerodha friction via `core.friction.zerodha`. Data: 1,415 FO bhavcopy parquet partitions (2021-01 → 2026-09). Rule (baseline, deliberately naive): t-1 ≥ +0.25% → bull spread; ≤ −0.25% → bear spread; else condor.

Self-checks: `python -m unittest experiments.e001_leakfree_replay.test_replay` (6 tests, pin the no-look-ahead semantics, spread math, and era table).

## Results (artifacts/labels_daily.csv, report.txt)

All days simulated (1 lot, era-correct):

| Archetype | n | Win rate | Avg net ₹/day | Total net ₹ | PF |
|---|---|---|---|---|---|
| Bull Call Spread | 1,408 | 33.4% | −420 | −590,841 | 0.54 |
| Bear Put Spread | 1,406 | 45.4% | −129 | −181,562 | 0.86 |
| Iron Condor | 1,326 | 52.0% | +789 | +1,045,925 | 4.06 |

Rule-selected subset (what the naive t-1 rule would have traded): n=1,386, net +₹152,346, WR 45.0% — positive only because condor days outweigh two losing directional books. (Era correction, 2026-09-30: the original run used a flat 25 lot for all pre-Nov-2024 rows — verified eras are 75/50/25/75/65 — so 2021→Apr-2024 rupees were understated 2–3×; re-run on the corrected table.)

Comparison with the old biased engine (decision from day-t close = look-ahead):

| Strategy | Old (biased) | Honest |
|---|---|---|
| Bull Call Spread | 79.5% WR, PF 12.4 | 33.4% WR, PF 0.54 |
| Bear Put Spread | 87.4% WR, PF 26.2 | 45.4% WR, PF 0.86 |
| Iron Condor | 45.9% WR, PF 7.0 | 52.0% WR, PF 4.06 |

## Verdict

**What works:**
1. The measurement pipeline itself: leak-free, era-correct, friction-real, all-archetype labels produced for ML (4,245 rows). This is the dataset e002 trains on.
2. **Iron condor survives honesty.** PF ~4.1–4.7 with 52–54% WR under the t-1 constraint. Short-vol on flat days after a non-trending yesterday is the one edge that replicates. This is the primary label for the ML models.
3. The bug-fix value of the sandbox: the test suite caught a real defect pattern (short put leg built on the wrong side of ATM would have silently emptied the bear archetype) — exactly the class of error the old untested engine shipped with.

**What does not work:**
1. **Naive daily momentum-continuation into directional spreads** — decisively negative (bull PF 0.55, bear PF 0.93). "Yesterday was up, buy calls at today's open" is not an edge after friction; if anything the bull side is anti-predictive (34% WR).
2. The old calibrated_params.json numbers (aggregate PF 22) — confirmed as pure look-ahead artifacts. Treat every EV currently feeding the live engine as invalid until regenerated from honest replay.
3. Absolute ₹ comparisons across lot eras remain approximate even with the era table (75→65 mid-sample, plus per-contract transition-day nuance flagged in `experiments/common/lots.py`). Points-based sanity checks are the cross-era fallback.

**Known ceilings (accepted for v1):**
- Open→close proxy cannot see intraday stop/target paths: condor results are optimistic (no intraday stop-out) and spread results are pessimistic (no intraday profit-taking). Directional books need 5-min data before any verdict is final.
- Nearest-expiry chain only; walls = max-OI strike; 88 days failed condor simulation (missing legs) and are excluded (`simulated=False`).
- One naive decision rule by design — separating good condor days from bad ones is exactly the job handed to the e002 ML models, not a flaw of this baseline.

**Next:** e002_regime_models — LightGBM P(win) per archetype on these labels, t-1 features, purged walk-forward, logistic + persistence baselines, SHAP. Success = a gating sim that keeps ~the same trade count while cutting the losing spread trades and keeping most condor wins.
