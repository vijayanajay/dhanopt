# E010 — One Frozen Credit Spread + a LightGBM When-Gate (the program's last cell)

**Contract:** [PREREG.md](PREREG.md) (frozen before any code; amendment 2
pre-run). **Question:** does a single LightGBM when-gate on t-1 features turn
one fixed credit-spread structure into a positive book at ~2–3 trades/month?
**Status: run as frozen, once, no sweeps.**

## Verdict — FAIL (3 of 5 kill criteria)

Walkforward OOS 2022–2026 (expanding, yearly refits, 1,164 OOS days), threshold
0.55 frozen, label = the frozen spread's own friction-inclusive net_pnl:

| Kill criterion | Bar | Observed | Pass? |
|---|---|---:|---|
| 1. OOS net | > ₹0 | **−₹121,187** (265 trades) | ❌ |
| 2. Edge | PF ≥ 1.5, n ≥ 30 | **PF 0.36, WR 32.1%** (n = 265 — judged, not starved) | ❌ |
| 3. Signal exists | Brier beats majority | **0.2952 < 0.3186** | ✅ |
| 4. Beats baselines | ≥ always-on and ≥ random-2/mo | always-on −₹560,168; **random −₹57,982 > gated −₹121,187** | ❌ |
| 5. Capacity | ≥ 1 trade/yr | 39–79/yr (every year) | ✅ |

## The mechanism — discrimination without monetization

Kill 3 passing while kill 1 fails is the cleanest scientific result of the
program: **the model's probabilities carry real OOS information** (it can
rank days better than the base rate, across 1,164 unseen days), **and the
days it selects still lose money**. That is e003's meta-finding at full
scale: per-day discriminative signal exists in t-1 features, but the
underlying structure loses more on the selected days than its credit pays —
selection multiplies a negative by a smaller negative. The gate cut the
always-on loss 4.6× (−₹560k → −₹121k), which proves the filter works and is
worthless: the owner's question "would it improve results?" has the honest
answer *yes, from −₹560k to −₹121k, i.e. from terrible to still-negative*.
The random 2/month baseline (−₹58k) beating both books shows how much of
"selection" here is just trading less.

Per-year trade counts (kill 5): 2022: 57, 2023: 79, 2024: 46, 2025: 39,
2026: 44 — no stability in quality, losses in every year.

## Protocol notes

- Structure: SELL ATM put + BUY ATM−150 put (credit), ATM from the 09:15
  open, IV from the t-1 straddle, exits 0.35×/0.70× of credit (e004's frozen
  fractions; themselves sweep-selected in v6 — caveat carried, not repaired).
- Features: e002's 16 t-1 columns, shift(1)-pinned; **no wall day-t input
  anywhere** — the e001-family leak had no vector in, so this FAIL is clean.
- One run: no threshold tuning, no feature selection, no variants. All
  artifacts: [credit_labels.csv](artifacts/credit_labels.csv) (1,410 days,
  always-on −₹714,016 / WR 35.4%), [gate_oos.json](artifacts/gate_oos.json),
  [gate_oos_trades.csv](artifacts/gate_oos_trades.csv).
- Registered `t-1 / live: True` in the leak registry before its numbers.
- Self-checks: [test_gate.py](test_gate.py) (fold hygiene, kill-bar logic on
  synthetic frames, frozen-threshold pins — 7 tests).

**Where this leaves the program:** every planned cell is now closed with
evidence — structure loses (e004), selection on walls was a leak (e002),
no per-trade signal pays (e003, e010), walls die on every data class
(e007, e008), and an ML when-gate on a clean label still cannot make one
fixed structure positive (e010). The only certified-positive action remains
the collateral play ([../../COLLATERAL_PLAYBOOK.md](../../COLLATERAL_PLAYBOOK.md)).
