"""
main.py — LetsTrading Bot entry point.

Usage:
  python main.py --mode paper    # Paper trading (default, safe)
    python main.py --mode advisory # Real-data advisory, no order execution
  python main.py --mode live     # Live trading
    python main.py --mode telegram-test # Validate Telegram setup
  python main.py --mode backtest # Run backtest and exit

The bot:
  1. Initialises the SQLite database
  2. Connects to the Upstox broker (paper or live)
  3. Sends a Telegram startup notification
  4. Every 5 minutes checks signals and optionally places orders
  5. At 15:30 sends a daily summary and resets state
"""
import argparse
import logging
import os
import sys
import schedule
import time
from datetime import datetime

# Ensure project root is on the path when run directly
sys.path.insert(0, os.path.dirname(__file__))

import config
from data.database      import init_db, log_signal, log_trade, get_trades_today, save_daily_summary
from broker.upstox_api  import UpstoxBroker
from engine.indicators  import calculate_all
from engine.signals     import combined_signal
from engine.risk        import calculate_trade_params, check_daily_loss_limit, is_market_hours
from alerts.telegram_bot import (
    send_signal_alert,
    telegram_self_test,
    send_daily_summary,
    send_error_alert,
    send_startup_alert,
    send_advisory_update,
)
from utils.helpers      import get_ist_time, is_expiry_day, get_next_expiry_date

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/trading_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
broker: UpstoxBroker = None
ORB_HIGH: float      = 0.0
ORB_LOW:  float      = 0.0
ORB_SET:  bool       = False
RUN_MODE: str         = "paper"
LAST_ADVISORY_SIGNATURE: str = ""


def _parse_rr(rr_ratio: str) -> float:
    """Convert rr_ratio like '1:2.5' into numeric reward/risk value."""
    try:
        right = rr_ratio.split(":", 1)[1]
        return float(right)
    except Exception:
        return 0.0


def _next_open_trend(df) -> dict:
    """Estimate next-session directional bias in plain language."""
    if df is None or df.empty:
        return {
            "label": "Neutral",
            "probability": 50,
            "reason": "Not enough recent data.",
        }

    last = df.iloc[-1]
    close = float(last.get("close", 0))
    ema21 = float(last.get("ema21", close))
    ema50 = float(last.get("ema50", close))
    vwap = float(last.get("vwap", close))
    rsi = float(last.get("rsi", 50))

    bull = 0
    bear = 0

    if close > ema21:
        bull += 1
    else:
        bear += 1

    if ema21 > ema50:
        bull += 1
    else:
        bear += 1

    if close > vwap:
        bull += 1
    else:
        bear += 1

    if rsi >= 55:
        bull += 1
    elif rsi <= 45:
        bear += 1

    if bull > bear:
        probability = int(min(85, 50 + (bull - bear) * 10))
        return {
            "label": "Bullish",
            "probability": probability,
            "reason": "Price and trend indicators are mostly above their support levels.",
        }

    if bear > bull:
        probability = int(min(85, 50 + (bear - bull) * 10))
        return {
            "label": "Bearish",
            "probability": probability,
            "reason": "Price and trend indicators are mostly below resistance levels.",
        }

    return {
        "label": "Sideways",
        "probability": 55,
        "reason": "Signals are mixed, so trend direction is not clear yet.",
    }


def _build_advisory_summary(signal: dict, params: dict, df, option_chain_note: str) -> dict:
    """Create a non-technical advisory summary with clear action and probability."""
    direction = signal.get("signal", "WAIT")
    confidence = int(round(float(signal.get("confidence", 0))))
    rr_value = _parse_rr(signal.get("rr_ratio", "1:0"))
    forecast = _next_open_trend(df)

    if direction == "BUY":
        action_text = "Possible BUY setup"
        simple_reason = "Momentum is leaning upward based on the active strategy checks."
    elif direction == "SELL":
        action_text = "Possible SELL setup"
        simple_reason = "Momentum is leaning downward based on the active strategy checks."
    else:
        action_text = "WAIT - no clear trade setup"
        simple_reason = "Current conditions are mixed, so skipping entry is safer."

    risk_text = "Moderate"
    if rr_value >= 2.5 and confidence >= 70:
        risk_text = "Lower"
    elif rr_value < 1.5 or confidence < 55:
        risk_text = "Higher"

    notes = [signal.get("note", "")]
    if option_chain_note:
        notes.append(option_chain_note)

    candle_count = len(df) if df is not None else 0
    analysis_meta = {
        "instrument": f"{config.BANK_NIFTY_SYMBOL} ({config.INSTRUMENT_KEY})",
        "scope": "Bank Nifty index trend with weekly expiry option-chain context",
        "timeframe": "30minute candles",
        "lookback": "Last 5 calendar days",
        "candles_used": candle_count,
        "expiry": get_next_expiry_date(),
        "option_chain_context": "Included" if option_chain_note else "Not available",
        "features": "EMA(5/9/21/50/200), RSI, VWAP, Bollinger Bands, Supertrend, MACD, strategy consensus",
    }

    return {
        "action_text": action_text,
        "probability": max(35, min(90, confidence if direction != "WAIT" else forecast["probability"])),
        "simple_reason": simple_reason,
        "risk_text": risk_text,
        "next_open_trend": forecast["label"],
        "next_open_probability": forecast["probability"],
        "next_open_reason": forecast["reason"],
        "notes": " | ".join(n for n in notes if n),
        "what_to_do": (
            "Watch for confirmation after market opens; do not execute immediately."
            if direction == "WAIT"
            else "Use strict stop-loss and only act if price stays aligned with this direction."
        ),
        "entry": params.get("entry", 0),
        "sl": params.get("sl", 0),
        "target": params.get("target", 0),
        "rr_ratio": params.get("rr_ratio", signal.get("rr_ratio", "1:0")),
        "analysis_meta": analysis_meta,
    }


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def initialize_broker() -> UpstoxBroker:
    """
    Create and return a configured UpstoxBroker instance.
    Uses credentials from config (loaded from .env).
    """
    return UpstoxBroker(
        api_key      = config.UPSTOX_API_KEY,
        api_secret   = config.UPSTOX_API_SECRET,
        access_token = config.UPSTOX_ACCESS_TOKEN,
    )


def upstox_api_test() -> dict:
    """
    Test Upstox API connectivity with live quote and historical data.
    Returns dict with status and diagnostic info.
    """
    logger.info("Testing Upstox API connectivity...")
    
    if not config.UPSTOX_ACCESS_TOKEN:
        logger.error("UPSTOX_ACCESS_TOKEN not configured in .env")
        return {
            "status": "error",
            "message": "UPSTOX_ACCESS_TOKEN is empty or missing from .env",
            "details": {
                "live_quote": "SKIPPED (no token)",
                "historical_candles": "SKIPPED (no token)",
            }
        }
    
    test_broker = initialize_broker()
    details = {}
    
    # Step 1: Test live quote
    logger.info("Step 1: Testing live quote for %s...", config.INSTRUMENT_KEY)
    try:
        quote = test_broker.get_live_quote(config.INSTRUMENT_KEY)
        if quote and quote.get("close", 0) > 0:
            details["live_quote"] = f"OK — LTP: {quote.get('ltp', 'N/A')}, Close: {quote.get('close', 'N/A')}"
            logger.info("✓ Live quote successful: %s", details["live_quote"])
        elif not quote or quote.get("close", 0) == 0:
            details["live_quote"] = "WARNING: Dummy quote returned (market closed or API unavailable)"
            logger.warning("Live quote returned dummy data (market may be closed)")
        else:
            details["live_quote"] = f"PARTIAL: {quote}"
    except Exception as exc:
        details["live_quote"] = f"ERROR: {str(exc)[:200]}"
        logger.error("✗ Live quote failed: %s", exc)
    
    # Step 2: Test historical candles
    logger.info("Step 2: Testing historical candles for %s...", config.INSTRUMENT_KEY)
    try:
        df = test_broker.get_historical_data(config.INSTRUMENT_KEY, interval="30minute", days_back=5)
        if df is not None and not df.empty and df.iloc[-1].get("close", 0) > 0:
            latest_close = df.iloc[-1].get("close", "N/A")
            candle_count = len(df)
            details["historical_candles"] = f"OK — {candle_count} candles, latest close: {latest_close}"
            logger.info("✓ Historical candles successful: %s", details["historical_candles"])
        elif df is not None and not df.empty:
            details["historical_candles"] = f"PARTIAL: {len(df)} dummy candles (real data may not be available)"
            logger.warning("Historical candles returned dummy data")
        else:
            details["historical_candles"] = "ERROR: No candle data returned"
    except Exception as exc:
        details["historical_candles"] = f"ERROR: {str(exc)[:200]}"
        logger.error("✗ Historical candles failed: %s", exc)
    
    # Determine overall status
    live_ok = "OK" in details["live_quote"]
    hist_ok = "OK" in details["historical_candles"]
    
    if live_ok and hist_ok:
        overall_status = "ok"
        summary = "Upstox API is working correctly"
    elif live_ok or hist_ok:
        overall_status = "partial"
        summary = "Some Upstox API calls succeeded (market may be closed)"
    else:
        overall_status = "error"
        summary = "Upstox API connectivity failed — check token and network"
    
    logger.info("UPSTOX TEST SUMMARY: %s", summary)
    
    return {
        "status": overall_status,
        "message": summary,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Opening Range Breakout setup
# ---------------------------------------------------------------------------

def set_orb() -> None:
    """
    Set the Opening Range high/low from the first 3 candles of the day.
    Scheduled to run at 9:31 AM so that 3 × 1-min candles are available.
    """
    global ORB_HIGH, ORB_LOW, ORB_SET
    if broker is None:
        return

    try:
        df = broker.get_historical_data(config.INSTRUMENT_KEY, interval="1minute", days_back=1)
        today_str = get_ist_time().strftime("%Y-%m-%d")
        today_df  = df[df["timestamp"].dt.strftime("%Y-%m-%d") == today_str]

        if len(today_df) >= 3:
            first3    = today_df.head(3)
            ORB_HIGH  = float(first3["high"].max())
            ORB_LOW   = float(first3["low"].min())
            ORB_SET   = True
            logger.info("ORB set — High: %.2f  Low: %.2f", ORB_HIGH, ORB_LOW)
        else:
            logger.warning("Not enough candles to set ORB (%d candles)", len(today_df))
    except Exception as exc:
        safe_error = config.sanitize_text(exc)
        logger.error("set_orb failed: %s", safe_error)
        send_error_alert(f"ORB setup failed: {safe_error}")


# ---------------------------------------------------------------------------
# Main signal check loop
# ---------------------------------------------------------------------------

def run_signal_check() -> None:
    """
    Core loop — called every SIGNAL_INTERVAL minutes by the scheduler.

    Steps:
      1. Check market hours
      2. Check daily loss limit
      3. Fetch live data and calculate indicators
      4. Generate combined signal
      5. Log signal to DB
      6. If actionable: send alert, log trade, place order
    """
    global broker, LAST_ADVISORY_SIGNATURE

    advisory_mode = RUN_MODE == "advisory"

    if not advisory_mode and not is_market_hours():
        logger.debug("Market closed — skipping signal check")
        return

    try:
        # ---- 1. Daily loss limit ----------------------------------------
        if not advisory_mode:
            trades_today = get_trades_today()
            if check_daily_loss_limit(trades_today, config.CAPITAL):
                logger.warning("Daily loss limit reached — no new trades today")
                return

        # ---- 2. Fetch data & compute indicators -------------------------
        df = broker.get_historical_data(config.INSTRUMENT_KEY, interval="30minute", days_back=5)
        logger.debug("Received %d candles from API", len(df) if df is not None else 0)
        if df is None or len(df) < 20:
            logger.warning("Insufficient historical data (received: %d, need: 20)", len(df) if df is not None else 0)
            return

        df = calculate_all(df)

        # Placeholder VIX / PCR / OI — in production fetch from NSE/Upstox
        vix       = 15.0
        pcr       = 1.0
        oi_change = 0.0

        # ---- 3. Generate signal -----------------------------------------
        signal = combined_signal(
            df         = df,
            vix        = vix,
            pcr        = pcr,
            oi_change  = oi_change,
            orb_high   = ORB_HIGH,
            orb_low    = ORB_LOW,
            is_expiry  = is_expiry_day(),
        )
        logger.info("Signal: %s  |  strategy: %s  |  confidence: %.0f%%",
                    signal["signal"], signal.get("strategy", "?"), signal.get("confidence", 0))
        if signal.get("note"):
            logger.info("Why this signal: %s", signal.get("note"))

        # ---- 4. Log signal to DB ----------------------------------------
        log_signal(signal)

        option_chain_note = ""
        if advisory_mode:
            try:
                expiry = get_next_expiry_date()
                oc_df = broker.get_option_chain(expiry)
                if oc_df is not None and not oc_df.empty:
                    ce_oi = float(oc_df["call_oi"].sum())
                    pe_oi = float(oc_df["put_oi"].sum())
                    total_oi = ce_oi + pe_oi
                    if total_oi > 0:
                        ce_share = (ce_oi / total_oi) * 100
                        pe_share = (pe_oi / total_oi) * 100
                        option_chain_note = f"OI mix CE={ce_share:.1f}% PE={pe_share:.1f}%"
            except Exception as exc:
                logger.debug("Option-chain context unavailable: %s", config.sanitize_text(exc))

        if advisory_mode and signal["signal"] == "WAIT":
            wait_params = {"entry": 0, "sl": 0, "target": 0, "rr_ratio": "1:0"}
            wait_summary = _build_advisory_summary(signal, wait_params, df, option_chain_note)
            wait_signal = dict(signal)
            wait_signal["advisory_summary"] = wait_summary
            signature = f"{signal.get('signal')}|{signal.get('strategy')}|{signal.get('note')}"
            if signature != LAST_ADVISORY_SIGNATURE:
                send_advisory_update(wait_signal)
                LAST_ADVISORY_SIGNATURE = signature
            logger.info("ADVISORY WAIT: %s", signal.get("note", "No setup"))
            return

        # ---- 5. If actionable — alert + trade ---------------------------
        if signal["signal"] in ("BUY", "SELL"):
            current_price = float(df.iloc[-1]["close"])
            params        = calculate_trade_params(signal, current_price, config.CAPITAL)

            if advisory_mode:
                advisory_signal = dict(signal)
                advisory_signal["advisory"] = True
                advisory_note_parts = [signal.get("note", "")]
                if option_chain_note:
                    advisory_note_parts.append(option_chain_note)
                advisory_signal["note"] = " | ".join(part for part in advisory_note_parts if part)
                advisory_signal["advisory_summary"] = _build_advisory_summary(
                    advisory_signal,
                    params,
                    df,
                    option_chain_note,
                )
                logger.info(
                    "ADVISORY: %s %s | entry=%.2f sl=%.2f tgt=%.2f | %s",
                    advisory_signal["signal"],
                    config.BANK_NIFTY_SYMBOL,
                    params["entry"],
                    params["sl"],
                    params["target"],
                    advisory_signal.get("note", "No reason provided"),
                )
                send_advisory_update(advisory_signal, params)
                LAST_ADVISORY_SIGNATURE = (
                    f"{advisory_signal.get('signal')}|"
                    f"{advisory_signal.get('strategy')}|"
                    f"{advisory_signal.get('note')}"
                )
                return

            send_signal_alert(signal, params)

            # Log the trade (open status, no P&L yet)
            trade_record = {
                "timestamp":   get_ist_time().strftime("%Y-%m-%d %H:%M:%S"),
                "direction":   signal["signal"],
                "entry_price": params["entry"],
                "exit_price":  0,
                "qty":         params["qty"],
                "lots":        params["lots"],
                "pnl":         0,
                "status":      "OPEN",
                "order_id":    "",
                "strategy":    signal.get("strategy", ""),
            }
            log_trade(trade_record)

            # Place order (paper or live based on config)
            order_resp = broker.place_order(
                tradingsymbol    = config.BANK_NIFTY_SYMBOL,
                qty              = params["qty"],
                transaction_type = signal["signal"],
            )
            logger.info("Order response: %s", config.safe_order_response(order_resp))

    except Exception as exc:
        safe_error = config.sanitize_text(exc)
        logger.error("run_signal_check error: %s", safe_error)
        send_error_alert(f"Signal check error: {safe_error}")


# ---------------------------------------------------------------------------
# End of day
# ---------------------------------------------------------------------------

def end_of_day() -> None:
    """
    Run at 15:30 IST:
      • Save daily summary to DB
      • Send Telegram daily summary
      • Reset ORB state for next day
    """
    global ORB_HIGH, ORB_LOW, ORB_SET
    logger.info("End of day — processing summary")

    try:
        trades    = get_trades_today()
        total_pnl = sum(t.get("pnl", 0) for t in trades)
        save_daily_summary(trades, total_pnl)
        send_daily_summary(trades, total_pnl)
    except Exception as exc:
        logger.error("end_of_day error: %s", config.sanitize_text(exc))

    # Reset ORB for next session
    ORB_HIGH = 0.0
    ORB_LOW  = 0.0
    ORB_SET  = False


# ---------------------------------------------------------------------------
# Backtest mode
# ---------------------------------------------------------------------------

def run_backtest_mode() -> None:
    """Run a quick backtest and print the report to console."""
    from backtest.backtester import run_backtest, print_backtest_report
    logger.info("Running backtest...")
    results = run_backtest(strategy="trend_following")
    print_backtest_report(results)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LetsTrading Bot — Bank Nifty Options")
    parser.add_argument(
        "--mode",
        choices=["paper", "advisory", "live", "backtest", "telegram-test", "upstox-test"],
        default="paper",
        help="Trading mode (default: paper)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run signal check once and exit (useful for advisory mode testing)",
    )
    args = parser.parse_args()
    mode = args.mode
    run_once = args.once

    global RUN_MODE
    RUN_MODE = mode

    # Override config mode for broker execution behavior.
    # Advisory runs through paper execution path but still uses available live data.
    if mode == "advisory":
        config.TRADING_MODE = "paper"
    elif mode in ("paper", "live"):
        config.TRADING_MODE = mode

    if mode == "telegram-test":
        result = telegram_self_test()
        status = result.get("status", "error").upper()
        logger.info("Telegram self-test result: %s", status)
        logger.info("Details: %s", result.get("message", "No details"))
        return

    if mode == "upstox-test":
        result = upstox_api_test()
        status = result.get("status", "error").upper()
        logger.info("Upstox API test result: %s", status)
        logger.info("Summary: %s", result.get("message", "No details"))
        for key, value in result.get("details", {}).items():
            logger.info("  %s: %s", key, value)
        return

    missing_mode = "live" if mode == "live" else "paper"
    missing = config.missing_credentials(missing_mode)
    if missing:
        missing_str = ", ".join(missing)
        raise SystemExit(
            f"Missing required configuration for {mode} mode: {missing_str}. "
            "Populate your local .env file and try again."
        )

    logger.info("=== LetsTrading Bot starting in %s mode ===", mode.upper())

    if mode == "backtest":
        run_backtest_mode()
        return

    # ---- Initialise -------------------------------------------------------
    init_db()

    global broker
    broker = initialize_broker()

    send_startup_alert(mode)

    # ---- Scheduler --------------------------------------------------------
    schedule.every(config.SIGNAL_INTERVAL).minutes.do(run_signal_check)
    schedule.every().day.at("09:31").do(set_orb)
    schedule.every().day.at("15:30").do(end_of_day)

    logger.info(
        "Scheduler started — signals every %d min, ORB at 09:31, EOD at 15:30",
        config.SIGNAL_INTERVAL,
    )

    # Run once immediately on startup
    run_signal_check()
    
    # If --once flag provided, exit after first check
    if run_once:
        logger.info("--once mode: exiting after signal check")
        return

    # ---- Main loop --------------------------------------------------------
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt)")


if __name__ == "__main__":
    main()
