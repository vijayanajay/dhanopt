# E028 — The Expiry Encoder Was a String Comparison Against a Date

**Contract first:** [PREREG.md](PREREG.md) — frozen 2026-10-03, before any code
existed here. Two post-run amendments in §8, logged not edited.

**VERDICT: `DEAD_AT_REALISTIC_FILL`.** The encoder bug was real, it cost four
years of data, and fixing it does **not** rescue the book. It kills it at a fill
e027 could not see.

```
.venv\Scripts\python.exe -m experiments.e028_expiry_encoding_audit.audit_encoding
.venv\Scripts\python.exe -m experiments.e028_expiry_encoding_audit.intrinsic_audit
.venv\Scripts\python.exe -m unittest experiments.e028_expiry_encoding_audit.test_e028
```

---

## 1. The defect

[audit_realmark.py](../e026_realmark_audit/audit_realmark.py) filtered the option
chain like this:

```python
n = n[n["expiry"] == str(front_expiry)]      # a date, compared to a string
```

`front_expiry` is a `datetime.date`. `str()` of it is `2023-12-20`. The bhavcopy
store holds **two encodings**:

| Era | Stored `expiry` |
|---|---|
| 2021–2024 | `04-Feb-2021` |
| 2025+ | `2025-01-02` |

So the comparison was true for **zero** pre-2025 sessions. The chain came back
empty, all four legs were `None`, and §5.5's fail-closed rule — correctly, on the
evidence it was given — dropped the session as `NO TRADE`.

**The guard worked. The lookup under it was wrong.** Nothing alerted, because a
lookup returning nothing and a market with nothing to say look identical to the
caller that consumes them.

Measured across the store: **356 of 576** wall sessions returned an empty front
chain. `e018` never had this bug — it builds an `exp_dt` date column. `e026` and
`e027` each carried their own copy of the broken loader, so neither could catch it
in the other.

## 2. The fix, at the shared root

Fixed in [core/feeds/bhavcopy.py](../../core/feeds/bhavcopy.py), not in the
experiment, so a fifth consumer cannot inherit it:

- `with_expiry_date(df)` attaches a parsed `expiry_date` column and **raises** if
  there is no `expiry` column.
- The normalize boundary now writes **ISO** for every UDiff partition, so the
  store converges on one encoding going forward.
- `filter_nifty_options` compares `expiry` **as a date**.

The defective loader is retained in e026 as `load_front_chain_string_eq`,
renamed, labelled `CONVICTED — do not use`, and kept solely as this
experiment's control arm.

## 3. Arms

Same sessions, same signals, same IV, same lot eras. One thing moves: how the
chain is addressed.

| | Arm A (control, string eq) | Arm B (corrected) |
|---|---:|---:|
| Marks found | 106 | **193** |
| Usable (non-expiry-day exit) | 64 | **129** |
| Sessions recovered | — | **+65** |

Marks are **identical on every session both arms share** — the fix only adds
sessions, it never re-prices one. That is the contract-identity check, and it is
the reason the delta below is attributable to the bug and nothing else.

**Gate 0 passed: arm A = ₹61,842.51 on n=64, e027's 2.64 pts/leg breakeven
reproduced exactly.** The control is the predecessor to the paisa.

## 4. The ladder

| Slippage | Arm A (n=64) | | Arm B (n=129) | |
|---:|---:|---:|---:|---:|
| | Net PnL | EV/trade | Net PnL | EV/trade |
| 0.05 pts/leg | +₹84,747 | +₹1,324 | +₹87,372 | +₹677 |
| 0.25 | +₹78,203 | +₹1,222 | +₹75,428 | +₹585 |
| **0.75 (engine)** | **+₹61,843** | **+₹966** | **+₹45,568** | **+₹353** |
| 1.00 | +₹53,663 | +₹838 | +₹30,638 | +₹238 |
| **1.50 (plan states)** | +₹37,303 | +₹583 | **+₹778** | **+₹6** |
| **2.00 (realistic)** | **+₹20,943** | **+₹327** | **−₹29,082** | **−₹225** |
| 2.50 | +₹4,583 | +₹72 | −₹58,942 | −₹457 |
| **3.00** | −₹11,777 | −₹184 | −₹88,802 | −₹688 |

> ### Breakeven slips **2.64 → 1.51 points per leg.**
> The plan's stated assumption is 1.5. The engine charges 0.75. The honest
> number is barely below the plan's, and the book turns negative at a fill
> nobody would call pessimistic.

Arm B's EV/trade is *lower* than arm A's at every rung despite a *larger* total —
the recovered sessions are, on average, worse than the ones the bug left in. The
bug was not hiding a bad book. It was hiding a **large** bad book behind a small
good-looking one.

| 2.0 pts/leg | Arm A | Arm B |
|---|---:|---:|
| Win rate | 60.9% | **31.0%** |
| Profit factor | 2.65 | **0.54** |
| Max DD | ₹4,204 (2.10%) | **₹52,438 (26.2%)** |
| Profit retained vs 0.75 | 34% | **—** |

## 5. Era

Arm B's recovered sample spans **5.71 years**, not 2.14 — and it is worse.

| Year | Sessions | Net PnL |
|---|---:|---:|
| 2021 | 19 | −₹7,487 |
| 2022 | 21 | −₹1,589 |
| 2023 | 18 | −₹6,173 |
| 2024 | 19 | +₹3,923 |
| 2025 | 31 | +₹42,399 |
| 2026 | 21 | +₹14,495 |

**93.0% of net PnL comes from 2025** — against a bar of 60%. Three consecutive
losing years, then one year that carries everything. Arm A's 68.6% looked bad;
the truth underneath it was 93.0%, and the span is five years wider.

## 6. Gates

| # | Gate | Bar | Observed | |
|---|---|---|---|---|
| 0 | Control reproduces predecessor | ₹61,842.51 / n=64 / 2.64 pts | exact | **PASS** |
| 1 | Contract identity | 0 mismatches | 0 | **PASS** |
| 2 | Arithmetic impossibility | 0 bound violations | 0 | **PASS** |
| 3 | Coverage | ≥95% of markable sessions marked | 100.0% (129/129) | **PASS** |
| 4 | Edge at realistic fill | EV ≥ +₹400 @ 2.0 pts | **−₹225** | **FAIL** |
| 5 | Era robustness | no year >60% of PnL | **93.0%** | **FAIL** |
| 6 | Round-trip identity | both encodings parse; no empty on an existing partition | pass | **PASS** |
| 7 | Marks not stale-early *(non-voiding, added post-run)* | 0 legs >4 ticks below intrinsic | **52 / 772** | fail |

Gate 3's literal PREREG denominator is also reported: **66.84%** (129/193). The
other 64 are expiry-day exits, which have no mark by construction. See §8.

## 7. Two things this experiment did not cause, and found anyway

**The impossibility check was wrong before the data was.** e026's
`check_impossibility` asserted the iron-fly bound `(entry − W) ≤ gross ≤ entry` on
*every* real mark, contradicting its own docstring — it is an expiry-payoff
statement, valid only at expiry. It never fired, because the one session that
breached it (**2023-12-20**) was excluded by the encoding bug. Root cause is real
market movement, not a bad print: spot fell 374 points that day and the ATM
straddle closed at 359.4 against an entry credit of 102.04. The bound is now
asserted only when `expiry_is_trade_date`.

**Stale-early marks run in the book's favour.** A stale final print reads low; a
pin fly entered on a low mark books a *cheap* fly. No gate above could see this,
because every one of them is looking for the number to be too good. 52 of 772
legs close more than 4 ticks below intrinsic against the same-expiry futures
close, on legs carrying 10–78M contracts. Flooring them at intrinsic
([intrinsic_audit.py](intrinsic_audit.py)) costs **₹3,578** at 0.75 pts/leg and
**₹3,578** more at 2.0.

> The one correction found last is the only one that made the book worse than
> *both* the published number and the un-corrected corrected-number. That is the
> signature of a check worth having run.

## 8. Amendments to the PREREG

Full text in [PREREG.md §8](PREREG.md). In short:

1. **Gate 3's denominator.** The bar named the wrong population. 64 of the 193
   selected sessions are selected *to exit on their own expiry day*, so they
   have no mark by design. Literal 66.84% ships alongside the markable 100.00%.
   No bar moved.
2. **Gate 7 added after a clean run.** Gates 0–6 passing on an audit that
   overturned a conviction deserved suspicion. Non-voiding, evidence only — and
   it found something.

Gate 4 and gate 5 are **untouched and both fail.** The verdict is read at the
frozen bars.

## 9. What this supersedes

- **e026 arm B** (+₹61,843, n=64) — correct method, format-selected sample.
- **e027's slippage ladder and its 2.64 pts/leg breakeven** — same sample.
- **actionplan.md §5.5 B/C** and **RETROSPECTIVE.md §5.11** — derived from it.

e027's `UNRESOLVABLE ON CURRENT DATA` verdict is also overtaken: the sample it
could not measure turned out to be half the sample, and at 2.0 pts/leg it is not
unresolved, it is negative.

## 10. What e028 does not do

Entry credit remains Black-Scholes in every arm — there is no intraday option
price on disk, exactly as in e026. **This correction can only move the number
against the book, never for it.** No signal, no timing, no cost model changed.
The one thing it changed was which sessions exist, and that changed the answer.