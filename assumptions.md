# Core System Assumptions & Architectural Invariants

This document establishes the non-negotiable quantitative and architectural invariants for the DhanOpt Nifty options engine. These rules prevent look-ahead bias, artificial inflation, and fail-open risk regressions.

---

## 1. Temporal Horizon & No Look-Ahead Policy ($t-1$ Invariant)

- **The Information Frontier:** At 09:15 on trading session $t$, the only observable data for session $t$ is the opening quote. The closing price, high, low, intraday path, and settlement at 15:30 do not exist.
- **Signal Formation:** Any strategy decision entering at session $t$ open must evaluate information strictly known prior to 09:15:
  $$\text{Signal}(t) = f(\text{Data}_{t-1}, \text{Data}_{t-2}, \dots, \text{Open}_t)$$
- **Forbidden Pattern:** Evaluating session return `day_pct = (close[t] - open[t]) / open[t]` to enter a position at `open[t]` is look-ahead leakage. It mechanically guarantees winning trades (e.g., 87% win rates / Profit Factor 26) and corrupts calibration files.
- **Cold Start:** If session $t-1$ context is absent (e.g., the first session in a dataset or a detached partition), the engine must fail closed and emit `None` (no trade).
- **Intraday Path Ceiling (`ponytail`):** Daily bars proxy execution via `open -> close`. They cannot simulate intraday stop-loss or profit-target triggers. Path fidelity requires 1-minute or 5-minute bar history.

---

## 2. Invariant Units & Historical Lot Size Eras

- **Primary Currency is Points:** True options edge is measured in **index points** (`exit_points - entry_points - friction_points`), which remain invariant across regulatory revisions.
- **Rupee Valuation:** Rupee figures are cosmetic scalings of points and must reflect the exact regulatory lot size in force on `trade_date`:
  | Era | Nifty Lot Size | Governing Authority / Circular |
  |---|:---:|---|
  | Pre-July 2021 | 75 | NSE Historical Norm |
  | 2021-07-01 to 2024-04-25 | 50 | NSE Circular Ref 25/2021 |
  | 2024-04-26 to 2024-11-19 | 25 | NSE Circular Ref 45/2024 |
  | 2024-11-20 to Present | 75 | SEBI Index Derivatives Framework |
- **Inflation Prevention:** Hardcoding `* 75` for all historical years inflates 2021–2024 rupee PnL by 50% to 200%. All PnL arithmetic and option leg quantities must call `config.get_nifty_lot_size(trade_date)`.
- **Pre-2015 Data:** Historical data prior to 2015 is excluded from rupee PnL aggregation and reserved for scale-free feature modeling only.

---

## 3. Fail-Closed Risk Policy (Capital Preservation Over Optimism)

- **Default Position is Cash:** In trading infrastructure, missing data or unmeasured edge is an error state, not an invitation to trade.
- **No Optimistic Fallbacks:** If `calibrated_params.json` is missing, unreadable, or lacks an empirical key, functions like `get_calibrated_strategy_edge()` return `None`. They must **never** silently fall back to synthetic winning defaults (e.g., `win_rate: 0.70`, `profit_factor: 2.0`, `net_ev: ₹800`).
- **Deterministic Veto Flow:**
  1. Missing calibration $\to$ Strategy maps `None` to `win_rate = 0.0`.
  2. `RuleGatekeeper.validate()` evaluates proposal against `EDGE_HURDLE` (`min_win_rate = 0.55`) and `ECONOMIC_HURDLE`.
  3. `EDGE_HURDLE` fails $\to$ Immediate veto.
  4. `ComparativeAuditEngine` eliminates unverified candidates and outputs **`TIER 0: NO TRADE`**.

---

## 4. Intraday Validation Boundaries (Daily Bhavcopy Limits)

- **Single Bar Reality:** NSE FO Bhavcopy contains exactly one EOD summary bar per contract per session (`open, high, low, close, volume, open_interest`).
- **Timing Windows are Unmeasured:** Daily Bhavcopy cannot determine whether a trade entered at 09:35 vs 10:15 had higher expectancy. Borrowing day-of-week Bhavcopy return statistics and labeling them as 45-minute intraday execution windows is cosmetic theater.
- **Status Classification:**
  - **`HIGH_RISK_AVOID` (Operational Policies):**
    - `09:15 - 09:45`: 30-minute Opening Range formation noise.
    - `11:15 - 12:45`: European handoff gap & midday low-volume lull.
    - `14:45 - 15:30`: 0DTE Expiry gamma explosion & square-off squeeze.
    - *These are hard risk policies, not backtested statistics (`trades = 0, win_rate = 0.0`).*
  - **`UNMEASURED` (Execution Windows):**
    - Windows between `09:45` and `14:45` are classified as `UNMEASURED` (`trades = 0, win_rate = None, profit_factor = None, avg_net_ev = None`).
    - Intraday timing claims remain blocked until true 1-min or 5-min tick data feeds are integrated.
