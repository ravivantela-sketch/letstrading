"""
dashboard/app.py — Streamlit dashboard for LetsTrading.

Run with:
    streamlit run dashboard/app.py

Features:
  • Live Bank Nifty TradingView chart (15-min, dark theme)
  • 5 top-row metrics: signals today, trades today, win rate, P&L, mode
  • Signal history table with color coding
  • Strategy performance pie chart (Plotly)
  • Auto-refresh every 60 seconds
"""
import sys
import os

# Allow imports from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import streamlit as st
import plotly.express as px
import pandas as pd
from datetime import datetime

import config
from data.database import (
    init_db,
    get_recent_signals,
    get_signals_today,
    get_trades_today,
    get_win_rate,
)
from utils.helpers import format_currency, get_ist_time

# ---------------------------------------------------------------------------
# Page config — must be the FIRST Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="🤖 LetsTrading",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Ensure the database is initialised before any queries
init_db()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("⚙️ Settings")

    mode = st.radio(
        "Trading Mode",
        options=["Paper", "Live"],
        index=0 if config.TRADING_MODE.lower() != "live" else 1,
        help="Paper = simulated orders. Live = real money!",
    )

    capital = st.number_input(
        "Capital (₹)",
        min_value=10_000,
        max_value=10_000_000,
        value=int(config.CAPITAL),
        step=10_000,
    )

    st.markdown("---")
    st.subheader("Active Strategies")
    strat_trend = st.checkbox("Trend Following",    value=True)
    strat_ema5  = st.checkbox("5 EMA Reversion",    value=True)
    strat_orb   = st.checkbox("ORB",                value=True)
    strat_bb    = st.checkbox("BB Squeeze",         value=True)
    strat_gamma = st.checkbox("Gamma Blast",        value=True)

    st.markdown("---")
    st.markdown("### 🔗 Links")
    st.markdown("[Upstox Developer](https://developer.upstox.com)")
    st.markdown("[NSE India](https://www.nseindia.com)")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🤖 LetsTrading — Bank Nifty Options Bot")
st.caption(f"Last refreshed: {get_ist_time().strftime('%d %b %Y  %H:%M:%S IST')}")

# ---------------------------------------------------------------------------
# Top-row metrics
# ---------------------------------------------------------------------------
signals_today = get_signals_today()
trades_today  = get_trades_today()
win_rate      = get_win_rate(days=30)
today_pnl     = sum(t.get("pnl", 0) for t in trades_today)
active_signals = [s for s in signals_today if s.get("signal") != "WAIT"]

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("📡 Signals Today",   len(active_signals))
col2.metric("💼 Trades Today",    len(trades_today))
col3.metric("🎯 Win Rate (30d)",  f"{win_rate:.1f}%")
col4.metric(
    "💰 Today P&L",
    format_currency(today_pnl),
    delta=f"{today_pnl:+.2f}",
    delta_color="normal",
)
col5.metric(
    "⚙️ Mode",
    mode.upper(),
    delta="Paper" if mode == "Paper" else "⚠️ LIVE",
    delta_color="off" if mode == "Paper" else "inverse",
)

st.markdown("---")

# ---------------------------------------------------------------------------
# TradingView Chart (free embeddable widget)
# ---------------------------------------------------------------------------
st.subheader("📈 Bank Nifty — 15 Minute Chart")

tradingview_html = """
<div class="tradingview-widget-container" style="height:520px;">
  <div id="tradingview_chart"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
    new TradingView.widget({
      "width":     "100%",
      "height":    520,
      "symbol":    "NSE:BANKNIFTY",
      "interval":  "15",
      "timezone":  "Asia/Kolkata",
      "theme":     "dark",
      "style":     "1",
      "locale":    "en",
      "toolbar_bg": "#1e1e2e",
      "enable_publishing": false,
      "hide_top_toolbar":  false,
      "hide_legend":       false,
      "save_image":        false,
      "container_id":      "tradingview_chart",
      "studies": [
        "RSI@tv-basicstudies",
        "VWAP@tv-basicstudies",
        "BB@tv-basicstudies"
      ]
    });
  </script>
</div>
"""
st.components.v1.html(tradingview_html, height=530, scrolling=False)

st.markdown("---")

# ---------------------------------------------------------------------------
# Signal history table
# ---------------------------------------------------------------------------
st.subheader("📋 Recent Signals (last 20)")

recent = get_recent_signals(limit=20)
if recent:
    df_signals = pd.DataFrame(recent)[
        ["timestamp", "signal", "strategy", "confidence", "entry", "sl", "target", "rr_ratio", "note"]
    ]

    def _row_color(row):
        """Colour-code rows by signal direction."""
        if row["signal"] == "BUY":
            return ["background-color: #0d3321"] * len(row)
        if row["signal"] == "SELL":
            return ["background-color: #3d0d0d"] * len(row)
        return ["background-color: #1e1e2e"] * len(row)

    st.dataframe(
        df_signals.style.apply(_row_color, axis=1),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No signals recorded yet. Start the bot with `python main.py`.")

st.markdown("---")

# ---------------------------------------------------------------------------
# Strategy performance pie chart
# ---------------------------------------------------------------------------
st.subheader("🍩 Strategy Signal Distribution")

all_signals = get_recent_signals(limit=200)
active_only = [s for s in all_signals if s.get("signal") in ("BUY", "SELL")]
if active_only:
    df_perf = pd.DataFrame(active_only)
    counts  = df_perf.groupby("strategy").size().reset_index(name="count")
    fig = px.pie(
        counts,
        names="strategy",
        values="count",
        title="Signal distribution by strategy",
        hole=0.4,
        template="plotly_dark",
        color_discrete_sequence=px.colors.qualitative.Bold,
    )
    fig.update_layout(paper_bgcolor="#0e1117", plot_bgcolor="#0e1117")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Not enough signal data to display the chart.")

st.markdown("---")
st.caption("⏱ Dashboard auto-refreshes every 60 seconds when running via `streamlit run`.")
