# E027 — Realized Slippage on the Restated e013 Pin Fly

> **⚠ STRUCK FIGURES — `₹61,843` was struck by e028**, whose control reproduced e026 to the paisa. Its own loader carried the same encoding defect, so the ladder priced half the sample; the corrected breakeven is 1.51 pts/leg on n=129.


**Contract first:** [PREREG.md](PREREG.md) — frozen 2026-10-03, before any code
existed here. Amendments in §9.

> ## ⚠️ SUPERSEDED BY [E028](../e028_expiry_encoding_audit/README.md)
>
> `load_front_chain_ohlc` in this experiment compared `expiry` to `str(date)` —
> the same defect e026 carried, in a second copy. It returned an empty chain for
> every 2021–2024 partition, so the Corwin-Schultz estimator below was fitted on
> a format-selected sample and **the n=64 book priced throughout this file is half
> the sessions e013 actually traded.**
>
> Re-run corrected, the breakeven is **1.51 pts/leg, not 2.64**, and the book is
> **−₹29,082 at 2.0 pts/leg**. The verdict below is kept for the record and its
> method is sound; its sample is not. Read E028.

**VERDICT: `UNRESOLVABLE ON CURRENT DATA` — and the book is *not* dead.**
*(superseded — see above)*

The slippage fear that motivated this check **does not kill e013.** The exact
number it will die on is now known:

> ### Breakeven = **2.64 index points per leg**
> Above that, net PnL is negative. Below it, positive.

What could not be settled is whether the *real* spread is above or below 2.64,
because no data on disk can measure it. That is the finding.

```
.venv\Scripts\python.exe -m experiments.e027_spread_realism.spread_realism
.venv\Scripts\python.exe -m unittest experiments.e027_spread_realism.test_spread
```

---

## 1. The number that matters

Identical marks, identical sessions, identical lot eras — only the slippage
term moves.

| Slippage | Net PnL (64 sessions) | EV/trade |
|---:|---:|---:|
| 0.05 pts/leg (one tick) | +₹84,748 | +₹1,324 |
| 0.25 | +₹78,203 | +₹1,222 |
| 0.50 | +₹70,023 | +₹1,094 |
| **0.75 (what e013 actually charged)** | **+₹61,843** | **+₹966** |
| 1.00 | +₹53,663 | +₹838 |
| **1.50 (what the plan *says*)** | **+₹37,303** | **+₹583** |
| **2.00 (realistic fill — arm B2)** | **+₹20,943** | **+₹327** |
| 2.50 | +₹4,583 | +₹72 |
| **3.00** | **−₹11,777** | **−₹184** |

**Control: +₹61,842.51 on n=64 — e026 reproduced to the paisa.** Gate 0 passed.

### The realistic-fill restatement (arm B2, 2.0 pts/leg)

2.0 pts/leg is ~33% of the median leg's own price — a genuinely poor fill, chosen
because it is pessimistic rather than because it is measured. Same 64 sessions,
same marks, only the slippage term moves.

| | Engine 0.75 | Plan 1.5 | **Realistic 2.0** |
|---|---:|---:|---:|
| Net PnL | +₹61,843 | +₹37,303 | **+₹20,943** |
| EV / trade | +₹966 | +₹583 | **+₹327** |
| Win rate | 82.8% | 71.9% | **60.9%** |
| Profit factor | 16.67 | 5.74 | **2.65** |
| Max DD | ₹1,441 (0.72%) | ₹2,290 (1.1%) | **₹4,204 (2.10%)** |
| Profit retained vs 0.75 | 100% | 60% | **34%** |
| Conservative annualised on ₹2L | ~5.42%/yr | ~3.27%/yr | **~1.83%/yr (₹3,668/yr)** |

**The edge is still real at 2.0.** Bootstrap 95% CI on EV is **[+₹106, +₹555]**,
P(EV>0) = 0.998, t = 2.84. DD is 2.1% of ₹2L — a defined-risk iron fly can
carry that.

**But it is not an annuity, and the average hides it.** 25 of 64 sessions (39%)
lose money; median session +₹124; 5th percentile −₹993 against a +₹2,752 best.
The edge lives in the right tail, which is the first thing a fatter-than-assumed
spread eats.

**And it is one year, not three:**

| Year | Sessions | Net @2.0 | Mean/session |
|---|---:|---:|---:|
| 2024 (from Jul 31) | 12 | +₹949 | ₹79 |
| **2025** | 31 | **+₹19,149** | **₹618** |
| 2026 (to Sep 21) | 21 | +₹845 | ₹40 |

**91% of the PnL is 2025.** 2026's mean session is indistinguishable from zero.

Two denominators, and the difference matters. The 64 validated sessions span
**2.14 years**; the conservative ~5.42%/yr divides into the **full 5.71-year**
calendar. That is the right direction — err low — and `test_concentration_is_
disclosed_not_averaged_away` pins it. But the sample is **era-selected, not
random**: the valid-mark share rises monotonically **38.7% → 56.4% → 70.0%** by
year, and **no pre-July-2024 session has a valid mark at all**. Measured on its
own 2.14-year span the same book reads ~14%/yr, and that number should be
believed *less*, not more.

**Plan against 1.83%/yr, and treat "one good year in three" as the shape.**

---

## 2. Three results, in order of how much they matter

### 2.1 The slippage assumption was conservative, not optimistic

`actionplan.md` §5.3 has said "1.5 points per option leg" for years. **e013 never
charged that.** The engine's friction term is `6.0 * lot_size` — six index points
per lot for the entire 4-leg, 8-leg-fill round trip, i.e. **0.75 pts/leg**. The
plan's stated model is 2× the engine's.

At the plan's own stated 1.5 pts/leg the book still makes **+₹37,303** on 64
sessions. The slippage fear was never a threat to this book.

This also **corrects the arithmetic I put in `actionplan.md` §5.5 B last**, which
computed breakeven at ~2.2 pts/leg by hand against a rounded ₹595 friction. The
exact figure, from the ladder, is **2.64**. Same conclusion, wrong number — the
document has been updated.

### 2.2 Corwin-Schultz is unusable on this data class

The PREREG's wide bound failed its own sanity gate, and the failure is
instructive rather than incidental.

| Evidence | Value |
|---|---|
| Median CS spread ÷ option's own price | **1.71×** |
| CS ÷ daily high-low range, by leg | 1.26 / 1.21 / 0.96 / 1.66 |
| Leg-days where the estimator returned nothing (α ≤ 0) | **69.1%** |
| ATM leg | "spread" of **100 points on an option worth 79** |

**Cause:** the daily high–low range on these contracts is **96–202% of the
option's price**, driven by genuine intraday mean reversion on 0–5 DTE NIFTY
options. Corwin–Schultz's separating assumption — that volatility is estimable
from close-to-close moves and the remainder is spread — is simply false in this
regime. It reads the whole range as spread.

The gate caught it because the bar was *"CS median must be below 20 points"* and
it came back at 100. A sanity bar written in advance did exactly its job.

*A bug found on the way:* an earlier draft set `gamma = beta`, which forces the
relative spread to ~0 by construction and would have reported **every leg as
perfectly liquid**. It failed only because gate 2 compared against absolute
points. `gamma` must come from closes. Both bugs are pinned in the tests.

### 2.3 What this data class simply cannot tell you

Volume on these strikes is **3.5–6.2 million contracts per day** on a 0.05-tick
exchange. The tick size was derived from the data, not assumed. A structurally
honest read is that the quoted spread is on the order of a few ticks — well
under the 0.75 the engine assumed — but **"several million contracts" is not a
quote**, and this experiment is not permitted to convert it into one.

So the book probably sits nearer the **+₹1,324** row than the **+₹966** row.
That is a *hypothesis*, not a result, and it is labelled as one.

---

## 3. Gates

| # | Gate | Result |
|---|---|---|
| 0 | Control reproduces e026 | ✅ **+₹61,842.51, n=64** |
| 0b | Plan's 1.5 pts/leg matches the engine's 0.75 | ❌ **FAIL — this is the finding** |
| 1 | Data coverage ≥ 90% | ✅ **100%** |
| 2 | CS within (1 tick, 20 pts) | ❌ **FAIL — 100 pts; estimator unusable** |
| 3 | CS within 2× of the e026 residual | ❌ (moot; CS rejected) |
| 4 | Book survives the *measured* wide bound | ⬜ **unmeasurable** |

Gates 0 and 1 pass, which means the **tight** bound is sound. Gate 2 fails, so
per the pre-registered rule the experiment reports `UNRESOLVABLE` rather than
routing to either a survival or a death verdict.

**The verdict is not "safe". A broken upper bound must never be read as a
passing grade** — that would be the same species of error this repo exists to
prevent, just pointed the other way.

---

## 4. What this changes

1. **`actionplan.md` §5.5 B is corrected** from ~2.2 to **2.64 pts/leg**, and
   the "10.7 pts" figure is gone.
2. **The slippage fear is retired.** It was sized against a ₹2,149 EV that no
   longer exists; at the real ₹966 the book has 1.89 pts/leg of margin over what
   the engine charged and 1.14 over what the plan claims.
3. **Phase 6's drift bar is re-framed.** `$1.25\times$ the modeled slippage` was
   written against a 1.5-pt model. The engine's is 0.75, so the operative
   tolerance is 0.94 pts/leg — against 1.13 pts of real headroom to breakeven.
   That is **comfortably clearable**, and the gate stops being the binding
   constraint it looked like an hour ago.

## 5. What still cannot be answered

**Fill feasibility is untouched.** These are EOD closing prices. A book that
clears at the close may still be untradeable at 12:35, and a 4-leg basket
crossing four markets at once is exactly where a close-mark says nothing.
That remains e009's job, and it is the only thing that can convert
`UNRESOLVABLE` into a decision.

**e026's one-sidedness stands.** The 12:35 entry credit is still Black-Scholes.

## 6. Artifacts

| File | What |
|---|---|
| `PREREG.md` | Frozen contract, the estimator's declared limitation, amendments |
| `spread_realism.py` | Arms, the CS estimator, tick derivation, the breakeven ladder |
| `test_spread.py` | 19 tests — control, the CS failure mode pinned, ladder consistency, the 2.0-pt arm pinned to `price_book`, concentration disclosure |
| `artifacts/verdict.json` | Every gate, the ladder, arm `B2_conservative_2p0pts`, the `concentration` block, per-leg decomposition |
| `artifacts/leg_spreads.csv` | 256 leg-days with OHLC, volume and the CS estimate |
| `artifacts/book_by_spread.csv` | The 64 sessions priced at every rung |

Registered in [../common/leak_registry.py](../common/leak_registry.py) as
`none / live True` — it produces **no strategy signal and no forward PnL
claim**, only the cost of trading a signal that already exists.