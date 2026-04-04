"""
config.py — Central configuration for LetsTrading
All settings loaded from .env file.
"""
import os
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
