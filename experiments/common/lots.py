"""NIFTY lot-size era table.

Verified against NSE circulars:
- FAOP67372 (Oct 2024): contracts introduced from Nov 20, 2024 carry lot 75 (was 25).
- FAOP70616 (Oct 3, 2025): revised to 65 effective Oct 28, 2025 EOD for new series;
  nearest-weekly contracts enter the 65-lot era with the Jan-2026 expiry cycle (~Dec 30, 2025).

# ponytail: boundary approximation — on transition days the expiring weekly keeps the
# old lot while new series use the new one. We use the new-lot start date as the split.
# Upgrade path: parse per-contract lot from bhavcopy when a day-level split matters.
"""

from __future__ import annotations

from datetime import date

BASE_LOT = 25

LOT_ERAS: list[tuple[date, int]] = [
    (date(2024, 11, 20), 75),
    (date(2025, 12, 30), 65),
]


def lot_for_date(d: date) -> int:
    lot = BASE_LOT
    for start, size in LOT_ERAS:
        if d >= start:
            lot = size
    return lot
