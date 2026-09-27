"""DhanHQ live market feed implementation with tenacity retry resilience.

Provides live and mock market data ingestion for Nifty 50 intraday candles,
option chain snapshots, spot prices, and India VIX.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

import config
from core.feeds.base import BaseMarketFeed, Candle, OptionChainSnapshot, OptionContract

logger = logging.getLogger(__name__)

# Try importing DhanContext and dhanhq from dhanhq library
try:
    from dhanhq import DhanContext, dhanhq
    DHAN_AVAILABLE = True
except ImportError:
    DHAN_AVAILABLE = False


def _approx_bs_greeks(spot: float, strike: float, is_call: bool, iv: float = 0.13, dte_days: float = 2.0) -> dict:
    """Fast institutional approximation of Black-Scholes Greeks for option chains.
    
    ponytail: Uses closed-form normal approximations to avoid scipy dependency.
    """
    t = max(dte_days, 0.1) / 365.0
    vol = max(iv, 0.05)
    sqrt_t = math.sqrt(t)
    denom = vol * sqrt_t
    
    d1 = (math.log(spot / strike) + 0.5 * (vol ** 2) * t) / denom
    d2 = d1 - denom
    
    # Cumulative standard normal approximation (Abramowitz & Stegun)
    def cdf(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
    
    def pdf(x: float) -> float:
        return (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * x * x)
    
    nd1 = cdf(d1)
    nd2 = cdf(d2)
    pd1 = pdf(d1)
    
    if is_call:
        delta = nd1
        ltp = max(0.5, spot * nd1 - strike * nd2)
    else:
        delta = nd1 - 1.0
        ltp = max(0.5, strike * (1.0 - nd2) - spot * (1.0 - nd1))
        
    gamma = pd1 / (spot * denom)
    vega = spot * pd1 * sqrt_t / 100.0  # per 1% vol change
    theta = -(spot * pd1 * vol / (2.0 * sqrt_t) / 365.0)  # 1-day theta
    
    return {
        "ltp": round(ltp, 2),
        "delta": round(delta, 3),
        "gamma": round(gamma, 5),
        "theta": round(theta, 2),
        "vega": round(vega, 2),
    }


def generate_mock_candles(
    symbol: str = "NIFTY",
    trade_date: Optional[date] = None,
    from_time: str = "09:15",
    to_time: Optional[str] = "10:15",
    interval: int = 5,
    base_price: float = 25200.0,
    trend: str = "bullish",
) -> pd.DataFrame:
    """Generate realistic synthetic 5-minute candles from 09:15 up to to_time."""
    d = trade_date or date.today()
    from_h, from_m = map(int, from_time.split(":"))
    start_dt = datetime.combine(d, time(from_h, from_m))
    
    if to_time:
        to_h, to_m = map(int, to_time.split(":"))
        end_dt = datetime.combine(d, time(to_h, to_m))
    else:
        end_dt = datetime.combine(d, time(15, 30))
        
    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(minutes=interval * 6)
        
    candles = []
    curr_dt = start_dt
    price = base_price
    
    step = 0
    while curr_dt <= end_dt:
        step += 1
        # Regime dynamics
        if trend == "bullish":
            drift = 5.0 if step <= 6 else 8.0  # Expands after 09:45
            volatility = 6.0
        elif trend == "bearish":
            drift = -5.0 if step <= 6 else -8.0
            volatility = 6.0
        elif trend == "range":
            drift = 1.5 * math.sin(step)
            volatility = 3.5
        else:  # noisy chop
            drift = 7.0 if step % 2 == 0 else -7.0
            volatility = 9.0
            
        c_open = price
        c_close = c_open + drift
        c_high = max(c_open, c_close) + abs(volatility)
        c_low = min(c_open, c_close) - abs(volatility)
        
        # Opening volume vs breakout volume
        if step == 1:
            volume = 150_000
        elif step == 7 and trend == "bullish":  # 09:45-09:50 breakout candle
            volume = 220_000  # 1.5x average
        else:
            volume = 95_000 + (step % 4) * 15_000
            
        candles.append({
            "timestamp": curr_dt,
            "open": round(c_open, 2),
            "high": round(c_high, 2),
            "low": round(c_low, 2),
            "close": round(c_close, 2),
            "volume": int(volume),
        })
        
        price = c_close
        curr_dt += timedelta(minutes=interval)
        
    return pd.DataFrame(candles)


def generate_mock_option_chain(
    spot_price: float = 25240.50,
    expiry: Optional[str] = None,
    snap_time: Optional[datetime] = None,
) -> OptionChainSnapshot:
    """Generate realistic OptionChainSnapshot around spot price."""
    ts = snap_time or datetime.now()
    if not expiry:
        # Default to nearest upcoming Thursday
        days_ahead = (3 - ts.weekday()) % 7
        target_expiry = ts.date() + timedelta(days=days_ahead)
        exp_str = target_expiry.strftime("%Y-%m-%d")
    else:
        exp_str = expiry
        
    atm = round(spot_price / config.STRIKE_INTERVAL) * config.STRIKE_INTERVAL
    strikes = [atm + i * config.STRIKE_INTERVAL for i in range(-7, 8)]
    
    contracts: Dict[Tuple[float, str], OptionContract] = {}
    
    # Establish Call Wall at ATM + 150, Put Wall at ATM - 150
    call_wall_strike = atm + 150.0
    put_wall_strike = atm - 150.0
    
    for k in strikes:
        # Greeks & theoretical LTP
        ce_greeks = _approx_bs_greeks(spot_price, k, is_call=True, iv=0.132)
        pe_greeks = _approx_bs_greeks(spot_price, k, is_call=False, iv=0.136)
        
        # Realistic Open Interest distribution
        ce_dist = abs(k - call_wall_strike) / 50.0
        ce_oi = int(220_000 * math.exp(-0.35 * ce_dist) + 40_000)
        ce_prev_oi = int(ce_oi * 0.88)
        
        pe_dist = abs(k - put_wall_strike) / 50.0
        pe_oi = int(240_000 * math.exp(-0.35 * pe_dist) + 45_000)
        pe_prev_oi = int(pe_oi * 0.85)
        
        ce_bid = round(max(0.5, ce_greeks["ltp"] - 0.25), 2)
        ce_ask = round(ce_greeks["ltp"] + 0.25, 2)
        
        pe_bid = round(max(0.5, pe_greeks["ltp"] - 0.25), 2)
        pe_ask = round(pe_greeks["ltp"] + 0.25, 2)
        
        contracts[(float(k), "CE")] = OptionContract(
            symbol=f"NIFTY{k}CE",
            strike=float(k),
            option_type="CE",
            expiry=exp_str,
            ltp=ce_greeks["ltp"],
            bid=ce_bid,
            ask=ce_ask,
            oi=ce_oi,
            prev_oi=ce_prev_oi,
            volume=int(ce_oi * 0.6),
            iv=13.2,
            delta=ce_greeks["delta"],
            gamma=ce_greeks["gamma"],
            theta=ce_greeks["theta"],
            vega=ce_greeks["vega"],
        )
        
        contracts[(float(k), "PE")] = OptionContract(
            symbol=f"NIFTY{k}PE",
            strike=float(k),
            option_type="PE",
            expiry=exp_str,
            ltp=pe_greeks["ltp"],
            bid=pe_bid,
            ask=pe_ask,
            oi=pe_oi,
            prev_oi=pe_prev_oi,
            volume=int(pe_oi * 0.65),
            iv=13.6,
            delta=pe_greeks["delta"],
            gamma=pe_greeks["gamma"],
            theta=pe_greeks["theta"],
            vega=pe_greeks["vega"],
        )
        
    return OptionChainSnapshot(
        timestamp=ts,
        spot_price=spot_price,
        contracts=contracts,
        expiry=exp_str,
    )


class DhanFeed(BaseMarketFeed):
    """DhanHQ live market data feed with resilience and mock fallback."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        access_token: Optional[str] = None,
        mock: Optional[bool] = None,
    ) -> None:
        self.client_id = client_id or config.DHAN_CLIENT_ID
        self.access_token = access_token or config.DHAN_ACCESS_TOKEN
        
        # If explicitly set, use mock parameter; else check config or missing credentials
        if mock is not None:
            self.mock_mode = mock
        else:
            self.mock_mode = config.MOCK_MODE or not (self.client_id and self.access_token)
            
        self.client = None
        if not self.mock_mode and DHAN_AVAILABLE:
            try:
                ctx = DhanContext(self.client_id, self.access_token)
                self.client = dhanhq(ctx)
            except Exception as e:
                logger.warning(f"Failed to initialize DhanHQ client: {e}. Falling back to mock mode.")
                self.mock_mode = True

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def fetch_intraday_candles(
        self,
        symbol: str = "NIFTY",
        from_time: str = "09:15",
        to_time: Optional[str] = None,
        interval: int = 5,
    ) -> pd.DataFrame:
        """Fetch intraday OHLCV candles from DhanHQ or mock generator."""
        if self.mock_mode or not self.client:
            return generate_mock_candles(
                symbol=symbol,
                from_time=from_time,
                to_time=to_time or datetime.now().strftime("%H:%M"),
                interval=interval,
            )
            
        # Live DhanHQ API call
        today_str = date.today().strftime("%Y-%m-%d")
        resp = self.client.intraday_minute_data(
            security_id=str(config.NIFTY_SECURITY_ID),
            exchange_segment="IDX_I",
            instrument_type="INDEX",
            from_date=today_str,
            to_date=today_str,
            interval=interval,
            oi=False,
        )
        
        if not resp or resp.get("status") != "success" or "data" not in resp:
            raise RuntimeError(f"DhanHQ intraday_minute_data failed: {resp}")
            
        data = resp["data"]
        timestamps = data.get("start_Time") or data.get("timestamp", [])
        opens = data.get("open", [])
        highs = data.get("high", [])
        lows = data.get("low", [])
        closes = data.get("close", [])
        volumes = data.get("volume", [0] * len(opens))
        
        records = []
        for i in range(len(opens)):
            ts = timestamps[i]
            # Convert epoch if needed
            dt_val = datetime.fromtimestamp(ts) if isinstance(ts, (int, float)) else pd.to_datetime(ts)
            records.append({
                "timestamp": dt_val,
                "open": float(opens[i]),
                "high": float(highs[i]),
                "low": float(lows[i]),
                "close": float(closes[i]),
                "volume": int(volumes[i]),
            })
            
        df = pd.DataFrame(records)
        if df.empty:
            return df
            
        # Filter from_time to to_time
        from_h, from_m = map(int, from_time.split(":"))
        start_t = time(from_h, from_m)
        df = df[df["timestamp"].dt.time >= start_t]
        
        if to_time:
            to_h, to_m = map(int, to_time.split(":"))
            end_t = time(to_h, to_m)
            df = df[df["timestamp"].dt.time <= end_t]
            
        return df.reset_index(drop=True)

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def fetch_option_chain(
        self,
        symbol: str = "NIFTY",
        expiry: Optional[str] = None,
    ) -> OptionChainSnapshot:
        """Fetch option chain snapshot for strikes within ATM +/- 300 pts."""
        if self.mock_mode or not self.client:
            spot = self.fetch_spot_price(symbol)
            return generate_mock_option_chain(spot_price=spot, expiry=expiry)
            
        # Discover expiry if not provided
        exp_str = expiry
        if not exp_str:
            exp_resp = self.client.expiry_list(
                under_security_id=config.NIFTY_SECURITY_ID,
                under_exchange_segment="IDX_I",
            )
            if exp_resp and exp_resp.get("status") == "success":
                exp_list = exp_resp.get("data", [])
                if exp_list:
                    exp_str = str(exp_list[0])
                    
        if not exp_str:
            raise ValueError("Unable to determine option chain expiry date from DhanHQ")
            
        resp = self.client.option_chain(
            under_security_id=config.NIFTY_SECURITY_ID,
            under_exchange_segment="IDX_I",
            expiry=exp_str,
        )
        
        if not resp or resp.get("status") != "success" or "data" not in resp:
            raise RuntimeError(f"DhanHQ option_chain API returned failure: {resp}")
            
        data = resp["data"]
        spot_price = float(data.get("last_price", 25200.0))
        oc_dict = data.get("oc", {})
        
        atm_strike = round(spot_price / config.STRIKE_INTERVAL) * config.STRIKE_INTERVAL
        min_strike = atm_strike - config.STRIKE_WINDOW
        max_strike = atm_strike + config.STRIKE_WINDOW
        
        contracts: Dict[Tuple[float, str], OptionContract] = {}
        
        for strike_str, strike_data in oc_dict.items():
            try:
                strike_flt = float(strike_str)
            except ValueError:
                continue
                
            if not (min_strike <= strike_flt <= max_strike):
                continue
                
            for opt_type in ("ce", "pe"):
                side_data = strike_data.get(opt_type)
                if not side_data:
                    continue
                    
                greeks = side_data.get("greeks") or {}
                opt_upper = opt_type.upper()
                contract = OptionContract(
                    symbol=f"NIFTY{int(strike_flt)}{opt_upper}",
                    strike=strike_flt,
                    option_type=opt_upper,
                    expiry=exp_str,
                    ltp=float(side_data.get("last_price", 0.0)),
                    bid=float(side_data.get("top_bid", 0.0)),
                    ask=float(side_data.get("top_ask", 0.0)),
                    oi=int(side_data.get("oi", 0)),
                    prev_oi=int(side_data.get("previous_oi", 0)),
                    volume=int(side_data.get("volume", 0)),
                    iv=float(side_data.get("implied_volatility", 0.0)),
                    delta=float(greeks.get("delta", 0.0)),
                    gamma=float(greeks.get("gamma", 0.0)),
                    theta=float(greeks.get("theta", 0.0)),
                    vega=float(greeks.get("vega", 0.0)),
                )
                contracts[(strike_flt, opt_upper)] = contract
                
        return OptionChainSnapshot(
            timestamp=datetime.now(),
            spot_price=spot_price,
            contracts=contracts,
            expiry=exp_str,
        )

    def fetch_spot_price(self, symbol: str = "NIFTY") -> float:
        """Fetch current underlying spot price."""
        if self.mock_mode or not self.client:
            return 25240.50
            
        resp = self.client.ohlc_data({"IDX_I": [config.NIFTY_SECURITY_ID]})
        if resp and resp.get("status") == "success":
            data = resp.get("data", {}).get("IDX_I", {})
            for _, item in data.items():
                if "last_price" in item:
                    return float(item["last_price"])
        return 25240.50

    def fetch_vix(self) -> float:
        """Fetch current India VIX index value."""
        if self.mock_mode or not self.client:
            return 13.20
            
        resp = self.client.ohlc_data({"IDX_I": [config.INDIA_VIX_SECURITY_ID]})
        if resp and resp.get("status") == "success":
            data = resp.get("data", {}).get("IDX_I", {})
            for _, item in data.items():
                if "last_price" in item:
                    return float(item["last_price"])
        return 13.20
