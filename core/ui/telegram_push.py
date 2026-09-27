"""Telegram Bot Dispatcher for Quantitative Nifty Options Alerts.

Following Kailash Nadh standard:
- Zero pip bot frameworks: Uses Python standard library `urllib.request` and `json`.
- Resilient timeouts and error handling (never crashes main process if network fails).
- Clean Markdown / HTML trade cards with one-click Zerodha mobile execution link.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import config
from core.execution.basket_builder import KiteBasket
from core.signals import MarketSignals
from core.strategies.audit_engine import AuditReport

logger = logging.getLogger(__name__)


def format_telegram_trade_card(
    signals: MarketSignals,
    report: AuditReport,
    basket: Optional[KiteBasket] = None,
) -> str:
    """Formats a clean Markdown trade card for Telegram."""
    run_dt = signals.timestamp if isinstance(signals.timestamp, datetime) else datetime.now()
    ts_str = run_dt.strftime("%Y-%m-%d %H:%M:%S")

    if not report.is_trade_approved or not report.selected_proposal:
        # Standby Trade Card
        msg = [
            "🛡️ *NIFTY QUANT ENGINE: CAPITAL PRESERVATION*",
            f"📅 *Timestamp:* {ts_str} IST",
            f"📊 *Spot:* {signals.spot_price:,.2f} | *VWAP:* {signals.vwap.vwap:,.2f} | *VIX:* {signals.vix_iv.vix:.1f}",
            "",
            "⏸️ *Status:* STAND BY / NO TRADE",
            f"• *Verdict:* {report.verdict}",
            f"• *KER:* {signals.ker.ker:.3f} (Path noise filter)",
            f"• *ORB Bounds:* {signals.orb.orl:.1f} - {signals.orb.orh:.1f}",
            "",
            "💡 *Bankroll ₹2,00,000 intact. Capital preserved.*",
        ]
        return "\n".join(msg)

    prop = report.selected_proposal
    lots = prop.legs[0].lots if prop.legs else 1
    qty = lots * config.NIFTY_LOT_SIZE
    sq_off = config.get_square_off_time(run_dt).strftime("%I:%M %p")

    msg = [
        "🎯 *NIFTY OPTIONS TRADE RECOMMENDATION*",
        f"📅 *Timestamp:* {ts_str} IST",
        f"⚡ *Strategy:* *{prop.strategy_name.upper()}*",
        f"📦 *Sizing:* {lots} Lot ({qty} Qty) | *Expiry:* {prop.expiry}",
        "",
        "📊 *Market Diagnostics:*",
        f"• *Spot:* {signals.spot_price:,.2f} | *VWAP:* {signals.vwap.vwap:,.2f} ({signals.vwap.slope_15m:+.3f}%)",
        f"• *India VIX:* {signals.vix_iv.vix:.1f} ({signals.vix_iv.delta_vix:+.2f}%) | *IV Spread:* {signals.vix_iv.iv_spread:+.1f}",
        f"• *KER:* {signals.ker.ker:.3f} | *ORB:* {signals.orb.status}",
        f"• *Walls:* Put {signals.oi.put_wall:.0f} / Call {signals.oi.call_wall:.0f}",
        "",
        "📝 *Basket Execution Sequence (Hedge 1st for Margin):*",
    ]

    for idx, leg in enumerate(prop.legs, 1):
        num_emoji = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"][min(idx - 1, 3)]
        action = leg.action.upper()
        sym = leg.symbol or f"NIFTY {int(leg.strike)} {leg.option_type}"
        msg.append(f"{num_emoji} *[{action}]* `{sym}` @ ~₹{leg.entry_price:.2f}")
        msg.append(f"     SL: ₹{leg.stop_price:.2f} | Target: ₹{leg.target_price:.2f}")

    msg.extend([
        "",
        "💰 *Risk & Return Metrics:*",
        f"• *Premium:* ₹{abs(prop.net_debit_or_credit):.2f}/sh (₹{abs(prop.net_debit_or_credit) * qty:,.2f})",
        f"• *Net Max Loss:* -₹{prop.max_loss:,.2f} (Strict Cap)",
        f"• *Net Profit Target:* +₹{prop.target_profit:,.2f} (Payoff: {prop.payoff_ratio:.2f})",
        f"• *Expected Net EV:* +₹{prop.net_ev:,.2f} (Win Rate: {prop.win_rate * 100:.1f}%)",
        f"• *Friction:* ₹{prop.friction.total_rupees:.2f} (~{prop.friction.points_equivalent:.2f} pts)",
        f"• *Hard Square-off:* {sq_off} IST (Strict Intraday)",
        "",
        "🔍 *3-Strategy Comparative Audit Summary:*",
    ])

    for entry in report.entries:
        icon = "✅" if entry.status == "SELECTED" else "❌"
        msg.append(f"{icon} *{entry.strategy_name}:* {entry.reason}")

    if basket and basket.publisher_url:
        msg.extend([
            "",
            f"🚀 [👉 Tap Here to Execute Zerodha Basket]({basket.publisher_url})",
        ])

    return "\n".join(msg)


def send_telegram_message(
    message: str,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    parse_mode: str = "Markdown",
    timeout: float = 8.0,
) -> bool:
    """Dispatches a message to Telegram using pure Python standard library urllib.request."""
    token = bot_token if bot_token is not None else config.TELEGRAM_BOT_TOKEN
    target_chat = chat_id if chat_id is not None else config.TELEGRAM_CHAT_ID

    if not token or not target_chat or "your_bot_token" in token.lower():
        logger.info("Telegram notification skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False,
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = Request(
            url=url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=timeout) as response:
            resp_code = response.getcode()
            if 200 <= resp_code < 300:
                logger.info("Telegram notification delivered successfully.")
                return True
            else:
                logger.warning("Telegram API returned non-200 code: %d", resp_code)
                return False
    except HTTPError as e:
        logger.error("Telegram HTTP error: %d %s", e.code, e.reason)
        return False
    except URLError as e:
        logger.error("Telegram network error: %s", e.reason)
        return False
    except Exception as e:
        logger.error("Unexpected error dispatching Telegram alert: %s", e)
        return False


def push_trade_alert(
    signals: MarketSignals,
    report: AuditReport,
    basket: Optional[KiteBasket] = None,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> bool:
    """Formats and pushes trade alert card to Telegram."""
    card = format_telegram_trade_card(signals=signals, report=report, basket=basket)
    return send_telegram_message(message=card, bot_token=bot_token, chat_id=chat_id)
