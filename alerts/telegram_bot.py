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
TELEGRAM_GET_ME_API = "https://api.telegram.org/bot{token}/getMe"


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
        status = getattr(getattr(exc, "response", None), "status_code", None)
        body = getattr(getattr(exc, "response", None), "text", "")
        if status is not None:
            logger.error(
                "Telegram send failed: %s | status=%s | body=%s",
                config.sanitize_text(exc),
                status,
                config.sanitize_text(body),
            )
        else:
            logger.error("Telegram send failed: %s", config.sanitize_text(exc))
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

    if signal.get("advisory"):
        mode_label = "🧠 <b>ADVISORY Mode</b> (no order execution)"
    else:
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
    note        = signal.get("note",       "")
    rr_ratio    = signal.get("rr_ratio",   "–")
    timestamp   = signal.get("timestamp",  get_ist_time().strftime("%H:%M:%S IST"))

    note_line = f"🧾 Why        : {note}\n" if note else ""

    text = (
        f"{emoji} <b>BANK NIFTY {direction} SIGNAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Strategy   : {strategy}\n"
        f"🎯 Confidence : {confidence:.0f}%\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{note_line}"
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


def send_advisory_update(signal: dict, trade_params: dict = None) -> bool:
    """Send advisory updates for both actionable and WAIT states."""
    advisory_signal = dict(signal)
    advisory_signal["advisory"] = True

    summary = advisory_signal.get("advisory_summary", {})
    action = summary.get("action_text", advisory_signal.get("signal", "WAIT"))
    probability = summary.get("probability", advisory_signal.get("confidence", 0))
    next_trend = summary.get("next_open_trend", "Neutral")
    next_prob = summary.get("next_open_probability", 50)
    simple_reason = summary.get("simple_reason", "No clear setup details yet.")
    notes = summary.get("notes", advisory_signal.get("note", ""))
    risk_text = summary.get("risk_text", "Moderate")
    what_to_do = summary.get("what_to_do", "Wait for clearer confirmation.")
    entry = summary.get("entry", 0)
    sl = summary.get("sl", 0)
    target = summary.get("target", 0)
    rr_ratio = summary.get("rr_ratio", advisory_signal.get("rr_ratio", "1:0"))
    analysis_meta = summary.get("analysis_meta", {})

    instrument = analysis_meta.get("instrument", config.BANK_NIFTY_SYMBOL)
    scope = analysis_meta.get("scope", "Bank Nifty index trend")
    timeframe = analysis_meta.get("timeframe", "30minute candles")
    lookback = analysis_meta.get("lookback", "Last 5 calendar days")
    candles_used = analysis_meta.get("candles_used", 0)
    expiry = analysis_meta.get("expiry", "N/A")
    option_chain_context = analysis_meta.get("option_chain_context", "Not available")
    features = analysis_meta.get("features", "Indicator consensus")

    timestamp = advisory_signal.get("timestamp", get_ist_time().strftime("%H:%M:%S IST"))
    text = (
        "🧠 <b>ADVISORY Recommendation</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Action      : {action}\n"
        f"Probability : {probability:.0f}%\n"
        f"Risk Level  : {risk_text}\n"
        f"Reason      : {simple_reason}\n"
        f"Strategy    : {advisory_signal.get('strategy', 'Combined')}\n"
        f"Notes       : {notes or 'No additional notes'}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Data Checked\n"
        f"Instrument   : {instrument}\n"
        f"Scope        : {scope}\n"
        f"Timeframe    : {timeframe}\n"
        f"Lookback     : {lookback} ({candles_used} candles)\n"
        f"Expiry Focus : Weekly ({expiry})\n"
        f"Option Chain : {option_chain_context}\n"
        f"Features     : {features}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Next Open Bias : {next_trend} ({next_prob:.0f}%)\n"
        f"Plan           : {what_to_do}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Entry/SL/TGT : {format_currency(entry)} / {format_currency(sl)} / {format_currency(target)}\n"
        f"R:R          : {rr_ratio}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⏰ Time : {timestamp}\n"
        "No order execution in advisory mode."
    )
    return _send_message(text)


def telegram_self_test() -> dict:
    """Validate Telegram token/chat configuration and send a test message."""
    token = config.TELEGRAM_BOT_TOKEN
    chat_id = config.TELEGRAM_CHAT_ID

    if not token:
        return {
            "status": "error",
            "message": "TELEGRAM_BOT_TOKEN is missing in .env.",
        }
    if not chat_id:
        return {
            "status": "error",
            "message": "TELEGRAM_CHAT_ID is missing in .env.",
        }

    if ":" not in token:
        return {
            "status": "error",
            "message": "TELEGRAM_BOT_TOKEN format looks invalid.",
        }

    if not (chat_id.lstrip("-").isdigit() or chat_id.startswith("@")):
        return {
            "status": "error",
            "message": "TELEGRAM_CHAT_ID should be numeric (user/group) or @channelusername.",
        }

    try:
        me_resp = requests.get(TELEGRAM_GET_ME_API.format(token=token), timeout=10)
        me_resp.raise_for_status()
        me_data = me_resp.json()
        if not me_data.get("ok"):
            return {
                "status": "error",
                "message": "Telegram token validation failed in getMe response.",
            }
    except requests.RequestException as exc:
        return {
            "status": "error",
            "message": f"Token check failed: {config.sanitize_text(exc)}",
        }

    test_text = (
        "✅ LetsTrading Telegram test successful.\n"
        "If you can read this, advisory and trade alerts can be delivered."
    )

    payload = {
        "chat_id": chat_id,
        "text": test_text,
    }
    try:
        send_resp = requests.post(
            TELEGRAM_API.format(token=token),
            json=payload,
            timeout=10,
        )
        send_resp.raise_for_status()
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        body = getattr(getattr(exc, "response", None), "text", "")
        if status == 400:
            return {
                "status": "error",
                "message": (
                    "Message send failed with 400. Most likely chat_id is wrong, "
                    "or the bot was not started/added to the target chat. "
                    f"Body: {config.sanitize_text(body)}"
                ),
            }
        return {
            "status": "error",
            "message": f"Message send failed: {config.sanitize_text(exc)}",
        }

    return {
        "status": "ok",
        "message": "Telegram token and chat_id are valid; test message sent successfully.",
    }


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
