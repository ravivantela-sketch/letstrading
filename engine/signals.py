"""
engine/signals.py — Trading signal generation strategies for LetsTrading.

Five distinct strategies are implemented:
  1. trend_following_signal      — multi-condition momentum trade
  2. five_ema_reversion_signal   — Subasish Pani EMA5 alert-candle technique
  3. orb_signal                  — Opening Range Breakout (9:30-11:00 AM only)
  4. bb_squeeze_breakout_signal  — Bollinger Band squeeze breakout
  5. gamma_blast_signal          — Expiry-day OI unwinding (after 2 PM)
  6. combined_signal             — orchestrator: runs all 5, picks best

Each strategy returns a standardised signal dict:
  {
    'signal':             'BUY' | 'SELL' | 'WAIT',
    'strategy':           <name>,
    'confidence':         float  (0–100),
    'entry':              float,
    'sl':                 float,
    'target':             float,
    'rr_ratio':           '1:3',
    'note':               str,
    'timestamp':          str  (IST),
  }
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config
from utils.helpers import get_ist_time, is_no_trade_zone


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _wait(strategy: str, note: str = "") -> dict:
    """Return a WAIT signal with zero trade parameters."""
    return {
        "signal":     "WAIT",
        "strategy":   strategy,
        "confidence": 0.0,
        "entry":      0.0,
        "sl":         0.0,
        "target":     0.0,
        "rr_ratio":   "–",
        "note":       note,
        "timestamp":  get_ist_time().strftime("%H:%M:%S IST"),
    }


def _build_signal(
    direction: str,
    strategy: str,
    entry: float,
    sl: float,
    target: float,
    confidence: float,
    note: str,
) -> dict:
    """Assemble a complete signal dict and compute R:R ratio."""
    risk   = abs(entry - sl)
    reward = abs(target - entry)
    rr     = f"1:{round(reward / risk, 1)}" if risk > 0 else "1:0"
    return {
        "signal":     direction,
        "strategy":   strategy,
        "confidence": round(confidence, 1),
        "entry":      round(entry,  2),
        "sl":         round(sl,     2),
        "target":     round(target, 2),
        "rr_ratio":   rr,
        "note":       note,
        "timestamp":  get_ist_time().strftime("%H:%M:%S IST"),
    }


# ---------------------------------------------------------------------------
# 1. Trend Following
# ---------------------------------------------------------------------------

def trend_following_signal(df, vix: float = 15.0, pcr: float = 1.0) -> dict:
    """
    Multi-condition momentum trade.

    BUY conditions (need ≥ 4 of 6):
      1. close > VWAP
      2. EMA9  > EMA21
      3. RSI   > RSI_BULL_THRESHOLD (60)
      4. PCR   < PCR_BULL_THRESHOLD (0.8)
      5. VIX   < VIX_HIGH           (18)
      6. Supertrend direction = +1 (uptrend)

    SELL conditions (mirror image, need ≥ 4 of 6).

    SL: EMA21 level.  Target: 3× risk from entry.
    """
    STRATEGY = "Trend Following"
    if is_no_trade_zone() or df is None or len(df) < 2:
        return _wait(STRATEGY, "No-trade zone or insufficient data")

    last  = df.iloc[-1]
    close = last["close"]

    # Collect conditions
    buy_conditions = [
        close > last.get("vwap",  close),
        last.get("ema9",  close) > last.get("ema21", close),
        last.get("rsi",   50)    > config.RSI_BULL_THRESHOLD,
        pcr < config.PCR_BULL_THRESHOLD,
        vix < config.VIX_HIGH,
        last.get("supertrend_dir", 0) == 1,
    ]
    sell_conditions = [
        close < last.get("vwap",  close),
        last.get("ema9",  close) < last.get("ema21", close),
        last.get("rsi",   50)    < config.RSI_BEAR_THRESHOLD,
        pcr > config.PCR_BEAR_THRESHOLD,
        vix < config.VIX_HIGH,
        last.get("supertrend_dir", 0) == -1,
    ]

    buy_count  = sum(buy_conditions)
    sell_count = sum(sell_conditions)

    if buy_count >= 4:
        sl     = float(last.get("ema21", close * (1 - config.DEFAULT_SL_PCT)))
        risk   = close - sl
        target = close + 3 * risk
        confidence = (buy_count / 6) * 100
        return _build_signal("BUY", STRATEGY, close, sl, target, confidence,
                             f"{buy_count}/6 conditions met")

    if sell_count >= 4:
        sl     = float(last.get("ema21", close * (1 + config.DEFAULT_SL_PCT)))
        risk   = sl - close
        target = close - 3 * risk
        confidence = (sell_count / 6) * 100
        return _build_signal("SELL", STRATEGY, close, sl, target, confidence,
                             f"{sell_count}/6 conditions met")

    return _wait(STRATEGY,
                 f"Only {max(buy_count, sell_count)}/6 conditions met (need 4)")


# ---------------------------------------------------------------------------
# 2. 5 EMA Reversion (Subasish Pani technique)
# ---------------------------------------------------------------------------

def five_ema_reversion_signal(df) -> dict:
    """
    Subasish Pani's 5-EMA setup:

    SETUP:
      • Alert candle: the previous candle is FULLY above/below EMA5
        (i.e., both open AND close on the same side of EMA5).
      • Trade candle: current candle breaks the high (BUY) or low (SELL)
        of the alert candle.

    SL:  Alert candle high (for SELL) or low (for BUY).
    RR:  1:3 — target is 3× risk from entry.
    """
    STRATEGY = "5 EMA Reversion"
    if is_no_trade_zone() or df is None or len(df) < 3:
        return _wait(STRATEGY, "No-trade zone or insufficient data")

    alert   = df.iloc[-2]  # previous candle = alert candle
    current = df.iloc[-1]  # current candle  = trade candle

    ema5_alert = alert.get("ema5", alert["close"])

    # BUY setup: alert candle fully above EMA5
    if alert["open"] > ema5_alert and alert["close"] > ema5_alert:
        if current["close"] > alert["high"]:
            entry  = current["close"]
            sl     = alert["low"]
            risk   = entry - sl
            if risk <= 0:
                return _wait(STRATEGY, "Invalid risk (entry <= sl)")
            target = entry + 3 * risk
            return _build_signal("BUY", STRATEGY, entry, sl, target, 70.0,
                                 "Alert candle fully above EMA5; breakout above alert high")

    # SELL setup: alert candle fully below EMA5
    if alert["open"] < ema5_alert and alert["close"] < ema5_alert:
        if current["close"] < alert["low"]:
            entry  = current["close"]
            sl     = alert["high"]
            risk   = sl - entry
            if risk <= 0:
                return _wait(STRATEGY, "Invalid risk (entry >= sl)")
            target = entry - 3 * risk
            return _build_signal("SELL", STRATEGY, entry, sl, target, 70.0,
                                 "Alert candle fully below EMA5; breakout below alert low")

    return _wait(STRATEGY, "No alert candle setup detected")


# ---------------------------------------------------------------------------
# 3. Opening Range Breakout (ORB)
# ---------------------------------------------------------------------------

def orb_signal(df, orb_high: float, orb_low: float) -> dict:
    """
    Opening Range Breakout — only valid between 9:30 and 11:00 AM IST.

    BUY : close > orb_high AND RSI > 55
    SELL: close < orb_low  AND RSI < 45

    SL  : orb_low  (for BUY) / orb_high (for SELL)
    RR  : 1:2
    """
    STRATEGY = "ORB"
    if is_no_trade_zone() or df is None or df.empty:
        return _wait(STRATEGY, "No-trade zone or insufficient data")

    now    = get_ist_time()
    hour   = now.hour
    minute = now.minute

    # Only valid 9:30 AM – 11:00 AM
    if not ((hour == 9 and minute >= 30) or (hour == 10) or (hour == 11 and minute == 0)):
        return _wait(STRATEGY, "Outside ORB window (9:30–11:00 AM)")

    if orb_high <= 0 or orb_low <= 0:
        return _wait(STRATEGY, "ORB levels not set yet")

    last  = df.iloc[-1]
    close = last["close"]
    rsi   = float(last.get("rsi", 50))

    if close > orb_high and rsi > 55:
        sl     = orb_low
        risk   = close - sl
        target = close + 2 * risk
        return _build_signal("BUY", STRATEGY, close, sl, target, 65.0,
                             f"Breakout above ORB high {orb_high:.0f}, RSI={rsi:.1f}")

    if close < orb_low and rsi < 45:
        sl     = orb_high
        risk   = sl - close
        target = close - 2 * risk
        return _build_signal("SELL", STRATEGY, close, sl, target, 65.0,
                             f"Breakdown below ORB low {orb_low:.0f}, RSI={rsi:.1f}")

    return _wait(STRATEGY, "No ORB breakout yet")


# ---------------------------------------------------------------------------
# 4. Bollinger Band Squeeze Breakout
# ---------------------------------------------------------------------------

def bb_squeeze_breakout_signal(df) -> dict:
    """
    Squeeze: when BB width < BB_SQUEEZE_THRESHOLD (0.015), the bands are
    compressed and a large move is imminent.

    BUY : squeeze detected AND close > bb_upper
    SELL: squeeze detected AND close < bb_lower

    SL  : bb_mid.  Target: 2× risk (approximate next expansion).
    """
    STRATEGY = "BB Squeeze"
    if is_no_trade_zone() or df is None or len(df) < 2:
        return _wait(STRATEGY, "No-trade zone or insufficient data")

    # Look for squeeze on the PREVIOUS candle, trade the breakout on current
    prev = df.iloc[-2]
    last = df.iloc[-1]

    bb_width_prev = float(prev.get("bb_width", 0.02))
    squeeze_on    = bb_width_prev < config.BB_SQUEEZE_THRESHOLD

    if not squeeze_on:
        return _wait(STRATEGY, f"No squeeze (bb_width={bb_width_prev:.4f})")

    close    = last["close"]
    bb_upper = float(last.get("bb_upper", close * 1.01))
    bb_lower = float(last.get("bb_lower", close * 0.99))
    bb_mid   = float(last.get("bb_mid",   close))

    if close > bb_upper:
        sl     = bb_mid
        risk   = close - sl
        target = close + 2 * risk
        return _build_signal("BUY", STRATEGY, close, sl, target, 72.0,
                             f"Squeeze breakout above upper band {bb_upper:.0f}")

    if close < bb_lower:
        sl     = bb_mid
        risk   = sl - close
        target = close - 2 * risk
        return _build_signal("SELL", STRATEGY, close, sl, target, 72.0,
                             f"Squeeze breakdown below lower band {bb_lower:.0f}")

    return _wait(STRATEGY, "Squeeze present but no band breakout yet")


# ---------------------------------------------------------------------------
# 5. Gamma Blast (Expiry Day)
# ---------------------------------------------------------------------------

def gamma_blast_signal(
    df,
    oi_change: float = 0.0,
    is_expiry: bool  = False,
) -> dict:
    """
    Expiry-day OI unwinding trade.

    Conditions:
      • Must be expiry day (Wednesday for Bank Nifty)
      • Must be after 2:00 PM IST (gamma acceleration zone)
      • OI change < -5% (significant unwinding of option OI)
      • Price breaks the 30-minute high (BUY) or low (SELL)

    SL  : 30-min low (for BUY) / 30-min high (for SELL)
    RR  : 1:2 (fast scalp, expiry is tight)
    """
    STRATEGY = "Gamma Blast"
    if not is_expiry:
        return _wait(STRATEGY, "Not expiry day")

    now = get_ist_time()
    if now.hour < 14:
        return _wait(STRATEGY, "Before 2:00 PM — gamma not yet accelerating")

    if is_no_trade_zone():
        return _wait(STRATEGY, "No-trade zone")

    if df is None or len(df) < 2:
        return _wait(STRATEGY, "Insufficient data")

    # OI unwinding threshold: oi_change < -0.05 (e.g. -8% change)
    if oi_change >= -0.05:
        return _wait(STRATEGY, f"No significant OI unwinding (oi_change={oi_change:.2%})")

    # Use last 2 candles as 30-min range proxy
    recent     = df.tail(2)
    range_high = float(recent["high"].max())
    range_low  = float(recent["low"].min())

    last  = df.iloc[-1]
    close = last["close"]

    if close > range_high:
        sl     = range_low
        risk   = close - sl
        target = close + 2 * risk
        return _build_signal("BUY", STRATEGY, close, sl, target, 80.0,
                             f"Expiry gamma blast BUY; OI change={oi_change:.2%}")

    if close < range_low:
        sl     = range_high
        risk   = sl - close
        target = close - 2 * risk
        return _build_signal("SELL", STRATEGY, close, sl, target, 80.0,
                             f"Expiry gamma blast SELL; OI change={oi_change:.2%}")

    return _wait(STRATEGY, "No breakout of 30-min range")


# ---------------------------------------------------------------------------
# 6. Combined Signal — orchestrator
# ---------------------------------------------------------------------------

def combined_signal(
    df,
    vix:       float = 15.0,
    pcr:       float = 1.0,
    oi_change: float = 0.0,
    orb_high:  float = 0.0,
    orb_low:   float = 0.0,
    is_expiry: bool  = False,
) -> dict:
    """
    Run all 5 strategies and return the highest-confidence non-WAIT signal.
    Adds a 'confirmation_count' key showing how many strategies agree.

    If all strategies return WAIT, returns a WAIT signal from this function.
    """
    STRATEGY = "Combined"

    signals = [
        trend_following_signal(df, vix, pcr),
        five_ema_reversion_signal(df),
        orb_signal(df, orb_high, orb_low),
        bb_squeeze_breakout_signal(df),
        gamma_blast_signal(df, oi_change, is_expiry),
    ]

    # Filter to non-WAIT signals only
    active = [s for s in signals if s["signal"] != "WAIT"]

    if not active:
        s = _wait(STRATEGY, "All strategies returned WAIT")
        s["confirmation_count"] = 0
        return s

    # Count direction agreement
    buy_count  = sum(1 for s in active if s["signal"] == "BUY")
    sell_count = sum(1 for s in active if s["signal"] == "SELL")

    # Pick the dominant direction
    dominant = "BUY" if buy_count >= sell_count else "SELL"
    candidates = [s for s in active if s["signal"] == dominant]

    # Among candidates pick the one with highest confidence
    best = max(candidates, key=lambda s: s["confidence"])
    best = best.copy()
    best["strategy"]           = STRATEGY
    best["confirmation_count"] = len(candidates)
    best["note"] = (
        f"Best: {best['note']} | "
        f"{len(candidates)} strategy(ies) agree on {dominant}"
    )
    return best
