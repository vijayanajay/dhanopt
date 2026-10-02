# E012 — Volatility Skew & Asymmetric Ratio Architecture

**Contract & Pre-Registration:** [PREREG.md](PREREG.md) — frozen 2026-10-02 before running simulation.  
**Question:** Does harvesting peak 25-Delta Put Skew ($\text{Skew}_{25\Delta} \ge \text{P}_{90}$) via 1×2 Put Ratio Spreads with Broken-Wing tail protection generate positive net expectancy after real Zerodha friction and path exits?

---

## 1. What Was Implemented

1. **Information Frontier:** Strictly $t-1$ observable signal.
   * Parameterized implied volatility across strikes on $t-1$ EOD FO Bhavcopy (`data/historical/`).
   * Computed:
     $$\text{Skew}_{25\Delta, t-1} = \frac{\sigma_{\text{IV}}(25\Delta \text{ PE}) - \sigma_{\text{IV}}(25\Delta \text{ CE})}{\sigma_{\text{IV}}(\text{ATM})}$$
   * Entry Gate: $\text{Skew}_{25\Delta, t-1} \ge \text{Percentile}_{90}(\text{trailing } 60\text{ days})$ and $\text{Skew} > 0$. Strictly shifted with `shift(1)`.
2. **Replay Engine ([replay_skew.py](replay_skew.py)):**
   * Entry at 09:20 IST (Bar 1 Open).
   * **Structure (1×2 Broken-Wing Put Ratio Spread):**
     * BUY 1 lot $35\Delta$ Put ($K_{\text{long}}$).
     * SELL 2 lots $15\Delta$ Put ($K_{\text{short}}$).
     * BUY 1 lot $2\Delta$ Put ($K_{\text{wing}}$) for tail protection.
   * **Path Exits (5-min bars):**
     * TARGET: 50% of maximum theoretical spread profit.
     * STOP: Loss reaches $1.5\times$ initial outlay OR spot breaches below $K_{\text{short}}$.
     * EOD: Square off at 15:15 IST (Bar 71).
   * **Friction:** 4 legs (₹80 brokerage entry, ₹80 exit, 0.1% STT on sell turnover, 6.0 points slippage per lot total, GST, exchange fees). Era-correct lots (75 $\to$ 50 $\to$ 25 $\to$ 75 $\to$ 65).

---

## 2. Verdict — FAIL ON ALL THREE KILL CRITERIA (Strategy Dead)

Simulated across 1,415 historical sessions (2021-01 to 2026-09, 5.7 years). The Skew signal triggered **115 trading sessions (20.2 trades/year)**.

| Kill Criterion | Pre-Registered Bar | Observed Result | Status |
|---|---|---:|---|
| **1. Profit Factor** | $PF \ge 1.80$ over walk-forward | **0.13** | ❌ **DECISIVE FAIL** |
| **2. Win Rate** | $\ge 70.0\%$ (reject if $> 3$ consec losses) | **14.78% (15 consec losses)** | ❌ **DECISIVE FAIL** |
| **3. Capacity** | $\ge 25$ occurrences per year | **20.2 trades/year** | ❌ **FAIL** |

---

## 3. Performance Summary

```
Total Trades:               115 sessions (20.2 trades/yr)
Win Rate:                   14.78% (17 wins / 98 losses)
Total Net PnL:              -₹98,801.92
Average Net / Trade:        -₹859.15
Profit Factor:              0.13 (Gross Profit ₹14,642 / Gross Loss ₹1,13,444)
Max Peak-to-Trough DD:      -₹97,979.82 (-48.99% of ₹2L bankroll)
Annualized Sharpe:          -3.06
Max Consecutive Losses:     15 consecutive losing trades
Exit Distribution:          EOD: 102 (88.7%) | STOP: 11 (9.6%) | TARGET: 2 (1.7%)
```

---

## 4. The Kailash Nadh Post-Mortem: Why Retail Ratio Spreads Bleed

This is one of the cleanest scientific negative findings in options market microstructure:

1. **The "Free Lunch" Financing Myth:**
   * Retail option manuals claim: *"Sell two cheap OTM puts to pay for an ATM put and get downside protection for free or a credit."*
   * **The Reality on Nifty:** Even when 25-delta Put Skew is in the 90th percentile, two $15\Delta$ puts do **not** generate enough premium to finance a $35\Delta$ put plus the $2\Delta$ wing.
   * Across the 115 trades, the average entry was a **net debit of 45.88 index points**.
2. **Theta Decay Destroys the Net-Long Structure:**
   * A $35\Delta$ put carries significant extrinsic value close to spot. Two $15\Delta$ puts are 300–400 points OTM.
   * During intraday trading, unless Nifty plunges directly into the narrow pocket between $K_{\text{long}}$ and $K_{\text{short}}$, the $35\Delta$ put suffers rapid intraday theta decay faster than the deep OTM puts decay.
   * On **88.7% of days (102 of 115)**, Nifty did not crash into the strike pocket; the position decayed into the 15:15 EOD square-off.
3. **The Multi-Leg Friction Trap:**
   * Gross PnL before friction averaged a pathetic **+₹33.10 per trade**.
   * But trading 4 legs (crossing the bid-ask spread on 4 options + brokerage + STT) cost **₹892.24 in friction per trade**.
   * Friction transformed a flat, unmonetizable structure into a steady, brutal bleed of **-₹859.15 per trade**, producing **15 consecutive losses** and a **-49% account drawdown**.

**Standing:** e012 is definitively dead. The hypothesis that high skew can be monetized via ratio spreads is falsified.

---

## 5. Artifacts Checklist

* `artifacts/skew_daily.parquet` — Daily OHLC, ATM IV, 25-delta Put/Call IVs, 25-Delta Skew, and shifted entry signals.
* `artifacts/skew_trades.csv` — Trade-by-trade log of all 115 sessions with strikes, entry credit/debit, exit reason, and net PnL.
* `artifacts/metrics.json` — Frozen performance metrics.
