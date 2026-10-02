"""E019 — Systematic cash momentum engine.

Two legs, one cost model, one signal family:

  * cross-sectional leg — rank the liquid universe by 12-1 month momentum,
    hold the top N equal-weight. This is the anomaly test.
  * single-asset (Nifty ETF) leg — the same idea on one instrument, which is
    pure time-series momentum and mostly a beta claim. Reported, not gated.

The question the experiment actually answers is the FRICTION DECAY BOUNDARY:
the same signal, the same universe, the same costs, rebalanced at two
frequencies. Whatever edge exists must be a function of how often you pay to
harvest it.

INFORMATION SET (PREREG §2): signals are formed from closes through t-1 only;
all fills are at the t close. A rank built on t-1's closes cannot be filled at
t-1's close.

SURVIVORSHIP (PREREG §2): the universe is the union of every symbol that
trades in the bhavcopy on any day of the sample, filtered by POINT-IN-TIME
liquidity (trailing 252-session median turnover ending t-1). No current-index
membership list is used anywhere. Names that stop trading stop qualifying.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from dataclasses import dataclass

from experiments.e019_momentum.download_cash import CASH_DIR, partition_path

ARTIFACTS = HERE / "artifacts"

# ------------------------------------------------------------- parameters --

LOOKBACK = 252          # ~12 months of trading days for the momentum window
SKIP = 21               # 12-1 momentum: skip the most recent month
TOP_N = 20              # equal-weight basket size
MIN_TURNOVER = 5e6      # point-in-time median daily traded value (Rs 5 crore)
SPLIT_THRESHOLD = 0.20  # |1-day return| beyond this is a split/bonus candidate
# Clean bonus/split ratios within 2pp. 1:1 bonus = -50%, 1:2 = -33.3%, 1:3 = -25%,
# 1:4 = -20%, 1:5 = -16.7% (below the threshold), plus reverse-split up-sides.
CLEAN_RATIOS = (0.5, 1 / 3, 0.25, 0.2, 0.75, 0.667, 0.8)
CAPITAL = 200_000.0
YEARS = 5.7
REBALANCES = {"monthly": 21, "daily": 1}

ETF_CANDIDATES = ("NIFTYBEES", "JUNIORBEES", "NIFTYETF", "NIFTYBEES")

COSTS_NOTE = {
    "stt": "0.1% on BOTH buy and sell (delivery, post-Oct-2024)",
    "exchange": "0.00297% NSE equity",
    "sebi": "0.00001% (Rs 10/cr)",
    "stamp_duty": "0.003% on BUY only",
    "gst": "18% on (brokerage + exchange + sebi)",
    "brokerage": "flat Rs 20 per order",
    "slippage": "15 bps per side",
}


# ---------------------------------------------------------- the cost model --

class Costs:
    """Indian retail delivery-equity cost stack, per side, as fractions.

    STT is 0.1% on BOTH buy and sell for delivery (post Oct 2024), which is
    what makes high-turnover strategies expensive here. Brokerage is a flat
    Rs 20/order, so it is the component that punishes small tickets hardest.
    """

    def __init__(
        self,
        stt: float = 0.001,
        exchange: float = 0.0000297,
        sebi: float = 0.0000001,
        stamp_buy: float = 0.00003,
        gst: float = 0.18,
        brokerage: float = 20.0,
        slippage_bps: float = 0.0015,
    ):
        self.stt, self.exchange, self.sebi = stt, exchange, sebi
        self.stamp_buy, self.gst = stamp_buy, gst
        self.brokerage, self.slippage_bps = brokerage, slippage_bps

    def per_side(self, notional: float, is_buy: bool) -> float:
        n = notional
        charges = (
            self.brokerage
            + self.stt * n          # STT 0.1% both sides for delivery
            + self.exchange * n
            + self.sebi * n
            + (self.stamp_buy * n if is_buy else 0.0)
        )
        return charges * (1 + self.gst) + n * self.slippage_bps

    def round_trip(self, notional: float) -> float:
        return self.per_side(notional, True) + self.per_side(notional, False)


def breakeven_holding_days(costs: Costs, expected_daily_alpha: float) -> float:
    """How many days an edge must persist to cover one round trip."""
    rt = costs.round_trip(1.0)
    return rt / expected_daily_alpha if expected_daily_alpha > 0 else math.inf


# ------------------------------------------------------------- price store --

def load_panel(out_dir: Path = CASH_DIR) -> pd.DataFrame:
    """Long panel -> wide close/turnover matrices indexed by date."""
    files = sorted(out_dir.glob("**/cm_*.parquet"))
    if not files:
        raise RuntimeError("no cash bhavcopy partitions on disk; run download_cash first")
    frames = [pd.read_parquet(f, columns=["symbol", "close", "volume", "turnover",
                                          "type", "trade_date"])
              for f in files]
    df = pd.concat(frames, ignore_index=True)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    # the archive mixes numeric and string junk in the money columns; coerce once
    for c in ("close", "volume", "turnover"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # a symbol can appear twice in a day under two series; keep the EQ line
    df = df[df["type"] == "STK"] if (df["type"] == "STK").any() else df
    df = df.drop_duplicates(subset=["symbol", "trade_date"], keep="first")
    close = df.pivot(index="trade_date", columns="symbol", values="close").sort_index()
    turn = df.pivot(index="trade_date", columns="symbol", values="turnover").sort_index()
    types = df.pivot_table(index="trade_date", columns="symbol", values="type",
                           aggfunc="first")
    return close.astype(float), turn.astype(float), types


def corporate_action_adjust(close: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
    """Back-adjust the price series for splits and bonuses.

    The bhavcopy carries RAW (unadjusted) closes, so a 1:1 bonus prints as a
    -50% day — which a momentum screen reads as a catastrophic loss, and which
    drops the name from the basket at exactly the moment it might qualify. That
    is a bias against exactly the large caps that lead the momentum factor.

    A drop whose ratio sits on a clean bonus/split value (1:1, 1:2, 1:3, 1:4,
    1:5, 2:1 and the reciprocal) within 2 percentage points is treated as a
    corporate action: the history BEFORE the event is scaled by (1 - ratio) so
    the series is continuous. Everything else is left alone — a real 40% crash
    must stay a real 40% crash.

    Returns (adjusted_close, stats) so the count is reported, not absorbed.
    """
    rets = close.pct_change(fill_method=None)   # NEVER forward-fill a sparse panel
    n_actions = 0
    affected: Dict[str, int] = {}
    adj = close.copy()

    for col in close.columns:
        r = rets[col]
        hits = r[(r < -SPLIT_THRESHOLD)].dropna()
        if hits.empty:
            continue
        for idx in hits.index:
            # ratio = 1 + r. A -49.8% day gives 1 + (-0.498) = 0.502, the
            # fraction of the old price still represented after a 1:1 bonus.
            ratio = 1.0 + float(hits.loc[idx])         # 0.502 for a -49.8% day
            if not any(abs(ratio - t) < 0.02 for t in CLEAN_RATIOS):
                continue
            pos = close.index.get_loc(idx)
            if pos == 0:
                continue
            factor = 1.0 - ratio
            if factor <= 0:
                continue
            adj.iloc[:pos, adj.columns.get_loc(col)] *= factor
            n_actions += 1
            affected[col] = affected.get(col, 0) + 1

    stats = {
        "corporate_actions_adjusted": n_actions,
        "symbols_affected": len(affected),
        "top_affected": dict(sorted(affected.items(), key=lambda kv: -kv[1])[:10]),
    }
    return adj, stats


# ----------------------------------------------------------------- signals --

def precompute_liquidity(turn: pd.DataFrame) -> pd.DataFrame:
    """Trailing LOOKBACK-session median turnover, computed ONCE.

    point_in_time_universe() recomputed this median over a 252 x 6475 frame at
    every rebalance, which for the daily leg meant ~1,100 identical recomputes
    and a run that took hours. The rolling median is the same number, done once.

    Strictly backward-looking by construction: the value on row i uses only
    sessions [i-251 .. i].
    """
    return turn.rolling(LOOKBACK, min_periods=120).median()


def point_in_time_universe(turn: pd.DataFrame, as_of: int,
                           med: Optional[pd.DataFrame] = None) -> List[str]:
    """Symbols whose TRAILING 252-session median turnover is liquid as of `as_of`.

    Strictly backward-looking: uses sessions [as_of-251 .. as_of] and nothing
    after. A symbol with fewer than 120 observations in that window is not
    liquid enough to trade and is excluded.
    """
    if as_of < 1 or as_of >= len(turn):
        return []
    if med is None:
        hist = turn.iloc[max(0, as_of - LOOKBACK): as_of + 1]
        if len(hist) < 120:
            return []
        row = hist.median()
    else:
        row = med.iloc[as_of].dropna()
        if row.empty:
            return []
    ok = row[row >= MIN_TURNOVER].index
    return [s for s in ok if s in turn.columns]


def momentum_rank(close: pd.DataFrame, as_of: int, universe: List[str]) -> pd.Series:
    """12-1 momentum: return from t-1-252 to t-1-21. Strictly t-1."""
    end = as_of - SKIP
    start = end - LOOKBACK
    if start < 0 or end < 0:
        return pd.Series(dtype=float)
    px0 = close.iloc[start]
    px1 = close.iloc[end]
    both = [s for s in universe if s in px0.index and s in px1.index]
    if not both:
        return pd.Series(dtype=float)
    p0, p1 = px0[both].astype(float), px1[both].astype(float)
    valid = (p0 > 0) & (p1 > 0) & p0.notna() & p1.notna()
    r = (p1[valid] / p0[valid]) - 1.0
    return r.sort_values(ascending=False)


# ------------------------------------------------------------ backtesting --

def run_backtest(
    close: pd.DataFrame,
    turn: pd.DataFrame,
    rebal_every: int,
    top_n: int = TOP_N,
    costs: Optional[Costs] = None,
    cost_mult: float = 1.0,
    start_idx: Optional[int] = None,
    end_idx: Optional[int] = None,
    top_frac: Optional[float] = None,
    adv_cap_pct: Optional[float] = None,
) -> Tuple[pd.DataFrame, Dict]:
    """Equal-weight top-N cross-sectional momentum, rebalanced every N sessions.

    Signal is formed on session i-1's data; the basket is traded at session i's
    close; it earns session i+1's return until the next rebalance.
    """
    costs = costs or Costs()
    n = len(close)
    start = max(LOOKBACK + SKIP + 1, start_idx or 0)
    end = n - 1 if end_idx is None else min(n, end_idx)
    med = precompute_liquidity(turn)

    holdings: Dict[str, float] = {}     # symbol -> weight
    equity = 1.0
    rows: List[Dict] = []
    turnover_events = 0
    total_cost = 0.0
    cap_binding = 0
    cap_headroom: List[float] = []

    for i in range(start, end):
        # --- decide on data through i-1, trade at i's close
        if (i - start) % rebal_every == 0:
            uni = point_in_time_universe(turn, i - 1, med)
            rank = momentum_rank(close, i - 1, uni)
            # top-N by COUNT, or by FRACTION of the rankable universe (top decile)
            if top_frac:
                k = max(1, int(math.ceil(top_frac * len(rank))))
            else:
                k = top_n
            target = list(rank.index[:k]) if len(rank) >= min(k, 1) else []
            if not target:
                continue
            new_w = {s: 1.0 / len(target) for s in target}
            # ADV cap: a position may not exceed cap_pct of that name's own
            # point-in-time median daily turnover. At Rs 2L / ~150 names this is
            # ~40x headroom, so it does not bind — reported, never claimed.
            if adv_cap_pct:
                adv = med.iloc[i - 1] if i - 1 < len(med) else None
                if adv is not None:
                    for s in list(new_w):
                        a = adv.get(s)
                        pos_inr = new_w[s] * equity * CAPITAL
                        if a and not pd.isna(a) and a > 0:
                            cap_inr = adv_cap_pct * float(a)
                            cap_headroom.append(cap_inr / pos_inr if pos_inr > 0 else np.inf)
                            if pos_inr > cap_inr:
                                new_w[s] = cap_inr / (equity * CAPITAL)
                                cap_binding += 1
                    tot = sum(new_w.values())
                    if tot > 0:
                        new_w = {s: w / tot for s, w in new_w.items()}
            # one-way turnover = half the L1 distance between old and new weights
            syms = set(holdings) | set(new_w)
            traded_notional = sum(
                abs(new_w.get(s, 0.0) - holdings.get(s, 0.0)) for s in syms
            ) / 2.0
            c = traded_notional * equity * CAPITAL
            # charge the full cost stack on the traded notional, both sides
            fee = (costs.round_trip(c) * cost_mult if traded_notional > 0 else 0.0)
            equity -= fee / CAPITAL
            total_cost += fee
            holdings = new_w
            turnover_events += 1

        if not holdings:
            continue

        # --- earn session i+1's return on the basket held into it
        fwd = i + 1
        if fwd > end:
            break
        # close is (date x symbol), so a row Series is indexed by SYMBOL and
        # .get(symbol) is the correct lookup.
        r0, r1 = close.iloc[i], close.iloc[fwd]
        rets = []
        for s, w in holdings.items():
            a, b = r0.get(s), r1.get(s)
            if a is not None and b is not None:
                a, b = float(a), float(b)
                if a > 0 and b > 0:
                    rets.append(w * (b / a - 1.0))
        r = float(np.sum(rets)) if rets else 0.0
        if not rets:
            continue
        equity *= (1 + r)
        rows.append({
            "date": close.index[fwd], "return": r, "equity": equity,
            "n_holdings": len(holdings), "rebalance": (fwd - start) % rebal_every == 0,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df, {}
    df["peak"] = df["equity"].cummax()
    df["drawdown"] = df["equity"] / df["peak"] - 1.0
    rets = df["return"]
    n_periods = len(df)
    yrs = n_periods / 252.0
    metrics = {
        "rebalances": turnover_events,
        "periods": n_periods,
        "years": round(yrs, 2),
        "median_holdings": int(df["n_holdings"].median()),
        "min_holdings": int(df["n_holdings"].min()),
        "total_return": round(float(df["equity"].iloc[-1] - 1), 4),
        "cagr": round(float(df["equity"].iloc[-1] ** (1 / yrs) - 1), 4) if yrs > 0 else None,
        "sharpe": round(float(rets.mean() / rets.std() * math.sqrt(252)), 2) if rets.std() > 0 else None,
        "max_dd": round(float(df["drawdown"].min()), 4),
        "hit_rate": round(float((rets > 0).mean()), 4),
        "total_cost_inr": round(total_cost, 0),
        "avg_cost_per_rebal": round(total_cost / turnover_events, 0) if turnover_events else 0,
        "adv_cap_binding_positions": cap_binding,
        "adv_cap_median_headroom": round(float(np.median(cap_headroom)), 1) if cap_headroom else None,
    }
    return df, metrics


def run_etf_leg(close: pd.DataFrame, turn: pd.DataFrame, symbol: str,
                rebal_every: int, costs: Optional[Costs] = None) -> Tuple[Optional[pd.DataFrame], Dict]:
    """Time-series momentum on one ETF: hold while its own 12m return is +ve."""
    costs = costs or Costs()
    if symbol not in close.columns:
        return None, {"error": f"{symbol} not in price store"}
    px = close[symbol].dropna()
    if len(px) < LOOKBACK + SKIP + 2:
        return None, {"error": f"{symbol}: only {len(px)} sessions"}
    n = len(close)
    rows: List[Dict] = []
    in_market, total_cost = False, 0.0
    for i in range(max(LOOKBACK + SKIP + 1, 1), n - 1):
        mom = (close[symbol].iloc[i - SKIP] / close[symbol].iloc[i - SKIP - LOOKBACK]) - 1.0
        want = mom > 0
        if (i - (LOOKBACK + SKIP + 1)) % rebal_every == 0:
            if want != in_market:
                total_cost += costs.round_trip(CAPITAL) if not in_market else \
                    costs.per_side(CAPITAL, False)
                in_market = want
        if not in_market:
            continue
        a, b = close[symbol].iloc[i], close[symbol].iloc[i + 1]
        if a and b and not pd.isna(a) and not pd.isna(b) and a > 0:
            rows.append({"date": close.index[i + 1], "return": b / a - 1.0})
    df = pd.DataFrame(rows)
    if df.empty:
        return None, {"error": "no ETF sessions"}
    eq = (1 + df["return"]).cumprod()
    dd = eq / eq.cummax() - 1.0
    rets = df["return"]
    yrs = len(df) / 252.0
    return df, {
        "symbol": symbol, "sessions_in_market": len(df), "years": round(yrs, 2),
        "total_return": round(float(eq.iloc[-1] - 1), 4),
        "cagr": round(float(eq.iloc[-1] ** (1 / yrs) - 1), 4),
        "sharpe": round(float(rets.mean() / rets.std() * math.sqrt(252)), 2) if rets.std() > 0 else None,
        "max_dd": round(float(dd.min()), 4),
        "total_cost_inr": round(total_cost, 0),
    }
