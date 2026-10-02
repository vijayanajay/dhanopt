"""Shared Black-Scholes pricing & greeks — single source of truth for all experiments.

Exact ports of the helpers that previously lived as private functions in
experiments/e011_vrp_delta_hedge/replay_vrp.py (identical numerics, including the
max(iv, 0.01) and max(t, 1e-4) floors), so every frozen artifact remains bit-for-bit
reproducible. New code imports from here; nothing re-derives these formulas.
"""

from __future__ import annotations

import math


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def d1(spot: float, strike: float, iv: float, t_years: float) -> float:
    vol = max(iv, 0.01)
    t = max(t_years, 0.0001)
    denom = vol * math.sqrt(t)
    return (math.log(spot / strike) + 0.5 * vol * vol * t) / denom


def bs_call(spot: float, strike: float, iv: float, t_years: float) -> float:
    t = max(t_years, 0.0001)
    vol = max(iv, 0.01)
    denom = vol * math.sqrt(t)
    d1_ = (math.log(spot / strike) + 0.5 * vol * vol * t) / denom
    d2 = d1_ - denom
    return spot * norm_cdf(d1_) - strike * norm_cdf(d2)


def bs_put(spot: float, strike: float, iv: float, t_years: float) -> float:
    t = max(t_years, 0.0001)
    vol = max(iv, 0.01)
    denom = vol * math.sqrt(t)
    d1_ = (math.log(spot / strike) + 0.5 * vol * vol * t) / denom
    d2 = d1_ - denom
    return strike * (1.0 - norm_cdf(d2)) - spot * (1.0 - norm_cdf(d1_))


def delta_ce(spot: float, strike: float, iv: float, t_years: float) -> float:
    return norm_cdf(d1(spot, strike, iv, t_years))


def delta_pe(spot: float, strike: float, iv: float, t_years: float) -> float:
    return norm_cdf(d1(spot, strike, iv, t_years)) - 1.0
