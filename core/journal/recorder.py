"""SQLite Trade Telemetry Journal & Attribution Engine.

Following Kailash Nadh standard:
- Standard library sqlite3: Zero ORMs, zero external dependencies.
- Strict telemetry schema capturing fill slippage, MAE, MFE, friction, and net PnL.
- Closed-loop attribution taxonomy:
  * CLEAN_WIN: Setup executed as planned with positive expectancy.
  * REGIME_MISCLASSIFIED: False breakout into chop or sudden trend reversal.
  * VOL_CRUSH: Unfavorable volatility spike or collapse.
  * SLIPPAGE_DRAG: Wide bid-ask or execution latency eroded edge.
- Circuit breaker queries for daily loss cap and consecutive losing sessions.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import config


@dataclass(slots=True)
class TradeRecord:
    """Represents a single executed trade recorded in the SQLite journal."""
    trade_id: str
    date: str                  # "YYYY-MM-DD"
    entry_time: str            # "HH:MM:SS"
    strategy: str              # e.g. "Debit Spread", "Credit Spread", "Iron Condor"
    action: str                # "BUY" / "SELL" / "SPREAD"
    underlying: str            # "NIFTY"
    lots: int
    quantity: int
    fill_price: float
    exit_time: Optional[str] = None
    exit_price: Optional[float] = None
    slippage: float = 0.0
    mae: float = 0.0           # Maximum Adverse Excursion (pts or ₹)
    mfe: float = 0.0           # Maximum Favorable Excursion (pts or ₹)
    gross_pnl: float = 0.0
    charges: float = 0.0       # Zerodha friction breakdown total
    net_pnl: float = 0.0
    exit_reason: Optional[str] = None   # TARGET_HIT, STOP_LOSS, SQUARE_OFF, MANUAL
    attribution: Optional[str] = None   # CLEAN_WIN, REGIME_MISCLASSIFIED, VOL_CRUSH, SLIPPAGE_DRAG
    metadata_json: str = "{}"


from contextlib import contextmanager

class TradeJournal:
    """SQLite-backed trade telemetry recorder and performance attribution engine."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = Path(db_path) if db_path else config.TRADE_JOURNAL_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Initializes trade_journal table and performance indices."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_journal (
                    trade_id TEXT PRIMARY KEY,
                    date TEXT NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_time TEXT,
                    strategy TEXT NOT NULL,
                    action TEXT NOT NULL,
                    underlying TEXT NOT NULL DEFAULT 'NIFTY',
                    lots INTEGER NOT NULL DEFAULT 1,
                    quantity INTEGER NOT NULL DEFAULT 75,
                    fill_price REAL NOT NULL,
                    exit_price REAL,
                    slippage REAL NOT NULL DEFAULT 0.0,
                    mae REAL NOT NULL DEFAULT 0.0,
                    mfe REAL NOT NULL DEFAULT 0.0,
                    gross_pnl REAL NOT NULL DEFAULT 0.0,
                    charges REAL NOT NULL DEFAULT 0.0,
                    net_pnl REAL NOT NULL DEFAULT 0.0,
                    exit_reason TEXT,
                    attribution TEXT,
                    metadata_json TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_date ON trade_journal(date);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_journal_strategy ON trade_journal(strategy);")
            conn.commit()

    def record_entry(
        self,
        strategy: str,
        fill_price: float,
        lots: int = 1,
        action: str = "SPREAD",
        underlying: str = "NIFTY",
        trade_date: Optional[str] = None,
        entry_time: Optional[str] = None,
        trade_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Records initial trade entry, returning unique trade_id."""
        t_id = trade_id or str(uuid.uuid4())[:8]
        now = datetime.now()
        t_date = trade_date or now.strftime("%Y-%m-%d")
        t_time = entry_time or now.strftime("%H:%M:%S")
        qty = lots * config.NIFTY_LOT_SIZE
        meta_str = json.dumps(metadata or {})

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO trade_journal (
                    trade_id, date, entry_time, strategy, action,
                    underlying, lots, quantity, fill_price, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (t_id, t_date, t_time, strategy, action, underlying, lots, qty, fill_price, meta_str),
            )
            conn.commit()
        return t_id

    def record_exit(
        self,
        trade_id: str,
        exit_price: float,
        charges: float,
        exit_reason: str,
        exit_time: Optional[str] = None,
        mae: float = 0.0,
        mfe: float = 0.0,
        slippage: float = 0.0,
        attribution: Optional[str] = None,
    ) -> TradeRecord:
        """Closes an open trade, computes net PnL, and classifies attribution."""
        now = datetime.now()
        t_exit_time = exit_time or now.strftime("%H:%M:%S")

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM trade_journal WHERE trade_id = ?;", (trade_id,)).fetchone()
            if not row:
                raise ValueError(f"Trade ID {trade_id} not found in journal.")

            qty = row["quantity"]
            fill_price = row["fill_price"]
            action = row["action"].upper()

            # Gross PnL computation:
            # If standard buy/spread entry: (exit - entry) * qty
            # If net credit sell entry: (entry - exit) * qty
            if "SELL" in action or "CREDIT" in row["strategy"].upper():
                gross_pnl = (fill_price - exit_price) * qty
            else:
                gross_pnl = (exit_price - fill_price) * qty

            net_pnl = round(gross_pnl - charges, 2)

            # Auto-classify attribution if not explicitly provided
            if not attribution:
                attribution = self.classify_attribution(
                    net_pnl=net_pnl,
                    mae=mae,
                    mfe=mfe,
                    slippage=slippage,
                    charges=charges,
                    exit_reason=exit_reason,
                )

            conn.execute(
                """
                UPDATE trade_journal
                SET exit_time = ?,
                    exit_price = ?,
                    slippage = ?,
                    mae = ?,
                    mfe = ?,
                    gross_pnl = ?,
                    charges = ?,
                    net_pnl = ?,
                    exit_reason = ?,
                    attribution = ?
                WHERE trade_id = ?;
                """,
                (t_exit_time, exit_price, slippage, mae, mfe, round(gross_pnl, 2), charges, net_pnl, exit_reason, attribution, trade_id),
            )
            conn.commit()

            updated = conn.execute("SELECT * FROM trade_journal WHERE trade_id = ?;", (trade_id,)).fetchone()
            return TradeRecord(
                trade_id=updated["trade_id"],
                date=updated["date"],
                entry_time=updated["entry_time"],
                strategy=updated["strategy"],
                action=updated["action"],
                underlying=updated["underlying"],
                lots=updated["lots"],
                quantity=updated["quantity"],
                fill_price=updated["fill_price"],
                exit_time=updated["exit_time"],
                exit_price=updated["exit_price"],
                slippage=updated["slippage"],
                mae=updated["mae"],
                mfe=updated["mfe"],
                gross_pnl=updated["gross_pnl"],
                charges=updated["charges"],
                net_pnl=updated["net_pnl"],
                exit_reason=updated["exit_reason"],
                attribution=updated["attribution"],
                metadata_json=updated["metadata_json"],
            )

    @staticmethod
    def classify_attribution(
        net_pnl: float,
        mae: float,
        mfe: float,
        slippage: float,
        charges: float,
        exit_reason: str,
    ) -> str:
        """Deterministic root-cause attribution logic for post-trade reviews."""
        if net_pnl > 0:
            return "CLEAN_WIN"

        # Check if slippage drag turned a winning/flat trade into a loss
        if (net_pnl + slippage + charges) > 0 and slippage > (charges * 0.5):
            return "SLIPPAGE_DRAG"

        # If MFE was high but price whipsawed through MAE into stop-loss
        if mfe > 20.0 and exit_reason == "STOP_LOSS":
            return "REGIME_MISCLASSIFIED"

        if exit_reason == "STOP_LOSS":
            return "REGIME_MISCLASSIFIED"

        return "VOL_CRUSH"

    def log_completed_trade(
        self,
        strategy: str,
        fill_price: float,
        exit_price: float,
        charges: float,
        exit_reason: str,
        lots: int = 1,
        trade_date: Optional[str] = None,
        entry_time: Optional[str] = None,
        exit_time: Optional[str] = None,
        mae: float = 0.0,
        mfe: float = 0.0,
        slippage: float = 0.0,
        attribution: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TradeRecord:
        """Single-call convenience method to insert a completed trade."""
        t_id = self.record_entry(
            strategy=strategy,
            fill_price=fill_price,
            lots=lots,
            trade_date=trade_date,
            entry_time=entry_time,
            metadata=metadata,
        )
        return self.record_exit(
            trade_id=t_id,
            exit_price=exit_price,
            charges=charges,
            exit_reason=exit_reason,
            exit_time=exit_time,
            mae=mae,
            mfe=mfe,
            slippage=slippage,
            attribution=attribution,
        )

    def get_daily_pnl(self, target_date: str) -> float:
        """Returns total net PnL realized on given date."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT SUM(net_pnl) FROM trade_journal WHERE date = ?;", (target_date,))
            res = cur.fetchone()[0]
            return float(res) if res is not None else 0.0

    def get_monthly_pnl(self, year_month: str) -> float:
        """Returns total net PnL for given year-month prefix (e.g. '2026-09')."""
        pattern = f"{year_month}%"
        with self._get_connection() as conn:
            cur = conn.execute("SELECT SUM(net_pnl) FROM trade_journal WHERE date LIKE ?;", (pattern,))
            res = cur.fetchone()[0]
            return float(res) if res is not None else 0.0

    def get_consecutive_losses(self) -> int:
        """Returns the number of consecutive losing trades looking backwards from latest."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT net_pnl FROM trade_journal
                WHERE exit_price IS NOT NULL
                ORDER BY date DESC, entry_time DESC
                LIMIT 10;
                """
            ).fetchall()

            streak = 0
            for r in rows:
                if r["net_pnl"] < 0:
                    streak += 1
                else:
                    break
            return streak

    def get_trade_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Returns recent trade records as dicts."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM trade_journal ORDER BY date DESC, entry_time DESC LIMIT ?;",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
