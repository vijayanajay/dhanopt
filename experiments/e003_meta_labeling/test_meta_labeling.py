"""E003 self-checks: rule-trade extraction, matched-count policy comparison.

Run: python -m unittest experiments.e003_meta_labeling.test_meta_labeling -v
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from experiments.e002_regime_models.walkforward import (
    ARCH_KEYS,
    PNL_COLUMNS,
    RULE_TO_ARCH,
    TARGETS,
)
from experiments.e003_meta_labeling.meta_labeling import (
    compare_policies,
    rule_trades,
)


def _ds(n: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    ds = pd.DataFrame({
        "date": pd.date_range("2023-01-02", periods=n),
        "rule_signal": ["UP", "FLAT", "NONE", "DOWN", "FLAT"] * (n // 5),
        "dow": [0] * n,
    })
    for arch in ARCH_KEYS:
        ds[arch.replace(" ", "_") + "_sim"] = True
        ds[TARGETS[arch]] = rng.random(n) > 0.5
        ds[PNL_COLUMNS[arch]] = rng.normal(0, 400, n)
    # tiny deterministic feature so LGBM can fit
    for c in ("fut_prev_ret", "pcr_t1", "straddle_pct", "dow"):
        if c not in ds.columns:
            ds[c] = rng.normal(0, 1, n)
    return ds


class TestRuleTrades(unittest.TestCase):
    def test_rule_trades_follow_rule_mapping_and_exclude_none(self):
        ds = _ds()
        trades = rule_trades(ds)
        self.assertEqual(len(trades), 48)  # 60 - 12 NONE days
        self.assertTrue((trades["rule_signal"] != "NONE").all())
        self.assertTrue(all(RULE_TO_ARCH[s] == a for s, a in zip(trades["rule_signal"], trades["archetype"])))


class TestPolicyComparison(unittest.TestCase):
    def test_matched_counts_and_no_overlap(self):
        rng = np.random.default_rng(5)
        n = 40
        meta = pd.DataFrame({
            "date": pd.date_range("2023-01-02", periods=n),
            "archetype": ["Iron Condor"] * n,
            "pnl": rng.normal(100, 300, n),
            "p_meta": rng.random(n),
        })
        e002 = pd.DataFrame({
            "date": pd.date_range("2023-01-02", periods=n),
            "rule_signal": ["FLAT"] * n,
        })
        for arch in ARCH_KEYS:
            e002[arch.replace(" ", "_") + "_sim"] = True
            e002[PNL_COLUMNS[arch]] = rng.normal(0, 300, n)
            e002[f"lgbm__{arch}"] = rng.random(n)
        res = compare_policies(meta, e002)
        self.assertEqual(res["baseline_rule"]["n"], res["meta_filtered"]["n"])
        self.assertEqual(res["baseline_rule"]["n"], res["e002_style_selector"]["n"])
        self.assertEqual(res["baseline_rule"]["n"], n)  # every rule trade in baseline


if __name__ == "__main__":
    unittest.main()
