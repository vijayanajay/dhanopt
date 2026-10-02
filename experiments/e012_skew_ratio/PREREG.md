# E012 — Volatility Skew & Asymmetric Ratio Architecture
**Pre-Registration Protocol (Frozen 2026-10-02)**

## 1. Quantitative Hypothesis
Retail market participants systematically overpay for Out-Of-The-Money (OTM) Put protection due to downside panic (crashophobia). This creates persistent positive volatility skew between OTM Puts and OTM Calls:
$$\text{Skew}_{25\Delta} = \frac{\sigma_{\text{IV}}(25\Delta \text{ PE}) - \sigma_{\text{IV}}(25\Delta \text{ CE})}{\sigma_{\text{IV}}(\text{ATM})}$$

When $\text{Skew}_{25\Delta}$ expands to its trailing 60-day 90th percentile, OTM Put implied volatility is empirically bloated. Rather than naked selling or directional spreads, we deploy an asymmetric **1×2 Put Ratio Spread with Broken-Wing Tail Protection**:
* **Long Leg:** Buy 1 lot $35\Delta$ Put (captures moderate downside).
* **Short Legs:** Sell 2 lots $15\Delta$ Put (monetizes the overpriced skew peak).
* **Wing Leg:** Buy 1 lot $2\Delta$ Put (caps catastrophic tail gap risk and defines maximum capital loss).

---

## 2. Mathematical Formulations & Execution Protocol

### 1. Daily Skew Measurement ($t-1$ EOD):
From the $t-1$ FO Bhavcopy partition:
* Locate the nearest weekly/monthly expiry.
* Identify strikes matching:
  * ATM ($50\Delta$): $\Delta \approx 0.50$
  * $25\Delta$ Call: $\Delta_{\text{CE}} \approx 0.25$
  * $25\Delta$ Put: $|\Delta_{\text{PE}}| \approx 0.25$
* Compute:
  $$\text{Skew}_{25\Delta, t-1} = \frac{\sigma_{\text{IV}}(25\Delta \text{ PE}) - \sigma_{\text{IV}}(25\Delta \text{ CE})}{\sigma_{\text{IV}}(\text{ATM})}$$
* Signal Gate: $\text{Skew}_{25\Delta, t-1} \ge \text{Percentile}_{90}(\text{trailing } 60\text{ days})$ and $\text{Skew} > 0$. Strictly shifted with `shift(1)`.

### 2. Intraday Execution on Day $t$:
* **Entry:** At 09:20 IST (Bar 1 Open):
  * Buy 1 lot $35\Delta$ Put ($K_{\text{long}}$).
  * Sell 2 lots $15\Delta$ Put ($K_{\text{short}}$).
  * Buy 1 lot $2\Delta$ Put ($K_{\text{wing}}$).
* **Path Exits (5-min bars):**
  * **TARGET:** Portfolio net profit reaches $\ge 50\%$ of max theoretical spread profit.
  * **STOP:** Loss reaches $\ge 1.5\times$ initial entry debit/credit OR spot price breaches below short strike $K_{\text{short}}$.
  * **EOD:** Square off all 4 legs at 15:15 IST (Bar 71).
* **Friction Schedule:**
  * 4 legs: Brokerage ₹20/order ($₹80$ entry, $₹80$ exit).
  * STT: 0.1% on sell leg turnover.
  * Slippage: 1.5 points per leg ($6.0$ points per lot total).
  * Era-correct lot sizes via `experiments.common.lots.lot_for_date`.

---

## 3. Pre-Registered Kill Criteria (Non-Negotiable)

| Metric | Pass Threshold | Failure Action |
|---|---|---|
| **1. Profit Factor** | $PF \ge 1.80$ over 2021–2026 walk-forward | Discard strategy if $PF < 1.40$ |
| **2. Win Rate** | $\ge 70.0\%$ on valid signal sessions | Reject if tail loss clusters exceed 3 consecutive losses |
| **3. Capacity** | $\ge 25$ occurrences per year | Reject if signal fires $< 15$ times/year (starvation) |
