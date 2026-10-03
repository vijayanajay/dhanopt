"""The record must cover every experiment on disk — and nothing else.

RETROSPECTIVE.md §6 claims to be "the complete record — every experiment, its
honest verdict". It drifted: e030 had a real, verified verdict and no row, and
the prose count of experiments was wrong in both directions.

Invariant §5.13 says a data claim is a testable assertion. This applies that to
the record itself. Two failures this catches:

  * an experiment that ran and produced artifacts but has no verdict row —
    the e030 gap, invisible until someone reads the table against `ls`;
  * a row for an experiment that does not exist — e021–e025 are Phase 7
    roadmap IDs that never started, and five empty rows would imply they did.

Cheap by construction: no data store, no fixtures, no network. It reads one
markdown file and one directory listing.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
RETROSPECTIVE = ROOT / "RETROSPECTIVE.md"

DIR_RE = re.compile(r"^e\d{3}_[a-z0-9_]+$")
ROW_RE = re.compile(r"^\| \*{0,2}(e\d{3})\*{0,2} \|", re.M)
COUNT_RE = re.compile(r"(\d+) of them at this writing")


def experiment_dirs() -> set[str]:
    """Experiment directories that exist on disk, by bare id (e030, e031, …)."""
    out = set()
    for p in EXPERIMENTS.iterdir():
        if p.is_dir() and DIR_RE.match(p.name):
            out.add(p.name.split("_", 1)[0])
    return out


def recorded_ids() -> set[str]:
    """Ids with a row in §6's table — the section's prose is excluded."""
    txt = RETROSPECTIVE.read_text(encoding="utf-8")
    try:
        section = txt.split("## 6. The complete record", 1)[1].split("## 7.", 1)[0]
    except IndexError as exc:  # pragma: no cover - structural break, not drift
        raise AssertionError("RETROSPECTIVE.md has no §6 or §7 heading") from exc
    return set(ROW_RE.findall(section))


class TestRecordCoversEveryExperiment(unittest.TestCase):
    def test_every_experiment_directory_has_a_verdict_row(self):
        """The e030 gap, as a failing check rather than an omission."""
        on_disk = experiment_dirs()
        self.assertTrue(
            on_disk,
            "experiment_dirs() found nothing — the scan is broken, not the record")
        missing = sorted(on_disk - recorded_ids())
        self.assertEqual(
            missing, [],
            f"experiments on disk with no §6 verdict row: {missing} — "
            "add a row or state why it has none")

    def test_no_verdict_row_for_an_experiment_that_does_not_exist(self):
        """Guards the opposite error: inventing rows for tests never run."""
        recorded = recorded_ids()
        self.assertTrue(
            recorded,
            "§6 yielded no verdict rows — the section parse is broken, not the record")
        ghosts = sorted(recorded - experiment_dirs())
        self.assertEqual(
            ghosts, [],
            f"§6 rows with no experiments/ directory: {ghosts} — "
            "a row implies the experiment ran")

    def test_the_stated_count_matches_the_directory_set(self):
        """The prose number is a claim about disk; pin it to disk."""
        txt = RETROSPECTIVE.read_text(encoding="utf-8")
        m = COUNT_RE.search(txt)
        self.assertIsNotNone(
            m, "§6 no longer states 'N of them at this writing'; "
               "either restore the checkable form or update this test")
        stated = int(m.group(1))
        actual = len(experiment_dirs())
        self.assertEqual(
            stated, actual,
            f"§6 says {stated} experiments, disk has {actual}")

    def test_the_struck_count_is_gone(self):
        """'Twenty-eight' was asserted in two places and was wrong."""
        txt = RETROSPECTIVE.read_text(encoding="utf-8")
        self.assertNotIn("twenty-eight experiments", txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
