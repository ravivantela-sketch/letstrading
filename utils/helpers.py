"""
utils/helpers.py — Common helper utilities for LetsTrading bot.
"""
from datetime import datetime, timedelta
import pytz

# Indian Standard Time timezone
IST = pytz.timezone("Asia/Kolkata")


def get_ist_time() -> datetime:
    """Return the current datetime in IST (UTC+5:30)."""
    return datetime.now(IST)


def is_expiry_day() -> bool:
    """
    Return True if today is Wednesday — Bank Nifty's weekly expiry day.
    weekday() returns 0=Mon … 6=Sun, so Wednesday == 2.
    """
    return get_ist_time().weekday() == 2


def is_no_trade_zone() -> bool:
    """
    Return True if the current IST time falls in a restricted zone:
      • 9:15 – 9:20 AM  — opening volatility, avoid entry
      • After 3:15 PM   — closing volatility, avoid new entry
    """
    now = get_ist_time()
    t = now.time()
    morning_start = now.replace(hour=9,  minute=15, second=0, microsecond=0).time()
    morning_end   = now.replace(hour=9,  minute=20, second=0, microsecond=0).time()
    evening_start = now.replace(hour=15, minute=15, second=0, microsecond=0).time()

    if morning_start <= t <= morning_end:
        return True
    if t >= evening_start:
        return True
    return False


def is_market_open() -> bool:
    """
    Return True if the NSE market is currently open:
      • Monday to Friday
      • 9:15 AM – 3:20 PM IST
    """
    now = get_ist_time()
    # weekday: 0=Mon … 4=Fri, 5=Sat, 6=Sun
    if now.weekday() >= 5:
        return False
    t = now.time()
    open_time  = now.replace(hour=9,  minute=15, second=0, microsecond=0).time()
    close_time = now.replace(hour=15, minute=20, second=0, microsecond=0).time()
    return open_time <= t <= close_time


def format_currency(amount: float) -> str:
    """
    Format a number as Indian currency string.
    Example: 48250.0  →  '₹48,250.00'
    """
    return f"₹{amount:,.2f}"


def calculate_percentage_change(old: float, new: float) -> float:
    """
    Calculate percentage change from old to new value.
    Returns 0.0 if old is zero to avoid division by zero.
    """
    if old == 0:
        return 0.0
    return ((new - old) / old) * 100


def get_atm_strike(spot_price: float, step: int = 100) -> int:
    """
    Round a spot price to the nearest ATM (At-The-Money) strike.
    Bank Nifty options are available in multiples of 100.
    Example: 48,267  →  48,300
    """
    return int(round(spot_price / step) * step)


def get_next_expiry_date() -> str:
    """
    Return the next Bank Nifty weekly expiry date (Wednesday) as 'YYYY-MM-DD'.
    If today is Wednesday, return today's date.
    """
    today = get_ist_time().date()
    # weekday 2 == Wednesday
    days_ahead = (2 - today.weekday()) % 7
    # If today is already Wednesday, days_ahead == 0, so we return today
    next_expiry = today + timedelta(days=days_ahead)
    return next_expiry.strftime("%Y-%m-%d")
