"""
engine/regime.py — Market regime classification for LetsTrading.

classify_regime() analyses the latest candle data and external inputs
(VIX, PCR) to decide whether conditions are suitable for trading and
what the overall market "mood" is.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config
from utils.helpers import is_no_trade_zone


def classify_regime(df, vix: float = 15.0, pcr: float = 1.0) -> dict:
    """
    Classify the current market regime.

    Parameters
    ----------
    df  : DataFrame enriched by calculate_all() (needs ema9, ema21,
          ema200, rsi, bb_width columns).
    vix : India VIX value (fear gauge). Low VIX = calm, high = volatile.
    pcr : Put-Call Ratio.  PCR < 0.8 = bullish, PCR > 1.2 = bearish.

    Returns
    -------
    dict with keys:
      trend          — 'BULLISH' | 'BEARISH' | 'SIDEWAYS'
      volatility     — 'LOW' | 'NORMAL' | 'HIGH'
      sentiment      — 'BULLISH' | 'BEARISH' | 'NEUTRAL'
      bb_squeeze     — bool: True if Bollinger Bands are compressed
      trade_allowed  — bool: False during no-trade zones or high volatility
      regime_score   — int: positive = bullish, negative = bearish
      vix            — float: passed-through VIX value
      pcr            — float: passed-through PCR value
      rsi            — float: latest RSI value
    """
    if df is None or df.empty:
        return _neutral_regime(vix, pcr)

    last = df.iloc[-1]

    # ------------------------------------------------------------------ #
    # 1. Trend — based on EMA alignment                                  #
    # ------------------------------------------------------------------ #
    ema9   = last.get("ema9",   last["close"])
    ema21  = last.get("ema21",  last["close"])
    ema200 = last.get("ema200", last["close"])
    close  = last["close"]

    if ema9 > ema21 and close > ema200:
        trend = "BULLISH"
    elif ema9 < ema21 and close < ema200:
        trend = "BEARISH"
    else:
        trend = "SIDEWAYS"

    # ------------------------------------------------------------------ #
    # 2. Volatility — based on India VIX                                 #
    # ------------------------------------------------------------------ #
    if vix < config.VIX_LOW:
        volatility = "LOW"
    elif vix > config.VIX_HIGH:
        volatility = "HIGH"
    else:
        volatility = "NORMAL"

    # ------------------------------------------------------------------ #
    # 3. Sentiment — based on Put-Call Ratio                             #
    # ------------------------------------------------------------------ #
    if pcr < config.PCR_BULL_THRESHOLD:
        sentiment = "BULLISH"
    elif pcr > config.PCR_BEAR_THRESHOLD:
        sentiment = "BEARISH"
    else:
        sentiment = "NEUTRAL"

    # ------------------------------------------------------------------ #
    # 4. BB Squeeze                                                       #
    # ------------------------------------------------------------------ #
    bb_width  = last.get("bb_width", 0.02)
    bb_squeeze = float(bb_width) < config.BB_SQUEEZE_THRESHOLD

    # ------------------------------------------------------------------ #
    # 5. Trade allowed                                                    #
    # ------------------------------------------------------------------ #
    # Do not trade during restricted time windows or extreme volatility
    trade_allowed = (
        not is_no_trade_zone()
        and volatility != "HIGH"
    )

    # ------------------------------------------------------------------ #
    # 6. Regime score — a simple composite score                         #
    # ------------------------------------------------------------------ #
    score = 0
    rsi   = float(last.get("rsi", 50))

    if trend == "BULLISH":
        score += 2
    elif trend == "BEARISH":
        score -= 2

    if sentiment == "BULLISH":
        score += 1
    elif sentiment == "BEARISH":
        score -= 1

    if rsi > config.RSI_BULL_THRESHOLD:
        score += 1
    elif rsi < config.RSI_BEAR_THRESHOLD:
        score -= 1

    if volatility == "HIGH":
        score = 0  # reset — too risky

    return {
        "trend":         trend,
        "volatility":    volatility,
        "sentiment":     sentiment,
        "bb_squeeze":    bb_squeeze,
        "trade_allowed": trade_allowed,
        "regime_score":  score,
        "vix":           vix,
        "pcr":           pcr,
        "rsi":           rsi,
    }


def _neutral_regime(vix: float, pcr: float) -> dict:
    """Return a safe neutral regime when no data is available."""
    return {
        "trend":         "SIDEWAYS",
        "volatility":    "NORMAL",
        "sentiment":     "NEUTRAL",
        "bb_squeeze":    False,
        "trade_allowed": False,
        "regime_score":  0,
        "vix":           vix,
        "pcr":           pcr,
        "rsi":           50.0,
    }
