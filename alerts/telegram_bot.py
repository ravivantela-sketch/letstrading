"""
alerts/telegram_bot.py — Telegram notifications for LetsTrading.

Sends nicely formatted signal alerts, daily summaries, errors, and
startup messages to the configured Telegram chat.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import requests
import logging

import config
from utils.helpers import format_currency, get_ist_time

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


# ---------------------------------------------------------------------------
# Core send helper
# ---------------------------------------------------------------------------

def _send_message(text: str) -> bool:
    """
    Send a Telegram message using HTML parse mode.
    Returns True on success, False on failure (so the bot can continue).
    """
    token   = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID

    if not token or not chat_id:
        logger.debug("Telegram not configured — skipping message")
        return False

    url     = TELEGRAM_API.format(token=token)
    payload = {
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Telegram send failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Signal alert
# ---------------------------------------------------------------------------

def send_signal_alert(signal: dict, trade_params: dict = None) -> bool:
    """
    Send a formatted BUY/SELL signal alert.
    Silently skips WAIT signals — no message is sent.

    Parameters
    ----------
    signal       : signal dict from engine/signals.py
    trade_params : optional dict from engine/risk.py calculate_trade_params()
    """
    direction = signal.get("signal", "WAIT")
    if direction == "WAIT":
        return False

    mode_label = "⚠️ Paper Trade Mode" if config.TRADING_MODE.lower() != "live" \
                 else "🔴 <b>LIVE Trade Mode</b>"

    emoji = "🟢" if direction == "BUY" else "🔴"

    # Trade parameters
    entry      = format_currency(signal.get("entry",  0))
    sl_price   = signal.get("sl",     0)
    tgt_price  = signal.get("target", 0)
    ep         = signal.get("entry",  1)

    sl_pct  = ((sl_price  - ep) / ep * 100) if ep else 0
    tgt_pct = ((tgt_price - ep) / ep * 100) if ep else 0

    sl_str  = f"{format_currency(sl_price)} ({sl_pct:+.1f}%)"
    tgt_str = f"{format_currency(tgt_price)} ({tgt_pct:+.1f}%)"

    qty_str = ""
    if trade_params:
        qty  = trade_params.get("qty",  15)
        lots = trade_params.get("lots",  1)
        qty_str = f"\n💰 Qty        : {qty} ({lots} lot{'s' if lots > 1 else ''})"

    confidence  = signal.get("confidence", 0)
    strategy    = signal.get("strategy",   "Unknown")
    rr_ratio    = signal.get("rr_ratio",   "–")
    timestamp   = signal.get("timestamp",  get_ist_time().strftime("%H:%M:%S IST"))

    text = (
        f"{emoji} <b>BANK NIFTY {direction} SIGNAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Strategy   : {strategy}\n"
        f"🎯 Confidence : {confidence:.0f}%\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 Entry     : {entry}\n"
        f"🛑 Stop Loss  : {sl_str}\n"
        f"✅ Target     : {tgt_str}\n"
        f"⚖️  Risk:Reward : {rr_ratio}"
        f"{qty_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ Time : {timestamp}\n"
        f"{mode_label}"
    )
    return _send_message(text)


# ---------------------------------------------------------------------------
# Daily summary
# ---------------------------------------------------------------------------

def send_daily_summary(trades: list, total_pnl: float) -> bool:
    """
    Send an end-of-day trade summary to Telegram.

    Parameters
    ----------
    trades    : list of trade dicts (each with 'pnl' key)
    total_pnl : total P&L for the day (float)
    """
    total  = len(trades)
    wins   = sum(1 for t in trades if t.get("pnl", 0) > 0)
    losses = total - wins
    wr     = (wins / total * 100) if total > 0 else 0

    pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
    date_str  = get_ist_time().strftime("%d %b %Y")

    text = (
        f"📅 <b>Daily Summary — {date_str}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Total Trades : {total}\n"
        f"✅ Wins         : {wins}\n"
        f"❌ Losses       : {losses}\n"
        f"🎯 Win Rate     : {wr:.1f}%\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{pnl_emoji} Today P&amp;L : <b>{format_currency(total_pnl)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Mode: {'Paper 📄' if config.TRADING_MODE.lower() != 'live' else 'Live 🔴'}"
    )
    return _send_message(text)


# ---------------------------------------------------------------------------
# Error alert
# ---------------------------------------------------------------------------

def send_error_alert(error_msg: str) -> bool:
    """Send a brief error notification."""
    text = (
        f"🚨 <b>LetsTrading ERROR</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<code>{error_msg}</code>\n"
        f"⏰ {get_ist_time().strftime('%H:%M:%S IST')}"
    )
    return _send_message(text)


# ---------------------------------------------------------------------------
# Startup alert
# ---------------------------------------------------------------------------

def send_startup_alert(mode: str) -> bool:
    """Send a startup confirmation message."""
    mode_emoji = "📄" if mode.lower() != "live" else "🔴"
    text = (
        f"🤖 <b>LetsTrading Bot Started</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{mode_emoji} Mode     : <b>{mode.upper()}</b>\n"
        f"💰 Capital  : {format_currency(config.CAPITAL)}\n"
        f"⏱  Interval : every {config.SIGNAL_INTERVAL} minutes\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ Started at {get_ist_time().strftime('%H:%M:%S IST')}\n"
        f"📅 {get_ist_time().strftime('%d %b %Y')}"
    )
    return _send_message(text)
