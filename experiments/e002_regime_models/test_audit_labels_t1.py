"""Self-check: the t-1-label leak audit's committed verdict — the label mapping is
NA-free (the crash that ended the first run), and the headline numbers stay pinned."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
T1 = HERE / "artifacts_t1labels"


class TestT1LabelAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.labels = pd.read_csv(T1 / "condor_labels_t1.csv")
        with open(T1 / "gating_sim.json") as f:
            cls.gate = json.load(f)
        with open(HERE / "artifacts_dte" / "gating_sim.json") as f:
            cls.frozen_gate = json.load(f)

    def test_labels_have_no_na_boolean_columns(self):
        # The first run crashed on `boolean value of NA is ambiguous` in gating;
        # the mapping must produce concrete booleans everywhere.
        self.assertFalse(self.labels["simulated"].isna().any())
        self.assertFalse(self.labels["win"].isna().any())
        self.assertFalse(self.labels["net_pnl"].isna().any())

    def test_t1_condor_book_is_negative(self):
        sim = self.labels[self.labels["simulated"]]
        self.assertGreater(len(sim), 1200)
        self.assertLess(sim["net_pnl"].sum(), 0)  # frozen day-t-wall book: +469,637

    def test_ml_policy_flips_sign_without_the_leak(self):
        frozen = self.frozen_gate["ml_logistic"]["net_total"]
        t1 = self.gate["ml_logistic"]["net_total"]
        self.assertGreater(frozen, 700_000)
        self.assertLess(t1, 0)


if __name__ == "__main__":
    unittest.main()
