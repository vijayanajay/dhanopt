"""E002: t-1 feature engineering for the regime models.

Every feature row is what you could compute before 09:15 on day t —
i.e. built ONLY from rows with date < t (shift(1) discipline), then joined to
day-t labels (the outcomes the models must predict).

Self-leakage guard: test_feature_rows_are_strictly_shifted pins a scenario where
an extreme day-t value is invisible to the day-t feature row.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from core.feeds.bhavcopy import parse_date

FEATURE_COLUMNS: List[str] = [
    "fut_prev_ret",           # t-1 open->close %
    "fut_prev_range_pct",     # t-1 high-low range as % of open
    "fut_prev_gap_pct",      # t-1 gap: open vs prior close (at build time: t-2 close)
    "gap_open_pct",           # day-t open vs t-1 close — KNOWN at 09:15 before any entry
    "mom5",                   # 5d momentum ending t-1 (close/close-5 - 1)
    "mom10",                  # 10d momentum ending t-1
    "range5_mean_pct",        # mean daily range % over 5d ending t-1
    "pcr_t1",                 # t-1 PCR (put OI / call OI)
    "pcr_t2",                 # t-2 PCR (change feature denominator)
    "pcr_chg",                # pcr_t1 - pcr_t2
    "delta_oi_skew",          # t-1 (PE ΔOI - CE ΔOI) / total OI
    "straddle_pct",           # t-1 ATM straddle close / futures close (IV proxy)
    "straddle_pct_chg",       # 1-day change in straddle_pct
    "wall_call_dist_pct",     # t-1 call wall distance from futures close (%)
    "wall_put_dist_pct",      # t-1 put wall distance from futures close (%)
    "dow",                    # weekday 0-4 of day t (known in advance)
]

LABELS_NAME = "labels_daily.csv"


def load_labels(experiment_root: Path) -> pd.DataFrame:
    """Loads e001's labels_daily.csv and normalizes dates."""
    path = experiment_root / "e001_leakfree_replay" / "artifacts" / LABELS_NAME
    if not path.exists():
        raise FileNotFoundError(f"Run e001 first; missing {path}")
    df = pd.read_csv(path, parse_dates=["date"])
    return df


def build_feature_rows(historical_dir: Path, limit: Optional[int] = None) -> pd.DataFrame:
    """Builds one feature row per trade day, strictly from prior-day information.

    Pipeline: per-day raw stats -> strict shift(1) -> derived features -> attach day-t label targets.
    """
    files = sorted(historical_dir.glob("**/*.parquet"))
    if limit:
        files = files[-limit:]

    rows: List[Dict] = []
    for f in files:
        try:
            df = pd.read_parquet(f)
        except Exception:
            continue
        nifty = df[df["symbol"] == "NIFTY"]
        if nifty.empty:
            continue

        fut = nifty[nifty["instrument"].isin(["FUTIDX", "IDF"])]
        if fut.empty:
            continue
        f = fut.iloc[0]
        td = None
        for cand in (f["trade_date"], str(f["trade_date"]).strip()):
            try:
                td = parse_date(cand)
                break
            except Exception:
                continue
        if td is None:
            continue
        if f["open"] <= 0 or f["close"] <= 0:
            continue

        opts = nifty[nifty["instrument"].isin(["OPTIDX", "IDO"])]
        expiries = []
        for e in opts["expiry"].unique():
            try:
                expiries.append((parse_date(str(e).strip()), str(e).strip()))
            except Exception:
                continue
        if expiries:
            expiries.sort()
            chain = opts[opts["expiry"] == expiries[0][1]]
        else:
            chain = opts.iloc[0:0]

        pe = chain[chain["option_type"] == "PE"]
        ce = chain[chain["option_type"] == "CE"]

        pe_oi = float(pe["open_interest"].sum()) if not pe.empty else 0.0
        ce_oi = float(ce["open_interest"].sum()) if not ce.empty else 0.0
        pcr = pe_oi / ce_oi if ce_oi > 0 else np.nan

        oi_total = pe_oi + ce_oi
        doi_pe = float(pe["change_in_oi"].sum()) if not pe.empty else 0.0
        doi_ce = float(ce["change_in_oi"].sum()) if not ce.empty else 0.0
        skew = (doi_pe - doi_ce) / oi_total if oi_total > 0 else np.nan

        # ATM straddle as IV proxy: nearest strikes to futures close, mid-quote from close.
        atm = round(float(f["close"]) / 50.0) * 50.0
        atm_ce = ce[ce["strike"] == atm]
        atm_pe = pe[pe["strike"] == atm]
        if not atm_ce.empty and not atm_pe.empty:
            straddle = float(atm_ce.iloc[0]["close"]) + float(atm_pe.iloc[0]["close"])
            straddle_pct = straddle / float(f["close"]) * 100.0
        else:
            straddle_pct = np.nan

        wall_call = float(ce.loc[ce["open_interest"].idxmax(), "strike"]) if not ce.empty else np.nan
        wall_put = float(pe.loc[pe["open_interest"].idxmax(), "strike"]) if not pe.empty else np.nan

        rows.append({
            "date": td,
            "fut_open": float(f["open"]),
            "fut_close": float(f["close"]),
            "fut_high": float(f["high"]),
            "fut_low": float(f["low"]),
            "pcr_raw": pcr,
            "skew_raw": skew,
            "straddle_pct_raw": straddle_pct,
            "wall_call_raw": wall_call,
            "wall_put_raw": wall_put,
        })

    raw = pd.DataFrame(rows)
    raw["date"] = pd.to_datetime(raw["date"])
    raw = raw.sort_values("date").reset_index(drop=True)

    # ---- strict t-1 shift: every raw column becomes "yesterday's value" ----
    shifted = raw[[
        "fut_open", "fut_close", "fut_high", "fut_low",
        "pcr_raw", "skew_raw", "straddle_pct_raw", "wall_call_raw", "wall_put_raw",
    ]].shift(1)
    shifted.columns = [
        "prev_open", "prev_close", "prev_high", "prev_low",
        "pcr_t1", "delta_oi_skew", "straddle_pct", "wall_call_t1", "wall_put_t1",
    ]
    out = pd.concat([raw[["date"]], shifted], axis=1)

    # t-2 PCR for the change feature
    out["pcr_t2"] = raw["pcr_raw"].shift(2)

    # ---- derived features (all functions of the shifted frame) ----
    o, c, h, l = out["prev_open"], out["prev_close"], out["prev_high"], out["prev_low"]
    out["fut_prev_ret"] = (c - o) / o * 100.0
    out["fut_prev_range_pct"] = (h - l) / o * 100.0
    out["fut_prev_gap_pct"] = (o - c.shift(1)) / c.shift(1) * 100.0

    closes = out["prev_close"]
    out["mom5"] = (closes / closes.shift(5) - 1.0) * 100.0
    out["mom10"] = (closes / closes.shift(10) - 1.0) * 100.0
    out["range5_mean_pct"] = out["fut_prev_range_pct"].rolling(5).mean()

    out["pcr_chg"] = out["pcr_t1"] - out["pcr_t2"]

    out["straddle_pct_chg"] = out["straddle_pct"].diff()

    out["wall_call_dist_pct"] = (out["wall_call_t1"] - c) / c * 100.0
    out["wall_put_dist_pct"] = (out["wall_put_t1"] - c) / c * 100.0

    out["dow"] = out["date"].dt.weekday

    # Day-t OPEN (known at 09:15, before any intraday information) vs t-1 close.
    out["gap_open_pct"] = (raw["fut_open"].to_numpy() - out["prev_close"].to_numpy()) / out["prev_close"].to_numpy() * 100.0

    features = out[["date"] + FEATURE_COLUMNS].copy()
    return features


def attach_labels(features: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Pivots e001's per-archetype rows into per-day win flags and net PnL columns."""
    wins = labels.pivot_table(index="date", columns="archetype", values="win", aggfunc="first")
    pnls = labels.pivot_table(index="date", columns="archetype", values="net_pnl", aggfunc="first")
    sim = labels.pivot_table(index="date", columns="archetype", values="simulated", aggfunc="first")

    wins.columns = [f"{c.replace(' ', '_')}_won" for c in wins.columns]
    pnls.columns = [f"{c.replace(' ', '_')}_net" for c in pnls.columns]
    sim.columns = [f"{c.replace(' ', '_')}_sim" for c in sim.columns]

    out = features.merge(wins, left_on="date", right_index=True, how="left")
    out = out.merge(pnls, left_on="date", right_index=True, how="left")
    out = out.merge(sim, left_on="date", right_index=True, how="left")
    for col in [c for c in out.columns if c.endswith("_won")]:
        out[col] = out[col].astype("boolean")
    for col in [c for c in out.columns if c.endswith("_sim")]:
        out[col] = out[col].astype("boolean")
    return out


def build_dataset(historical_dir: Path, experiment_root: Path, limit: Optional[int] = None) -> pd.DataFrame:
    """Full dataset: features (strict t-1) + day-t labels. Cached under artifacts/."""
    cache = experiment_root / "e002_regime_models" / "artifacts" / "dataset_cache.parquet"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and limit is None:
        return pd.read_parquet(cache)
    labels = load_labels(experiment_root)
    features = build_feature_rows(historical_dir, limit=limit)
    ds = attach_labels(features, labels)
    if limit is None:
        ds.to_parquet(cache, index=False)
    return ds
