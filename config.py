"""Single source of truth for quantitative Nifty options engine.

Defines capital constants, contract specs, post-Oct 2024 Zerodha fee schedules,
and weekday-calibrated high-probability intraday execution windows.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path
from typing import Tuple

from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# --- Filesystem Paths ---
BASE_DIR: Path = Path(__file__).resolve().parent
DATA_DIR: Path = BASE_DIR / "data"
HISTORICAL_DATA_DIR: Path = DATA_DIR / "historical"
TRADE_JOURNAL_PATH: Path = DATA_DIR / "trade_journal.sqlite"
CALIBRATED_PARAMS_PATH: Path = DATA_DIR / "calibrated_params.json"

# Ensure data directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
HISTORICAL_DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- Capital & Risk Preservation Limits (Bankroll: ₹2,00,000) ---
TOTAL_CAPITAL: float = 200_000.0
MAX_DAILY_LOSS: float = 2_500.0          # 1.25% of bankroll hard stop
MONTHLY_DRAWDOWN_CAP: float = 10_000.0   # 5.0% of bankroll circuit breaker
TARGET_PAYOFF_RATIO: float = 1.40        # Minimum Target Profit : Max Risk
MIN_WIN_RATE: float = 0.55               # Statistical out-of-sample edge hurdle
ECONOMIC_HURDLE_RATIO: float = 2.0       # Expected Net Value >= 2.0x friction
OFF_WINDOW_HURDLE_RATIO: float = 3.0     # Elevated hurdle outside optimal window

# Capital Tiers
TIER_0_CAPITAL: float = 0.0              # NO TRADE / Capital preservation
TIER_1_CAPITAL: float = 45_000.0         # 1 Lot (75 qty), max risk ₹2,000
TIER_1_LOTS: int = 1
TIER_1_MAX_RISK: float = 2_000.0

TIER_2_CAPITAL: float = 90_000.0         # 2 Lots (150 qty), max risk ₹2,500
TIER_2_LOTS: int = 2
TIER_2_MAX_RISK: float = 2_500.0

# --- Nifty 50 Contract Specifications ---
NIFTY_SYMBOL: str = "NIFTY"
NIFTY_LOT_SIZE: int = 75
STRIKE_INTERVAL: int = 50
STRIKE_WINDOW: int = 300                 # +/- 300 points from ATM
NIFTY_SECURITY_ID: int = 13              # DhanHQ underlying security ID for Nifty 50
INDIA_VIX_SECURITY_ID: int = 26000       # DhanHQ security ID for India VIX

# --- Zerodha & Regulatory Cost Model (Post-Oct 2024 SEBI Norms) ---
BROKERAGE_PER_LEG_PER_SIDE: float = 20.0 # ₹20 per executed leg per order
STT_SELL_RATE: float = 0.001             # 0.1% on sell-side option premium turnover
EXCHANGE_TURNOVER_RATE: float = 0.000505 # 0.0505% NSE turnover charge
SEBI_TURNOVER_RATE: float = 0.000001     # ₹10 per crore (0.0001%)
STAMP_DUTY_BUY_RATE: float = 0.00003     # 0.003% on buy-side premium turnover
GST_RATE: float = 0.18                   # 18% on (Brokerage + Exchange + SEBI)
SLIPPAGE_POINTS_PER_LEG: float = 1.5     # Modeled slippage buffer per leg

# --- Weekday Execution Windows & Expiry Gamma Cutoffs ---
# Python weekday index: Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4
@dataclass(frozen=True, slots=True)
class ExecutionWindow:
    start: time
    end: time

    def contains(self, t: time) -> bool:
        return self.start <= t <= self.end


@dataclass(frozen=True, slots=True)
class WeekdaySchedule:
    day_name: str
    primary_window: ExecutionWindow
    secondary_window: ExecutionWindow | None
    square_off_time: time
    description: str

    def is_in_window(self, t: time) -> Tuple[bool, str]:
        if self.primary_window.contains(t):
            return True, f"{self.day_name} Primary Window ({self.primary_window.start.strftime('%H:%M')}-{self.primary_window.end.strftime('%H:%M')})"
        if self.secondary_window and self.secondary_window.contains(t):
            return True, f"{self.day_name} Secondary Window ({self.secondary_window.start.strftime('%H:%M')}-{self.secondary_window.end.strftime('%H:%M')})"
        return False, f"Outside {self.day_name} optimal windows"


WEEKDAY_SCHEDULES: dict[int, WeekdaySchedule] = {
    0: WeekdaySchedule(
        day_name="Monday",
        primary_window=ExecutionWindow(time(10, 0), time(10, 45)),
        secondary_window=ExecutionWindow(time(13, 15), time(14, 0)),
        square_off_time=time(15, 0),
        description="Gap digestion & stabilization",
    ),
    1: WeekdaySchedule(
        day_name="Tuesday",
        primary_window=ExecutionWindow(time(9, 45), time(10, 30)),
        secondary_window=ExecutionWindow(time(12, 45), time(13, 30)),
        square_off_time=time(15, 0),
        description="Directional momentum drift",
    ),
    2: WeekdaySchedule(
        day_name="Wednesday",
        primary_window=ExecutionWindow(time(10, 0), time(11, 0)),
        secondary_window=ExecutionWindow(time(13, 30), time(14, 15)),
        square_off_time=time(15, 0),
        description="Pre-expiry theta decay initiation",
    ),
    3: WeekdaySchedule(
        day_name="Thursday",
        primary_window=ExecutionWindow(time(9, 35), time(10, 15)),
        secondary_window=ExecutionWindow(time(13, 15), time(14, 0)),
        square_off_time=time(14, 45),  # 14:45 hard square-off before 0DTE gamma spikes
        description="Weekly expiry day; gamma cutoff at 14:45",
    ),
    4: WeekdaySchedule(
        day_name="Friday",
        primary_window=ExecutionWindow(time(10, 15), time(11, 0)),
        secondary_window=None,
        square_off_time=time(15, 0),
        description="Initial structure setup, avoid post-13:30",
    ),
}


def get_schedule_for_date(dt: datetime | None = None) -> WeekdaySchedule | None:
    """Return WeekdaySchedule for given datetime or current local time."""
    target_dt = dt or datetime.now()
    return WEEKDAY_SCHEDULES.get(target_dt.weekday())


def is_optimal_window(dt: datetime | None = None) -> Tuple[bool, str]:
    """Check if the provided datetime falls within an optimal weekday window."""
    target_dt = dt or datetime.now()
    schedule = get_schedule_for_date(target_dt)
    if schedule is None:
        return False, "Market closed on weekends"
    return schedule.is_in_window(target_dt.time())


def get_square_off_time(dt: datetime | None = None) -> time:
    """Return the hard intraday square-off time for the given day."""
    target_dt = dt or datetime.now()
    schedule = get_schedule_for_date(target_dt)
    if schedule is None:
        return time(15, 0)
    return schedule.square_off_time


# --- API Credentials & Run Mode ---
DHAN_CLIENT_ID: str = os.getenv("DHAN_CLIENT_ID", "")
DHAN_ACCESS_TOKEN: str = os.getenv("DHAN_ACCESS_TOKEN", "")
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
MOCK_MODE: bool = os.getenv("MOCK_MODE", "True").strip().lower() in ("true", "1", "yes")
