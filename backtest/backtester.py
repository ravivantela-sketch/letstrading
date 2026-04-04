"""
backtest/backtester.py — Strategy backtester for LetsTrading.

Usage:
    from backtest.backtester import run_backtest, print_backtest_report
    results = run_backtest(strategy="trend_following")
    print_backtest_report(results)

Simulates entry and exit based on SL/target, tracks equity,
and reports key performance metrics.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go

import config
from engine.indicators import calculate_all
from engine.signals import trend_following_signal


# ---------------------------------------------------------------------------
# Main backtest runner
# ---------------------------------------------------------------------------

def run_backtest(
    df=None,
    initial_capital: float = 100_000,
    strategy: str          = "trend_following",
) -> dict:
    """
    Simulate a trading strategy on historical OHLCV data.

    Parameters
    ----------
    df              : DataFrame with OHLCV columns (uses dummy data if None)
    initial_capital : Starting capital in INR
    strategy        : strategy name to test (currently 'trend_following')

    Returns
    -------
    dict with keys:
      total_trades, wins, losses, win_rate, total_pnl, return_pct,
      max_drawdown, sharpe_ratio, equity_curve
    """
    if df is None:
        df = _generate_dummy_data()

    # Compute all technical indicators
    df = calculate_all(df.copy())
    df = df.dropna().reset_index(drop=True)

    capital    = initial_capital
    equity     = [capital]
    trades_log = []

    lot_size = config.BANK_NIFTY_LOT_SIZE
    in_trade = False
    entry_price = 0.0
    sl_price    = 0.0
    target_price = 0.0
    direction    = "BUY"
    qty          = lot_size

    for i in range(1, len(df)):
        row = df.iloc[i]

        if in_trade:
            high  = row["high"]
            low   = row["low"]
            close = row["close"]
            pnl   = 0.0
            exited = False

            if direction == "BUY":
                if low <= sl_price:
                    pnl    = (sl_price - entry_price) * qty
                    exited = True
                elif high >= target_price:
                    pnl    = (target_price - entry_price) * qty
                    exited = True
            else:  # SELL
                if high >= sl_price:
                    pnl    = (entry_price - sl_price) * qty
                    exited = True
                elif low <= target_price:
                    pnl    = (entry_price - target_price) * qty
                    exited = True

            if exited:
                capital    += pnl
                in_trade    = False
                trades_log.append({"pnl": pnl, "direction": direction})

            equity.append(capital)
            continue

        # Generate signal on current slice
        window = df.iloc[max(0, i - 50): i + 1]
        sig    = trend_following_signal(window, vix=15.0, pcr=0.9)

        if sig["signal"] in ("BUY", "SELL") and not in_trade:
            in_trade     = True
            direction    = sig["signal"]
            entry_price  = row["close"]
            sl_price     = sig.get("sl",     entry_price * (0.995 if direction == "BUY" else 1.005))
            target_price = sig.get("target", entry_price * (1.015 if direction == "BUY" else 0.985))
            qty          = _calc_qty(capital, entry_price, sl_price, lot_size)

        equity.append(capital)

    # ---------------------------------------------------------------
    # Performance metrics
    # ---------------------------------------------------------------
    total  = len(trades_log)
    wins   = sum(1 for t in trades_log if t["pnl"] > 0)
    losses = total - wins
    wr     = (wins / total * 100) if total > 0 else 0.0

    total_pnl  = capital - initial_capital
    return_pct = (total_pnl / initial_capital) * 100

    eq_series   = pd.Series(equity)
    rolling_max = eq_series.cummax()
    drawdown    = (eq_series - rolling_max) / rolling_max * 100
    max_dd      = float(drawdown.min())

    # Simplified daily returns for Sharpe (assuming 1 candle ≈ 15 min, ~26 candles/day)
    daily_returns = eq_series.pct_change(26).dropna()
    sharpe = 0.0
    if daily_returns.std() > 0:
        sharpe = round((daily_returns.mean() / daily_returns.std()) * (252 ** 0.5), 2)

    return {
        "total_trades":  total,
        "wins":          wins,
        "losses":        losses,
        "win_rate":      round(wr, 1),
        "total_pnl":     round(total_pnl, 2),
        "return_pct":    round(return_pct, 2),
        "max_drawdown":  round(max_dd, 2),
        "sharpe_ratio":  sharpe,
        "equity_curve":  equity,
        "initial_capital": initial_capital,
    }


# ---------------------------------------------------------------------------
# Equity curve chart
# ---------------------------------------------------------------------------

def plot_equity_curve(results: dict):
    """
    Plot the equity curve using Plotly with a dark theme.
    Returns a Plotly Figure object.
    """
    equity   = results["equity_curve"]
    capital0 = results["initial_capital"]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y     = equity,
        mode  = "lines",
        name  = "Equity",
        line  = dict(color="#00d4aa", width=2),
    ))
    fig.add_hline(
        y          = capital0,
        line_dash  = "dash",
        line_color = "gray",
        annotation_text = "Initial Capital",
    )
    fig.update_layout(
        title      = "📈 Backtest Equity Curve",
        xaxis_title= "Candle",
        yaxis_title= "Portfolio Value (₹)",
        template   = "plotly_dark",
        paper_bgcolor = "#0e1117",
        plot_bgcolor  = "#0e1117",
        font       = dict(color="white"),
        height     = 450,
    )
    return fig


# ---------------------------------------------------------------------------
# Console report
# ---------------------------------------------------------------------------

def print_backtest_report(results: dict) -> None:
    """Print a formatted backtest summary to the console."""
    sep = "=" * 45
    print(f"\n{sep}")
    print("   LetsTrading — Backtest Report")
    print(sep)
    print(f"  Total Trades  : {results['total_trades']}")
    print(f"  Wins          : {results['wins']}")
    print(f"  Losses        : {results['losses']}")
    print(f"  Win Rate      : {results['win_rate']:.1f}%")
    print(sep)
    print(f"  Total P&L     : ₹{results['total_pnl']:,.2f}")
    print(f"  Return        : {results['return_pct']:.2f}%")
    print(f"  Max Drawdown  : {results['max_drawdown']:.2f}%")
    print(f"  Sharpe Ratio  : {results['sharpe_ratio']:.2f}")
    print(sep)


# ---------------------------------------------------------------------------
# Dummy data generator
# ---------------------------------------------------------------------------

def _generate_dummy_data(n: int = 200) -> pd.DataFrame:
    """
    Generate realistic Bank Nifty OHLCV data for backtesting.
    Uses a random-walk simulation seeded for reproducibility.
    """
    np.random.seed(0)
    base   = 48000
    closes = [base]
    for _ in range(n - 1):
        change = np.random.normal(0, 0.003)
        closes.append(round(closes[-1] * (1 + change), 2))

    rows = []
    now  = datetime.now()
    for i, c in enumerate(closes):
        h = round(c * (1 + abs(np.random.normal(0, 0.002))), 2)
        l = round(c * (1 - abs(np.random.normal(0, 0.002))), 2)
        o = round(c + np.random.normal(0, 50), 2)
        v = int(np.random.uniform(5000, 25000))
        t = now - timedelta(minutes=(n - i) * 15)
        rows.append({"timestamp": t, "open": o, "high": h, "low": l, "close": c, "volume": v})

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _calc_qty(capital: float, entry: float, sl: float, lot_size: int) -> int:
    """Calculate quantity rounded to the nearest lot size."""
    risk_amount   = capital * config.MAX_RISK_PER_TRADE
    risk_per_unit = abs(entry - sl)
    if risk_per_unit == 0:
        return lot_size
    raw = risk_amount / risk_per_unit
    lots = max(1, round(raw / lot_size))
    return lots * lot_size
