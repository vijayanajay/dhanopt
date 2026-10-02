# E013 — 0DTE Expiry Microstructure & Pin Dynamics
**Pre-Registration Protocol (Frozen 2026-10-02)**

## 1. Quantitative Hypothesis
On weekly index expiry sessions ($dte \le 1$, Tuesdays and Thursdays), dealer gamma inventory creates two distinct afternoon regimes:
1. **The Pinning Regime:** If morning realized range is compressed relative to the opening straddle premium ($\text{Expansion Ratio} \le 0.65$), option sellers actively defend strikes. Dealer gamma hedging forces spot to mean-revert toward the high-OI pin strike. Entering an ATM Iron Butterfly at 12:35 IST captures the afternoon theta collapse into the 15:15 IST close.
2. **The Gamma Squeeze Regime:** If morning range expands aggressively ($\text{Expansion Ratio} \ge 1.20$), option sellers are overrun and forced to delta-hedge in the direction of the break, fueling an afternoon gamma cascade.

$$\text{Expansion Ratio} = \frac{\text{High}_{09:15-12:30} - \text{Low}_{09:15-12:30}}{\text{ATM Straddle Premium at 09:20}}$$

---

## 2. Replay Architecture & Execution Rules

1. **Information Frontier:**
   * Range and Straddle evaluated strictly on bars $\le 39$ (09:15 to 12:30 IST).
   * **Execution Rule:** All orders fill strictly at **Bar 40 Open (12:35:00 IST)**. Same-bar execution is banned.
2. **Strategy A (Pin Harvest — Iron Butterfly):**
   * Condition: $\text{Expansion Ratio} \le 0.65$.
   * Structure:
     * SELL 1 lot ATM CE at $K_{\text{ATM}}$
     * SELL 1 lot ATM PE at $K_{\text{ATM}}$
     * BUY 1 lot Wing CE at $K_{\text{ATM}} + 150$
     * BUY 1 lot Wing PE at $K_{\text{ATM}} - 150$
   * Exit: 15:15 IST (Bar 71 Close).
3. **Strategy B (Gamma Breakout Follower):**
   * Condition: $\text{Expansion Ratio} \ge 1.20$.
   * Structure: Directional debit spread (Bull Call Spread if $S_{12:30} \ge S_{09:20}$, else Bear Put Spread).
   * Exit: 15:15 IST (Bar 71 Close).
4. **Middle Zone ($0.65 < \text{Expansion Ratio} < 1.20$):**
   * `NO TRADE` (Indifferent regime; unfavorable risk-reward).
5. **Friction & Lots:**
   * Pin Iron Fly (4 legs): Brokerage ₹80 entry, ₹80 exit, 0.1% STT on sell legs, 6.0 pts slippage per lot, GST, exchange fees.
   * Breakout Spread (2 legs): Brokerage ₹40 entry, ₹40 exit, 3.0 pts slippage per lot.
   * Era-correct lots: `experiments.common.lots.lot_for_date`.

---

## 3. Pre-Registered Kill Criteria (Non-Negotiable)

| Metric | Pass Threshold | Failure Action |
|---|---|---|
| **1. Post-12:30 Expectancy** | Net EV $\ge +₹600$ per lot traded after all friction | Reject if net EV $\le ₹150$ |
| **2. Fill Feasibility** | $\ge 80\%$ of required legs observable within 5-min window | Reject if data latency prevents execution |
