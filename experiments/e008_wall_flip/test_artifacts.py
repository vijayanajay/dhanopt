"""Integrity self-check for the e008 wall dataset — the FINAL verdict in
flip_signal.json is only as good as these artifacts, so verify they parse,
that the session set is complete (576), and that every file still matches
the walls_576.tar.gz snapshot byte-for-byte. Skips cleanly on a fresh
checkout without the artifacts.

    python -m unittest experiments.e008_wall_flip.test_artifacts
"""
from __future__ import annotations

import json
import tarfile
import unittest
from pathlib import Path

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"
WALLS_DIR = ARTIFACTS / "walls"
ARCHIVE = ARTIFACTS / "walls_576.tar.gz"
EXPECTED_SESSIONS = 576  # the dte<=1 universe; the dataset contract


@unittest.skipUnless(WALLS_DIR.is_dir() and ARCHIVE.is_file(),
                     "e008 wall artifacts not present (fresh checkout)")
class TestWallArtifactIntegrity(unittest.TestCase):
    def test_all_jsons_parse_and_set_is_complete(self):
        files = sorted(WALLS_DIR.glob("*.json"))
        self.assertEqual(len(files), EXPECTED_SESSIONS)
        for f in files:
            entry = json.loads(f.read_text())
            self.assertEqual(entry.get("status"), "OK", f.name)
            self.assertIn("bars", entry, f.name)
            self.assertIn("date", entry, f.name)

    def test_each_json_matches_the_archive_byte_for_byte(self):
        with tarfile.open(ARCHIVE, "r:gz") as tar:
            members = {m.name: m for m in tar.getmembers() if m.isfile()}
            disk = {f"walls/{f.name}": f for f in WALLS_DIR.glob("*.json")}
            self.assertEqual(set(members), set(disk),
                             "archive members and walls/ contents disagree")
            for name, f in sorted(disk.items()):
                archived = tar.extractfile(members[name])
                self.assertIsNotNone(archived, name)
                self.assertEqual(archived.read(), f.read_bytes(),
                                 f"{name} diverged from the snapshot")


if __name__ == "__main__":
    unittest.main()
