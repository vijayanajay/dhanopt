"""NIFTY lot-size era table.

Verified against NSE circulars (2026-09-29; supersedes the earlier flat-25 table,
which mis-scaled 2021→Apr-2024 experiment PnL by 2-3x):
- Pre-Jul-2021: 75 (FAOP47854: 75→50 with the July-2021 weekly series)
- Jul 2021 → Apr 25, 2024: 50 (periodic review; core config pins Circular 25/2021)
- Apr 26, 2024 → Nov 19, 2024: 25 (Apr-2024 periodic review, Circular 45/2024)
- Nov 20, 2024 → Dec 29, 2025: 75 (SEBI index-derivatives framework, FAOP67372)
- Dec 30, 2025 → present: 65 (FAOP70616: new series from Oct 28, 2025 EOD;
  weeklies enter the 65-lot era with the Jan-2026 expiry cycle)

# ponytail: boundary approximation — on transition days the expiring weekly keeps the
# old lot while new series use the new one. We use the new-lot start date as the split.
# Upgrade path: parse per-contract lot from bhavcopy when a day-level split matters.
"""

from __future__ import annotations

from datetime import date

BASE_LOT = 75

LOT_ERAS: list[tuple[date, int]] = [
    (date(2021, 7, 1), 50),
    (date(2024, 4, 26), 25),
    (date(2024, 11, 20), 75),
    (date(2025, 12, 30), 65),
]


def lot_for_date(d: date) -> int:
    lot = BASE_LOT
    for start, size in LOT_ERAS:
        if d >= start:
            lot = size
    return lot
