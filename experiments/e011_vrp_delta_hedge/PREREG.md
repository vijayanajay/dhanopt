# E011 — True Variance Risk Premium (VRP) & Dynamic Delta-Neutral Replay
**Pre-Registration Protocol (Frozen 2026-10-02)**

## 1. Quantitative Hypothesis
The Variance Risk Premium (VRP) is the structural difference between forward implied volatility and realized volatility:
$$\text{VRP}_t = IV_{\text{ATM}, t-1} - \sigma_{\text{realized}, t-1}$$
Over long horizons, index option buyers pay an insurance premium, causing $\mathbb{E}[IV] > \mathbb{E}[RV]$.

Previous credit strategies in this repository ([e004](file:///d:/Code/dhanopt/experiments/e004_intraday_replay), [e005](file:///d:/Code/dhanopt/experiments/e005_theta_condor)) failed because:
1. Static premium stop-losses (e.g. 1.4× credit SL) trigger at the worst possible moment—at the peak of intraday IV expansion during spot whipsaws.
2. They traded unconditionally or on leaky EOD walls without measuring whether IV was genuinely expensive relative to forward volatility.

**Institutional Solution:**
1. Filter entries: Only sell short volatility when $t-1$ VRP is in the top 80th percentile of its trailing 60-day distribution.
2. Neutralize direction: Dynamically hedge portfolio delta using Nifty Futures (or spot proxy) whenever $|\Delta_{\text{net}}| \ge 0.15 \times \text{lot\_size}$ (approx 10 index points).
3. Enforce the hard rule: All hedge signals evaluated at bar $t$ execute strictly at bar $t+1$ Open. Same-bar execution is banned.

---

## 2. Mathematical Formulations

### Realized Volatility Estimators:
Garman-Klass intraday volatility over a trailing $n=10$ session window:
$$\sigma_{GK}^2 = \frac{252}{n} \sum_{i=1}^n \left[ 0.5 \left(\ln\frac{H_i}{L_i}\right)^2 - (2\ln 2 - 1) \left(\ln\frac{C_i}{O_i}\right)^2 \right]$$

### Implied Volatility ($IV_{\text{ATM}}$):
Inverted Black-Scholes volatility from the $t-1$ EOD ATM straddle price from `data/historical/`.

### Delta Neutralization Mechanism:
At each 5-minute bar $i$:
$$\Delta_{\text{net}, i} = -(\Delta_{\text{CE}, i} + \Delta_{\text{PE}, i}) + h_{i-1}$$
If $|\Delta_{\text{net}, i}| \ge 0.15$:
* Order triggered at bar $i$.
* Filled at bar $i+1$ Open with $0.5$ pts slippage.
* Target hedge position: $h_i = h_{i-1} - \Delta_{\text{net}, i}$.

---

## 3. Friction & Cost Schedule
* **Option Legs:**
  * Brokerage: ₹20 per order.
  * STT: 0.1% on sell turnover (SEBI mandate).
  * Slippage: 1.5 points per leg.
  * Exchange (0.0505%) + SEBI (₹10/Cr) + Stamp (0.003%) + GST (18%).
* **Futures Hedge:**
  * Brokerage: ₹20 per order.
  * STT: 0.02% on sell turnover.
  * Slippage: 0.5 points per hedge execution.
  * Exchange (0.0019%) + GST (18%).
* **Lot Sizing:** Exact era-correct lots via `experiments.common.lots.lot_for_date`:
  * Pre-July 2021: 75
  * 2021-07 to 2024-04: 50
  * 2024-04 to 2024-11: 25
  * 2024-11 to 2025-12: 75
  * 2025-12 to Present: 65

---

## 4. Pre-Registered Kill Criteria (Non-Negotiable)

| Metric | Pass Threshold | Failure Action |
|---|---|---|
| **1. Net Sharpe Ratio** | $\ge 1.5$ annualized net of all friction | Discard strategy if Sharpe $< 1.0$ |
| **2. Maximum Drawdown** | $\le 8.0\%$ of ₹2,00,000 (₹16,000) | Hard stop; failure if max DD $> ₹16,000$ |
| **3. Slippage Cliff** | Positive net PnL at $\ge 2.5\times$ modeled slippage | Reject if edge evaporates at $< 3.0$ pts/leg |
