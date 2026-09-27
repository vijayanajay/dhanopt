"""Zerodha Kite Basket Order Builder and One-Click Publisher Deep Link Generator.

Following Kailash Nadh / Zerodha standards:
- Strict Execution Sequencing: Long/Hedge legs FIRST (BUY), Short legs SECOND (SELL).
  This guarantees immediate margin relief on Zerodha RMS before short order hits the market.
- Zerodha Kite Basket JSON format for Kite Web import.
- Kite Publisher URL generation for single-swipe mobile execution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import config
from core.auditors.rule_gatekeeper import TradeProposal
from core.friction.zerodha import OptionLeg


@dataclass(slots=True)
class KiteOrder:
    """Represents a single order item in a Zerodha Kite basket."""
    variety: str
    tradingsymbol: str
    exchange: str
    transaction_type: str  # "BUY" or "SELL"
    order_type: str        # "LIMIT" or "MARKET"
    quantity: int
    price: float
    product: str           # "MIS" for intraday margin relief
    validity: str = "DAY"
    tag: str = "DHANOPT"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variety": self.variety,
            "tradingsymbol": self.tradingsymbol,
            "exchange": self.exchange,
            "transaction_type": self.transaction_type,
            "order_type": self.order_type,
            "quantity": self.quantity,
            "price": round(self.price, 2) if self.order_type == "LIMIT" else 0.0,
            "product": self.product,
            "validity": self.validity,
            "tag": self.tag,
        }


@dataclass(slots=True)
class KiteBasket:
    """Complete Zerodha Basket ready for JSON export or Kite Publisher execution."""
    strategy_name: str
    orders: List[KiteOrder]
    total_quantity: int
    net_premium: float
    is_credit: bool
    publisher_url: str
    json_payload: str

    def to_list(self) -> List[Dict[str, Any]]:
        return [order.to_dict() for order in self.orders]

    def export_to_file(self, filepath: Optional[Path | str] = None) -> Path:
        """Saves the basket orders as a JSON file suitable for Kite Web basket import."""
        out_path = Path(filepath) if filepath else config.DATA_DIR / "kite_basket.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(self.json_payload)
        return out_path


def format_tradingsymbol(leg: OptionLeg, expiry_str: Optional[str] = None) -> str:
    """Formats an option leg into standard Zerodha Kite tradingsymbol.
    
    If leg.symbol is already a valid formatted symbol (e.g. NIFTY26OCT25000CE or NIFTY25000CE),
    it is normalized. Otherwise constructs NIFTY{expiry}{strike}{type}.
    """
    if leg.symbol and leg.symbol.strip():
        sym = leg.symbol.strip().upper()
        if sym.startswith("NIFTY") or sym.startswith("N"):
            return sym

    strike_int = int(leg.strike)
    opt_type = leg.option_type.upper()

    if expiry_str:
        try:
            # Handle formats: "YYYY-MM-DD" or "DD-MMM-YYYY"
            if "-" in expiry_str:
                parts = expiry_str.split("-")
                if len(parts[0]) == 4:  # YYYY-MM-DD
                    exp_dt = datetime.strptime(expiry_str, "%Y-%m-%d")
                else:
                    exp_dt = datetime.strptime(expiry_str, "%d-%b-%Y")
                exp_tag = exp_dt.strftime("%y%b").upper()
                return f"NIFTY{exp_tag}{strike_int}{opt_type}"
        except Exception:
            pass

    return f"NIFTY{strike_int}{opt_type}"


def build_kite_basket(
    proposal: TradeProposal,
    product: str = "MIS",
    order_type: str = "LIMIT",
    api_key: str = "",
) -> KiteBasket:
    """Builds a Zerodha Kite basket with strict execution sequencing.
    
    Execution Ordering:
    1. All BUY / Hedge legs FIRST (Secures margin benefit upfront)
    2. All SELL / Short legs SECOND
    """
    if not proposal.legs:
        raise ValueError("Cannot build basket from proposal with zero legs.")

    # Strict sequencing: BUY legs first, SELL legs second
    buy_legs = [leg for leg in proposal.legs if leg.is_buy]
    sell_legs = [leg for leg in proposal.legs if leg.is_sell]
    ordered_legs = buy_legs + sell_legs

    orders: List[KiteOrder] = []
    total_qty = 0

    for leg in ordered_legs:
        tsym = format_tradingsymbol(leg, proposal.expiry)
        price = leg.entry_price if order_type.upper() == "LIMIT" else 0.0
        order = KiteOrder(
            variety="regular",
            tradingsymbol=tsym,
            exchange="NFO",
            transaction_type=leg.action.upper(),
            order_type=order_type.upper(),
            quantity=leg.quantity,
            price=price,
            product=product.upper(),
            validity="DAY",
            tag="DHANOPT",
        )
        orders.append(order)
        total_qty += leg.quantity

    orders_dict_list = [o.to_dict() for o in orders]
    json_payload = json.dumps(orders_dict_list, indent=2)

    # Kite Publisher URL format:
    # https://kite.zerodha.com/connect/basket?data=[...]
    encoded_data = quote(json.dumps(orders_dict_list))
    if api_key:
        publisher_url = f"https://kite.zerodha.com/connect/basket?api_key={api_key}&data={encoded_data}"
    else:
        publisher_url = f"https://kite.zerodha.com/connect/basket?data={encoded_data}"

    return KiteBasket(
        strategy_name=proposal.strategy_name,
        orders=orders,
        total_quantity=total_qty,
        net_premium=proposal.net_debit_or_credit,
        is_credit=proposal.is_credit,
        publisher_url=publisher_url,
        json_payload=json_payload,
    )
