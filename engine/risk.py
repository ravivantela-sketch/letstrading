"""
engine/risk.py — Position sizing and risk management for LetsTrading.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config
from utils.helpers import is_no_trade_zone, is_market_open


def calculate_position_size(
    capital: float,
    risk_pct: float,
    entry: float,
    sl: float,
) -> int:
    """
    Calculate the number of lots to trade given a risk per trade.

    Logic:
      risk_amount   = capital * risk_pct           (e.g. ₹1,000 for 1% risk)
      risk_per_unit = abs(entry - sl)              (e.g. ₹50 per unit)
      raw_qty       = risk_amount / risk_per_unit  (e.g. 20 units)
      lots          = round raw_qty to nearest lot size (15)
      qty           = lots * BANK_NIFTY_LOT_SIZE

    Returns the final quantity (always a multiple of lot size, minimum 1 lot).
    """
    lot_size    = config.BANK_NIFTY_LOT_SIZE
    risk_amount = capital * risk_pct
    risk_per_unit = abs(entry - sl)

    if risk_per_unit == 0:
        return lot_size  # default to 1 lot if SL equals entry

    raw_qty = risk_amount / risk_per_unit

    # Round to nearest lot size (minimum 1 lot)
    lots = max(1, round(raw_qty / lot_size))
    return lots * lot_size


def calculate_trade_params(
    signal: dict,
    current_price: float,
    capital: float,
) -> dict:
    """
    Derive all trade parameters from a signal dict.

    Returns a dict with:
      entry, sl, target, qty, lots, risk_amount, reward, rr_ratio
    """
    direction = signal.get("signal", "BUY")
    entry = signal.get("entry", current_price)
    sl    = signal.get("sl",    entry * (1 - config.DEFAULT_SL_PCT)     if direction == "BUY"
                                else entry * (1 + config.DEFAULT_SL_PCT))
    target = signal.get("target", entry * (1 + config.DEFAULT_TARGET_PCT) if direction == "BUY"
                                  else entry * (1 - config.DEFAULT_TARGET_PCT))

    qty         = calculate_position_size(capital, config.MAX_RISK_PER_TRADE, entry, sl)
    lots        = qty // config.BANK_NIFTY_LOT_SIZE
    risk_amount = abs(entry - sl) * qty
    reward      = abs(target - entry) * qty

    risk_unit   = abs(entry - sl)
    reward_unit = abs(target - entry)
    rr_ratio    = f"1:{round(reward_unit / risk_unit, 1)}" if risk_unit > 0 else "1:0"

    return {
        "entry":       round(entry,  2),
        "sl":          round(sl,     2),
        "target":      round(target, 2),
        "qty":         qty,
        "lots":        lots,
        "risk_amount": round(risk_amount, 2),
        "reward":      round(reward, 2),
        "rr_ratio":    rr_ratio,
    }


def check_daily_loss_limit(
    trades_today: list,
    capital: float,
    max_loss_pct: float = None,
) -> bool:
    """
    Return True if today's cumulative P&L has breached the daily loss limit.
    Each trade dict is expected to have a 'pnl' key.

    Example:
      trades_today = [{"pnl": -500}, {"pnl": -300}]
      If total loss > capital * max_loss_pct  → True (stop trading)
    """
    if max_loss_pct is None:
        max_loss_pct = config.MAX_DAILY_LOSS

    total_pnl = sum(t.get("pnl", 0) for t in trades_today)
    max_loss  = -abs(capital * max_loss_pct)  # e.g. -2000 for 2% of ₹1L
    return total_pnl <= max_loss


def is_market_hours() -> bool:
    """
    Convenience wrapper — True if the market is currently open (9:15–15:20 IST,
    Monday–Friday).  Delegates to utils.helpers.is_market_open().
    """
    return is_market_open()
