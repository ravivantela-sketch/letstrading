"""
main.py — LetsTrading Bot entry point.

Usage:
  python main.py --mode paper    # Paper trading (default, safe)
  python main.py --mode live     # Live trading
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
from alerts.telegram_bot import send_signal_alert, send_daily_summary, send_error_alert, send_startup_alert
from utils.helpers      import get_ist_time, is_expiry_day

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
        logger.error("set_orb failed: %s", exc)
        send_error_alert(f"ORB setup failed: {exc}")


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
    global broker

    if not is_market_hours():
        logger.debug("Market closed — skipping signal check")
        return

    try:
        # ---- 1. Daily loss limit ----------------------------------------
        trades_today = get_trades_today()
        if check_daily_loss_limit(trades_today, config.CAPITAL):
            logger.warning("Daily loss limit reached — no new trades today")
            return

        # ---- 2. Fetch data & compute indicators -------------------------
        df = broker.get_historical_data(config.INSTRUMENT_KEY, interval="15minute", days_back=5)
        if df is None or len(df) < 30:
            logger.warning("Insufficient historical data")
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

        # ---- 4. Log signal to DB ----------------------------------------
        log_signal(signal)

        # ---- 5. If actionable — alert + trade ---------------------------
        if signal["signal"] in ("BUY", "SELL"):
            current_price = float(df.iloc[-1]["close"])
            params        = calculate_trade_params(signal, current_price, config.CAPITAL)

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
            logger.info("Order response: %s", order_resp)

    except Exception as exc:
        logger.error("run_signal_check error: %s", exc, exc_info=True)
        send_error_alert(f"Signal check error: {exc}")


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
        logger.error("end_of_day error: %s", exc)

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
        choices=["paper", "live", "backtest"],
        default="paper",
        help="Trading mode (default: paper)",
    )
    args = parser.parse_args()
    mode = args.mode

    # Override config mode if passed via CLI
    if mode in ("paper", "live"):
        os.environ["TRADING_MODE"] = mode
        config.TRADING_MODE        = mode

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

    # ---- Main loop --------------------------------------------------------
    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user (KeyboardInterrupt)")


if __name__ == "__main__":
    main()
