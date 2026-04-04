"""
engine/indicators.py — Technical indicator calculations for LetsTrading.

All functions accept a pandas DataFrame with at minimum these OHLCV columns:
  open, high, low, close, volume

They return either a Series (single indicator) or an enriched DataFrame.
"""
import pandas as pd
import numpy as np

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config


# ---------------------------------------------------------------------------
# EMA — Exponential Moving Average
# ---------------------------------------------------------------------------

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """
    Calculate EMA using pandas ewm (exponentially-weighted mean).
    adjust=False gives the standard recursive EMA formula used on trading platforms.
    """
    return series.ewm(span=period, adjust=False).mean()


# ---------------------------------------------------------------------------
# RSI — Relative Strength Index
# ---------------------------------------------------------------------------

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate RSI (Wilder's Smoothing).

    Bank Nifty thresholds used in this bot:
      • RSI > 60  →  bullish momentum (use RSI_BULL_THRESHOLD)
      • RSI < 40  →  bearish momentum (use RSI_BEAR_THRESHOLD)
    These differ from the classic 70/30 overbought-oversold levels because
    Bank Nifty is a high-beta index that rarely reaches 70/30 intraday.
    """
    delta = df["close"].diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)

    # Use ewm with com=period-1 to replicate Wilder's smoothing
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)  # neutral default for early candles


# ---------------------------------------------------------------------------
# VWAP — Volume-Weighted Average Price
# ---------------------------------------------------------------------------

def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """
    Calculate intraday VWAP.
    VWAP = cumulative(typical_price * volume) / cumulative(volume)
    Typical price = (high + low + close) / 3
    """
    typical_price = (df["high"] + df["low"] + df["close"]) / 3
    cum_tp_vol    = (typical_price * df["volume"]).cumsum()
    cum_vol       = df["volume"].cumsum().replace(0, np.nan)
    return cum_tp_vol / cum_vol


# ---------------------------------------------------------------------------
# Bollinger Bands
# ---------------------------------------------------------------------------

def calculate_bollinger_bands(
    df: pd.DataFrame,
    period: int = 20,
    std: float = 2.0,
) -> pd.DataFrame:
    """
    Calculate Bollinger Bands and return DataFrame with columns:
      bb_mid   — simple moving average of close
      bb_upper — mid + std_dev * multiplier
      bb_lower — mid - std_dev * multiplier
      bb_width — (upper - lower) / mid  (normalised band width)

    A small bb_width (<0.015) indicates a squeeze — a breakout is likely.
    """
    rolling     = df["close"].rolling(window=period)
    bb_mid      = rolling.mean()
    bb_std_dev  = rolling.std()

    df = df.copy()
    df["bb_mid"]   = bb_mid
    df["bb_upper"] = bb_mid + std * bb_std_dev
    df["bb_lower"] = bb_mid - std * bb_std_dev
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"].replace(0, np.nan)
    return df


# ---------------------------------------------------------------------------
# Supertrend
# ---------------------------------------------------------------------------

def calculate_supertrend(
    df: pd.DataFrame,
    period: int = 10,
    multiplier: float = 3.0,
) -> pd.DataFrame:
    """
    Calculate Supertrend indicator.
    Returns DataFrame enriched with:
      supertrend      — the Supertrend line value
      supertrend_dir  — +1 = uptrend (bullish), -1 = downtrend (bearish)
    """
    df = df.copy()
    hl2 = (df["high"] + df["low"]) / 2

    # True Range
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"]  - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)

    # ATR via Wilder's smoothing (EWM)
    atr = tr.ewm(com=period - 1, min_periods=period).mean()

    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    supertrend = [0.0] * len(df)
    direction  = [1]   * len(df)  # start bullish

    for i in range(1, len(df)):
        close_prev = df["close"].iloc[i - 1]
        close_curr = df["close"].iloc[i]

        # Adjust bands to prevent them from widening unnecessarily
        upper_band.iloc[i] = min(upper_band.iloc[i], upper_band.iloc[i - 1]) \
            if close_prev <= upper_band.iloc[i - 1] else upper_band.iloc[i]
        lower_band.iloc[i] = max(lower_band.iloc[i], lower_band.iloc[i - 1]) \
            if close_prev >= lower_band.iloc[i - 1] else lower_band.iloc[i]

        if supertrend[i - 1] == upper_band.iloc[i - 1]:
            # Was in downtrend
            direction[i]  = -1 if close_curr <= upper_band.iloc[i] else 1
        else:
            # Was in uptrend
            direction[i]  = 1  if close_curr >= lower_band.iloc[i] else -1

        supertrend[i] = lower_band.iloc[i] if direction[i] == 1 else upper_band.iloc[i]

    df["supertrend"]     = supertrend
    df["supertrend_dir"] = direction
    return df


# ---------------------------------------------------------------------------
# MACD — Moving Average Convergence / Divergence
# ---------------------------------------------------------------------------

def calculate_macd(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate MACD with standard settings (12, 26, 9).
    Returns DataFrame with:
      macd        — MACD line  (EMA12 - EMA26)
      macd_signal — Signal line (EMA9 of MACD)
      macd_hist   — Histogram   (MACD - Signal)
    """
    df = df.copy()
    ema_fast = calculate_ema(df["close"], config.MACD_FAST)
    ema_slow = calculate_ema(df["close"], config.MACD_SLOW)

    df["macd"]        = ema_fast - ema_slow
    df["macd_signal"] = calculate_ema(df["macd"], config.MACD_SIGNAL)
    df["macd_hist"]   = df["macd"] - df["macd_signal"]
    return df


# ---------------------------------------------------------------------------
# calculate_all — Master function
# ---------------------------------------------------------------------------

def calculate_all(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply all indicators to the DataFrame and return the enriched result.
    Input df must have columns: open, high, low, close, volume.
    """
    df = df.copy()

    # EMAs
    df["ema5"]  = calculate_ema(df["close"], config.EMA_5)
    df["ema9"]  = calculate_ema(df["close"], config.EMA_FAST)
    df["ema21"] = calculate_ema(df["close"], config.EMA_SLOW)
    df["ema50"] = calculate_ema(df["close"], config.EMA_MID)
    df["ema200"]= calculate_ema(df["close"], config.EMA_LONG)

    # RSI
    df["rsi"] = calculate_rsi(df, config.RSI_PERIOD)

    # VWAP
    df["vwap"] = calculate_vwap(df)

    # Bollinger Bands (returns df with bb_* columns)
    df = calculate_bollinger_bands(df, config.BB_PERIOD, config.BB_STD)

    # Supertrend
    df = calculate_supertrend(df, config.SUPERTREND_PERIOD, config.SUPERTREND_MULTIPLIER)

    # MACD
    df = calculate_macd(df)

    return df
