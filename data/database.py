"""
data/database.py — SQLite persistence layer for LetsTrading.

Tables:
  signals    — every generated signal (BUY/SELL/WAIT)
  trades     — executed (paper or live) trades
  daily_pnl  — end-of-day P&L summary per date
"""
import sqlite3
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Database file lives inside the data/ package directory
DB_PATH = os.path.join(os.path.dirname(__file__), "trades.db")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    """
    Create the database tables if they do not already exist.
    Safe to call multiple times (uses CREATE TABLE IF NOT EXISTS).
    """
    conn = _connect()
    c    = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT    NOT NULL,
            signal    TEXT    NOT NULL,
            strategy  TEXT,
            confidence REAL,
            entry     REAL,
            sl        REAL,
            target    REAL,
            rr_ratio  TEXT,
            note      TEXT,
            raw_json  TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT    NOT NULL,
            symbol          TEXT    DEFAULT 'BANKNIFTY',
            direction       TEXT,
            entry_price     REAL,
            exit_price      REAL,
            qty             INTEGER,
            lots            INTEGER,
            pnl             REAL    DEFAULT 0,
            status          TEXT    DEFAULT 'OPEN',
            order_id        TEXT,
            strategy        TEXT,
            raw_json        TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_pnl (
            date        TEXT PRIMARY KEY,
            total_trades INTEGER DEFAULT 0,
            wins         INTEGER DEFAULT 0,
            losses       INTEGER DEFAULT 0,
            win_rate     REAL    DEFAULT 0,
            total_pnl    REAL    DEFAULT 0,
            updated_at   TEXT
        )
    """)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def log_signal(signal: dict) -> int:
    """
    Insert a signal record and return the new row id.
    Accepts the standard signal dict from engine/signals.py.
    """
    conn = _connect()
    c    = conn.cursor()
    c.execute("""
        INSERT INTO signals
            (timestamp, signal, strategy, confidence, entry, sl, target, rr_ratio, note, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        signal.get("timestamp", _now()),
        signal.get("signal",    "WAIT"),
        signal.get("strategy",  ""),
        signal.get("confidence", 0),
        signal.get("entry",     0),
        signal.get("sl",        0),
        signal.get("target",    0),
        signal.get("rr_ratio",  ""),
        signal.get("note",      ""),
        json.dumps(signal),
    ))
    row_id = c.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_signals_today() -> list:
    """Return all signals generated today as a list of dicts."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn  = _connect()
    conn.row_factory = sqlite3.Row
    c    = conn.cursor()
    c.execute("SELECT * FROM signals WHERE timestamp LIKE ? ORDER BY id DESC",
              (f"{today}%",))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_recent_signals(limit: int = 20) -> list:
    """Return the most recent N signals (used in the dashboard)."""
    conn = _connect()
    conn.row_factory = sqlite3.Row
    c    = conn.cursor()
    c.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

def log_trade(trade: dict) -> int:
    """
    Insert a trade record and return the new row id.
    trade dict keys: timestamp, direction, entry_price, exit_price, qty,
                     lots, pnl, status, order_id, strategy.
    """
    conn = _connect()
    c    = conn.cursor()
    c.execute("""
        INSERT INTO trades
            (timestamp, symbol, direction, entry_price, exit_price, qty,
             lots, pnl, status, order_id, strategy, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade.get("timestamp",   _now()),
        trade.get("symbol",      "BANKNIFTY"),
        trade.get("direction",   ""),
        trade.get("entry_price", 0),
        trade.get("exit_price",  0),
        trade.get("qty",         0),
        trade.get("lots",        0),
        trade.get("pnl",         0),
        trade.get("status",      "OPEN"),
        trade.get("order_id",    ""),
        trade.get("strategy",    ""),
        json.dumps(trade),
    ))
    row_id = c.lastrowid
    conn.commit()
    conn.close()
    return row_id


def get_trades_today() -> list:
    """Return all trades for today as a list of dicts."""
    today = datetime.now().strftime("%Y-%m-%d")
    conn  = _connect()
    conn.row_factory = sqlite3.Row
    c    = conn.cursor()
    c.execute("SELECT * FROM trades WHERE timestamp LIKE ? ORDER BY id DESC",
              (f"{today}%",))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_win_rate(days: int = 30) -> float:
    """
    Calculate the win rate (%) over the last N days.
    A win is any closed trade with pnl > 0.
    Returns 0.0 if no closed trades found.
    """
    conn = _connect()
    c    = conn.cursor()
    c.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins
        FROM trades
        WHERE status = 'CLOSED'
          AND timestamp >= date('now', ?)
    """, (f"-{days} days",))
    row = c.fetchone()
    conn.close()
    if row and row[0] > 0:
        return round((row[1] / row[0]) * 100, 1)
    return 0.0


# ---------------------------------------------------------------------------
# Daily P&L
# ---------------------------------------------------------------------------

def save_daily_summary(trades: list, total_pnl: float) -> None:
    """
    Upsert the daily_pnl table for today.
    trades: list of trade dicts with 'pnl' key.
    """
    today  = datetime.now().strftime("%Y-%m-%d")
    total  = len(trades)
    wins   = sum(1 for t in trades if t.get("pnl", 0) > 0)
    losses = total - wins
    wr     = round((wins / total * 100), 1) if total > 0 else 0.0

    conn = _connect()
    c    = conn.cursor()
    c.execute("""
        INSERT INTO daily_pnl (date, total_trades, wins, losses, win_rate, total_pnl, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            total_trades = excluded.total_trades,
            wins         = excluded.wins,
            losses       = excluded.losses,
            win_rate     = excluded.win_rate,
            total_pnl    = excluded.total_pnl,
            updated_at   = excluded.updated_at
    """, (today, total, wins, losses, wr, round(total_pnl, 2), _now()))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    """Open and return a connection to the SQLite database."""
    return sqlite3.connect(DB_PATH)


def _now() -> str:
    """Return current IST datetime as ISO string (consistent with the rest of the bot)."""
    from utils.helpers import get_ist_time
    return get_ist_time().strftime("%Y-%m-%d %H:%M:%S")
