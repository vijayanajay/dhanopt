"""Invariant: a module declared to use day-t decision information must never be
flagged live-replicable, and every experiment that produces PnL must have a row."""
from __future__ import annotations

import unittest
from pathlib import Path

from experiments.common.leak_registry import REGISTRY

HERE = Path(__file__).resolve().parent
EXPERIMENTS = HERE.parent

# Modules known to produce (or have produced) actionable net-PnL numbers.
EXPECTED_COVERAGE = [
    "e001_leakfree_replay/replay.py",
    "e002_regime_models/features.py",
    "e002_regime_models/walkforward_dte.py",
    "e003_meta_labeling/meta_labeling.py",
    "e004_intraday_replay/replay_intraday.py",
    "e005_theta_condor/replay_theta.py",
    "e005_theta_condor/breach_spread.py",
    "e005_theta_condor/paper_trade.py",
    "e006_compound_sim/compound_sim.py",
    "e007_open_oi/build_book.py",
]

VALID_INFO = {"t-1", "day-t", "none"}


class TestLeakRegistry(unittest.TestCase):
    def test_invariant_day_t_implies_not_live(self):
        for row in REGISTRY:
            if row["info"] == "day-t":
                self.assertFalse(row["live"],
                                 f"{row['module']}: day-t information declared live-replicable — "
                                 f"this is exactly how the +940,697 happened")

    def test_info_sets_are_valid_and_nonempty(self):
        for row in REGISTRY:
            self.assertIn(row["info"], VALID_INFO, row["module"])
            self.assertIn("note", row) and self.assertTrue(row["note"].strip(), row["module"])

    def test_no_duplicate_modules(self):
        mods = [r["module"] for r in REGISTRY]
        self.assertEqual(len(mods), len(set(mods)))

    def test_registered_modules_exist_on_disk(self):
        for row in REGISTRY:
            self.assertTrue((EXPERIMENTS / row["module"].split("experiments/", 1)[1]).exists(),
                            f"registry row points at a missing file: {row['module']}")

    def test_expected_pnl_modules_are_covered(self):
        covered = {r["module"] for r in REGISTRY}
        for rel in EXPECTED_COVERAGE:
            self.assertIn(f"experiments/{rel}", covered),
            # (a missing row is a failure to declare, which is itself the failure mode)

    def test_registered_paths_use_experiments_prefix(self):
        for row in REGISTRY:
            self.assertTrue(row["module"].startswith("experiments/"), row["module"])


if __name__ == "__main__":
    unittest.main()
