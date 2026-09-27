"""Base contracts and abstract interfaces for market data feeds.

Defines Candle, OptionContract, OptionChainSnapshot, and BaseMarketFeed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd


@dataclass(slots=True)
class Candle:
    """Represents a single OHLCV bar."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    oi: int = 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "oi": self.oi,
        }


@dataclass(slots=True)
class OptionContract:
    """Represents a single option contract (CE/PE) at a specific strike."""
    symbol: str
    strike: float
    option_type: str  # "CE" or "PE"
    expiry: str       # "YYYY-MM-DD"
    ltp: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    oi: int = 0
    prev_oi: int = 0
    volume: int = 0
    iv: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0

    @property
    def delta_oi(self) -> int:
        return self.oi - self.prev_oi

    @property
    def bid_ask_spread(self) -> float:
        return round(abs(self.ask - self.bid), 2)


@dataclass
class OptionChainSnapshot:
    """Point-in-time snapshot of the option chain around ATM."""
    timestamp: datetime
    spot_price: float
    contracts: Dict[Tuple[float, str], OptionContract] = field(default_factory=dict)
    expiry: str = ""

    def get_contract(self, strike: float, option_type: str) -> Optional[OptionContract]:
        """Fetch contract by strike and option_type ('CE' or 'PE')."""
        return self.contracts.get((float(strike), option_type.upper()))

    def strikes(self) -> List[float]:
        """Return sorted list of all unique strikes present in chain."""
        return sorted({k[0] for k in self.contracts.keys()})

    def atm_strike(self, interval: int = 50) -> float:
        """Calculate the nearest At-The-Money strike for index interval."""
        return round(self.spot_price / interval) * interval

    def filtered_contracts(self, window: float = 300.0) -> List[OptionContract]:
        """Return contracts within +/- window points of ATM."""
        atm = self.atm_strike()
        low, high = atm - window, atm + window
        return [c for c in self.contracts.values() if low <= c.strike <= high]

    def call_wall(self, window: float = 300.0) -> float:
        """Call Wall: Strike with maximum Call Open Interest within ATM window."""
        atm = self.atm_strike()
        calls = [
            c for c in self.contracts.values()
            if c.option_type == "CE" and (atm - window) <= c.strike <= (atm + window)
        ]
        if not calls:
            return atm + 100.0
        return max(calls, key=lambda c: c.oi).strike

    def put_wall(self, window: float = 300.0) -> float:
        """Put Wall: Strike with maximum Put Open Interest within ATM window."""
        atm = self.atm_strike()
        puts = [
            c for c in self.contracts.values()
            if c.option_type == "PE" and (atm - window) <= c.strike <= (atm + window)
        ]
        if not puts:
            return atm - 100.0
        return max(puts, key=lambda c: c.oi).strike

    def total_call_oi(self, window: float = 300.0) -> int:
        atm = self.atm_strike()
        return sum(
            c.oi for c in self.contracts.values()
            if c.option_type == "CE" and (atm - window) <= c.strike <= (atm + window)
        )

    def total_put_oi(self, window: float = 300.0) -> int:
        atm = self.atm_strike()
        return sum(
            c.oi for c in self.contracts.values()
            if c.option_type == "PE" and (atm - window) <= c.strike <= (atm + window)
        )

    def pcr_oi(self, window: float = 300.0) -> float:
        """Put-Call Ratio based on Open Interest within window."""
        call_oi = self.total_call_oi(window)
        put_oi = self.total_put_oi(window)
        if call_oi == 0:
            return 1.0
        return round(put_oi / call_oi, 3)

    def pcr_volume(self, window: float = 300.0) -> float:
        """Put-Call Ratio based on Traded Volume within window."""
        atm = self.atm_strike()
        call_vol = sum(
            c.volume for c in self.contracts.values()
            if c.option_type == "CE" and (atm - window) <= c.strike <= (atm + window)
        )
        put_vol = sum(
            c.volume for c in self.contracts.values()
            if c.option_type == "PE" and (atm - window) <= c.strike <= (atm + window)
        )
        if call_vol == 0:
            return 1.0
        return round(put_vol / call_vol, 3)

    def atm_straddle_iv(self) -> float:
        """Compute average IV of ATM Call and Put options."""
        atm = self.atm_strike()
        ce = self.get_contract(atm, "CE")
        pe = self.get_contract(atm, "PE")
        ce_iv = ce.iv if ce and ce.iv > 0 else 13.0
        pe_iv = pe.iv if pe and pe.iv > 0 else 13.0
        return round((ce_iv + pe_iv) / 2.0, 2)


class BaseMarketFeed(ABC):
    """Abstract base class for market data providers."""

    @abstractmethod
    def fetch_intraday_candles(
        self,
        symbol: str = "NIFTY",
        from_time: str = "09:15",
        to_time: Optional[str] = None,
        interval: int = 5,
    ) -> pd.DataFrame:
        """Fetch intraday OHLCV candles as a pandas DataFrame."""
        pass

    @abstractmethod
    def fetch_option_chain(
        self,
        symbol: str = "NIFTY",
        expiry: Optional[str] = None,
    ) -> OptionChainSnapshot:
        """Fetch live option chain snapshot within ATM +/- window."""
        pass

    @abstractmethod
    def fetch_spot_price(self, symbol: str = "NIFTY") -> float:
        """Fetch current spot price of underlying."""
        pass

    @abstractmethod
    def fetch_vix(self) -> float:
        """Fetch current India VIX index value."""
        pass
