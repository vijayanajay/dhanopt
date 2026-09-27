"""UI package providing Terminal Rich dashboard and Telegram alerts."""

from core.ui.telegram_push import (
    format_telegram_trade_card,
    push_trade_alert,
    send_telegram_message,
)
from core.ui.terminal_rich import (
    render_dashboard_to_string,
    render_terminal_dashboard,
)

__all__ = [
    "render_terminal_dashboard",
    "render_dashboard_to_string",
    "format_telegram_trade_card",
    "send_telegram_message",
    "push_trade_alert",
]
