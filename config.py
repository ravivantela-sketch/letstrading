"""
config.py — Central configuration for LetsTrading
All settings loaded from .env file.
"""
import os
from typing import Iterable

from dotenv import load_dotenv

load_dotenv()

# Upstox API
UPSTOX_API_KEY      = os.getenv("UPSTOX_API_KEY", "")
UPSTOX_API_SECRET   = os.getenv("UPSTOX_API_SECRET", "")
UPSTOX_REDIRECT_URI = os.getenv("UPSTOX_REDIRECT_URI", "http://127.0.0.1:5000/callback")
UPSTOX_ACCESS_TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# Trading
TRADING_MODE       = os.getenv("TRADING_MODE", "paper")
CAPITAL            = float(os.getenv("CAPITAL", 100000))
MAX_RISK_PER_TRADE = float(os.getenv("MAX_RISK_PER_TRADE", 0.01))
MAX_DAILY_LOSS     = float(os.getenv("MAX_DAILY_LOSS", 0.02))

# Bank Nifty
BANK_NIFTY_LOT_SIZE = 15
INSTRUMENT_KEY      = "NSE_INDEX|Nifty Bank"
BANK_NIFTY_SYMBOL   = "BANKNIFTY"

# Market Hours IST
MARKET_OPEN          = "09:15"
MARKET_CLOSE         = "15:20"
NO_TRADE_MORNING_END = "09:20"
NO_TRADE_EVENING     = "15:15"

# Indicator Settings
EMA_FAST              = 9
EMA_SLOW              = 21
EMA_MID               = 50
EMA_LONG              = 200
EMA_5                 = 5
RSI_PERIOD            = 14
BB_PERIOD             = 20
BB_STD                = 2.0
SUPERTREND_PERIOD     = 10
SUPERTREND_MULTIPLIER = 3
MACD_FAST             = 12
MACD_SLOW             = 26
MACD_SIGNAL           = 9

# Signal Thresholds
RSI_BULL_THRESHOLD   = 60
RSI_BEAR_THRESHOLD   = 40
PCR_BULL_THRESHOLD   = 0.8
PCR_BEAR_THRESHOLD   = 1.2
VIX_LOW              = 13
VIX_HIGH             = 18
BB_SQUEEZE_THRESHOLD = 0.015

# Risk Management
DEFAULT_SL_PCT     = 0.005
DEFAULT_TARGET_PCT = 0.015
SIGNAL_INTERVAL    = 5


def _defined_secrets() -> tuple[str, ...]:
	return tuple(
		value for value in (
			UPSTOX_API_KEY,
			UPSTOX_API_SECRET,
			UPSTOX_ACCESS_TOKEN,
			TELEGRAM_BOT_TOKEN,
			TELEGRAM_CHAT_ID,
		)
		if value
	)


def sanitize_text(text: object) -> str:
	"""Redact configured secret values before logging or sending alerts."""
	sanitized = str(text)
	for secret in _defined_secrets():
		sanitized = sanitized.replace(secret, "[REDACTED]")
	return sanitized


def missing_credentials(mode: str) -> list[str]:
	"""Return the missing required credentials for the selected mode."""
	required: list[tuple[str, str]] = []

	if mode == "live":
		required.extend([
			("UPSTOX_API_KEY", UPSTOX_API_KEY),
			("UPSTOX_API_SECRET", UPSTOX_API_SECRET),
			("UPSTOX_ACCESS_TOKEN", UPSTOX_ACCESS_TOKEN),
		])

	return [name for name, value in required if not value]


def safe_order_response(data: object) -> dict:
	"""Return only non-sensitive order response fields for logs."""
	if not isinstance(data, dict):
		return {"summary": sanitize_text(data)}

	allowed_keys: Iterable[str] = (
		"status",
		"order_id",
		"mode",
		"message",
		"symbol",
		"qty",
		"type",
		"data",
	)
	safe_data: dict = {}
	for key in allowed_keys:
		if key not in data:
			continue
		value = data[key]
		if isinstance(value, dict):
			nested = {
				nested_key: sanitize_text(nested_value)
				for nested_key, nested_value in value.items()
				if nested_key in {"order_id", "status", "message"}
			}
			if nested:
				safe_data[key] = nested
			continue
		safe_data[key] = sanitize_text(value)

	return safe_data
