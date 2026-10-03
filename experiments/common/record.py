"""The canonical experiment manifest, derived from disk.

Four places restate which experiments exist and what each concluded:
actionplan.md's void-and-dead ledger (§1.1) and execution schedule (§4), and
RETROSPECTIVE.md's complete record (§6) and status list (§7). Each drifts on
its own clock — §6 claimed to be "every experiment, its honest verdict" while
e030 sat there with a real verdict and no row, and the prose count of
experiments was wrong in both directions.

This module answers "what is actually on disk" in one place, so a check can
compare the documents against it rather than against a number somebody typed.
It is deliberately read-only and derived: nothing here is hand-maintained, so
it cannot drift from the thing it describes.

    python -m experiments.common.record     # print the canonical table

Rung 3 of the reuse ladder: the filesystem already knows the answer.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPERIMENTS = ROOT / "experiments"

DIR_RE = re.compile(r"^e(\d{3})_([a-z0-9_]+)$")


@dataclass(frozen=True)
class Experiment:
    """One experiment directory. Every field is read, never remembered."""

    id: str            # "e030"
    number: int        # 30
    slug: str          # "calendar_credit"
    path: Path
    has_prereg: bool
    verdict: str | None  # artifacts/verdict.json's `verdict`, if the run wrote one

    @property
    def has_verdict(self) -> bool:
        return self.verdict is not None


def experiments() -> list[Experiment]:
    """Every `experiments/eNNN_slug/` on disk, in id order."""
    out: list[Experiment] = []
    for p in sorted(EXPERIMENTS.iterdir()):
        if not p.is_dir():
            continue
        m = DIR_RE.match(p.name)
        if not m:
            continue
        number, slug = int(m.group(1)), m.group(2)
        verdict = None
        verdict_file = p / "artifacts" / "verdict.json"
        if verdict_file.exists():
            try:
                doc = json.loads(verdict_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise AssertionError(f"{verdict_file} is not valid JSON: {exc}") from exc
            # The artifact must name itself. A copy-pasted verdict under the
            # wrong directory is a silent false claim about what ran.
            claimed = doc.get("experiment")
            if claimed is not None and claimed != p.name:
                raise AssertionError(
                    f"{verdict_file} claims experiment {claimed!r} but lives in "
                    f"{p.name!r}")
            verdict = doc.get("verdict")
        out.append(Experiment(
            # zero-padded: the id is the record's key and must match the
            # directory's own eNNN prefix exactly, or it cannot be joined to
            # the documents' rows.
            id=f"e{number:03d}", number=number, slug=slug, path=p,
            has_prereg=(p / "PREREG.md").exists(), verdict=verdict))
    out.sort(key=lambda e: e.number)
    return out


def ids() -> set[str]:
    return {e.id for e in experiments()}


def table() -> str:
    """The canonical markdown table. Machine-derived; never hand-edit a copy."""
    rows = ["| # | Slug | PREREG | Verdict artifact | Verdict |",
            "|---|---|---|---|---|"]
    for e in experiments():
        v = (e.verdict or "—").replace("|", "\\|")
        rows.append(f"| {e.id} | {e.slug} | {'Y' if e.has_prereg else '—'} | "
                    f"{'Y' if e.has_verdict else '—'} | {v} |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(table())
