# E029 — Does Any Slice of e013 Survive Its Own Early Era?

**Contract first:** [PREREG.md](PREREG.md) — frozen 2026-10-03, before any code
existed here. No amendments.

**VERDICT: `NO SLICE` — and the early era is not a cost problem.**

```
.venv\Scripts\python.exe -m experiments.e029_era_slices.eras
.venv\Scripts\python.exe -m unittest experiments.e029_era_slices.test_e029
```

---

## 1. Why this was worth an afternoon

e028 recovered the four years of real marks that its own expiry-encoding bug had
hidden. For the first time the repo had **any** measured PnL for 2021–2023 —
and it was bad:

| Era | n | Net PnL @0.75 | mean/session |
|---|---:|---:|---:|
| 2021–2023 | 58 | −₹15,249 | −₹263 |

The honest question: does the signal fail outright, or fail *in aggregate* while
working in an identifiable slice? If a slice exists there is a book to rebuild.

## 2. The design, and the trap it avoids

The obvious version — filter on 2021–2023, then score on all six years — is
**in-sample**. The early era loses ₹15,249 over 58 sessions; almost any
aggressive filter turns a small losing sample positive. You would have "found"
a book before touching the data.

So the contract froze a holdout:

> **Selection reads 2021–2023 (n=58). The verdict reads 2024–2026 (n=71). They never overlap.**

Five structural filters (PREREG §3.3), each using only fields known at or
before the 12:35 entry: `expansion ≤ 0.50`, `expansion ≤ 0.40`, `dte == 2`,
their conjunction, and `credit ≥ median`. Selection rule frozen: highest
selection-era EV among those with EV > 0 and n ≥ 20, ties to the smaller n.
**Exactly one filter crosses into the holdout** — and here, none did.

Gate 0 passed: the unfiltered book reproduces e028 to the rupee
(**+₹45,568** @0.75, **−₹29,082** @2.0, n=129).

## 3. The result

| Filter | n (selection) | Net | EV @2.0 |
|---|---:|---:|---:|
| *unfiltered* | 58 | −₹46,499 | −₹802 |
| F1 `expansion ≤ 0.50` | 26 | −₹17,369 | −₹668 |
| F2 `expansion ≤ 0.40` | 9 | −₹6,134 | −₹682 |
| F3 `dte == 2` | 54 | −₹44,437 | −₹823 |
| F4 `dte 2 AND exp ≤ 0.50` | 25 | −₹16,734 | −₹669 |
| F5 `credit ≥ selection median` | 29 | −₹20,455 | −₹705 |

**None is positive.** Gate 1 fails; the experiment stops there with `NO SLICE`
and nothing is carried out of sample. Tightening the expansion filter makes the
loss *smaller* (F1 loses ₹17k where the book loses ₹46k) but never positive —
the "quieter mornings" hypothesis buys less exposure, not better sessions.

## 4. The finding that actually matters

Not a gate, and explicitly **not** a filter — reported because it is true and
because it is the trap:

| | n | @0.75 | @1.50 | @2.00 |
|---|---:|---:|---:|---:|
| **2021–2023** | 58 | −₹263 | −₹586 | −₹802 |
| **2024–2026** | 71 | **+₹857** | **+₹490** | **+₹245** |
| six-year | 129 | +₹353 | +₹6 | −₹225 |

Two things fall out:

1. **The early era is not a slippage problem.** It is negative at the engine's
   own optimistic 0.75-pt fill as well as at a realistic 2.0. No fill
   assumption rescues it, so there is nothing to re-price and no execution
   story to tell. The signal simply did not work before 2024.
2. **2024–2026 is positive at every fill** — +₹245 EV at 2.0 pts, PF 2.07.

> ### Why "just trade 2024 onward" is not offered as a slice
>
> Because **the era boundary was chosen by looking at the eras.** It is the most
> overfit filter available and it has no holdout by construction — there is no
> data after 2026 to test it on. It is a *regime observation*, not a book. The
> warning ships inside `verdict.json` as well as here, and
> `test_f5_is_an_era_detector` pins the same trap in the filter set: F5's credit
> threshold selects **100% of the 2024–2026 era** and about half of the early
> one. A filter that is really a date filter always looks brilliant in sample.

The six-year book is dead because it spans a period where the signal did not
work. Restating it as "2025 alone" would be e028's "93% of PnL from 2025"
dressed up as a strategy.

## 5. What this adds to the record

- e028 killed e013 on execution and era. e029 closes the last door: it is not
  execution cost, not slippage, and not a dilutable slice. **The signal was
  regime-dependent and there is no way to know which regime you are in before
  trading it.**
- It is the first experiment in this repo to use a **held-out era** as the
  primary verdict and to report an in-sample arm beside it. Gates 2 and 3 (EV
  > 0, and EV > the 95th percentile of 500 same-size random subsets) were
  written for the day a filter *does* qualify. They did not fire today, and the
  machinery is left in place and tested so the next candidate is held to them.

## 6. What it does not do

Nothing was re-selected, re-marked or re-priced. Arm 0 is e028's book verbatim.
The 12:35 entry credit remains Black-Scholes in every arm — no intraday option
price on disk — so **this experiment could only move the number against the
book, never for it.** It moved no signal, no timing, no cost model; it removed
sessions.