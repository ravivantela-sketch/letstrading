# 🤖 LetsTrading — AI-Powered Bank Nifty Trading Platform

![Python](https://img.shields.io/badge/Python-3.11+-blue) ![License](https://img.shields.io/badge/License-MIT-green) ![Broker](https://img.shields.io/badge/Broker-Upstox-purple)

> Free, AI-powered Bank Nifty intraday trading platform using Upstox API, technical indicators, and Telegram alerts.

## ✨ Features
- 🎯 **Triple Confirmation Signal Engine** — EMA + RSI + VWAP combined
- 📊 **5 EMA Mean Reversion** — Subasish Pani style reversal strategy
- 🚀 **Opening Range Breakout (ORB)** — 9:15–9:30 AM breakout logic
- 💥 **Gamma Blast** — Expiry day OTM options strategy
- 📱 **Telegram Alerts** — Real-time BUY/SELL notifications
- 🖥️ **Streamlit Dashboard** — Live charts + signal history
- 🗃️ **SQLite Trade Logging** — Track every signal and trade
- 📄 **Paper Trading Mode** — Safe simulation, no real orders
- 🔗 **Upstox API v2** — Live data + order placement

## 🚀 Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/ravivantela-sketch/letstrading.git
cd letstrading
```

### 2. Create virtual environment
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Setup credentials
```bash
cp .env.example .env
# Open .env in VS Code and fill in your Upstox API keys and Telegram bot token
```

### 5. Run in Paper Mode (safe — no real orders)
```bash
python main.py --mode paper
```

### 6. Run the Dashboard
```bash
streamlit run dashboard/app.py
```

### 7. Run Backtest
```bash
python main.py --mode backtest
```

## 📁 Project Structure
```
letstrading/
├── main.py              # Entry point — run the bot
├── config.py            # All settings loaded from .env
├── engine/
│   ├── indicators.py    # EMA, RSI, VWAP, Bollinger Bands, Supertrend, MACD
│   ├── signals.py       # Buy/Sell strategies (5 strategies)
│   ├── risk.py          # Position sizing, SL/Target, daily loss limit
│   └── regime.py        # Market regime classifier
├── broker/
│   └── upstox_api.py    # Upstox API v2 integration
├── alerts/
│   └── telegram_bot.py  # Telegram BUY/SELL notifications
├── data/
│   └── database.py      # SQLite trade logging
├── dashboard/
│   └── app.py           # Streamlit web dashboard
├── backtest/
│   └── backtester.py    # Historical strategy testing
└── utils/
    └── helpers.py       # IST time, expiry check, formatting
```

## 🗺️ Next Steps (Read This!)

### ✅ Week 1 — Setup
- [ ] Get Upstox API credentials → [developer.upstox.com](https://developer.upstox.com) → Create App → Copy API Key & Secret into `.env`
- [ ] Create Telegram Bot → Message [@BotFather](https://t.me/BotFather) → `/newbot` → copy token into `.env`
- [ ] Get your Chat ID → Message [@userinfobot](https://t.me/userinfobot) → copy ID into `.env`
- [ ] Run `python main.py --mode paper` → watch signals in VS Code terminal
- [ ] Open dashboard → `streamlit run dashboard/app.py`

### ✅ Week 2–3 — Paper Trade
- [ ] Run paper trading every market day (9:15 AM – 3:30 PM IST)
- [ ] Monitor Telegram for BUY/SELL alerts
- [ ] Check dashboard for signal history and win rate
- [ ] Target at least **30 paper trades** before going live

### ✅ Week 4 — Evaluate
- [ ] Run `python main.py --mode backtest` → check historical performance
- [ ] Aim for **win rate > 55%** before going live
- [ ] Tune RSI/EMA thresholds in `config.py` if needed

### ✅ Month 2 — Go Live (only if paper trading profitable)
- [ ] Change `TRADING_MODE=live` in `.env`
- [ ] Start with minimum capital — 1 lot Bank Nifty options (~₹5,000 margin)
- [ ] Never risk more than 1% per trade (enforced in `risk.py`)
- [ ] Bot auto-stops after 2% daily loss (`MAX_DAILY_LOSS=0.02`)

### ✅ Advanced (Month 3+)
- [ ] Add live PCR feed from NSE
- [ ] Add India VIX live feed
- [ ] Add Iron Condor / Bull Call Spread strategies
- [ ] Deploy on Railway.app for 24/7 uptime (free tier)

## 💡 Tips for VS Code Users
- Install **Python extension** in VS Code for syntax highlighting
- Install **GitHub Copilot** extension — it will help you understand and modify the code
- Use the integrated terminal: `Ctrl+`` ` to run commands
- Open `.env` file and fill in your credentials — never share this file!

## ⚠️ Disclaimer
This platform is for **educational purposes only**. Trading in financial markets involves substantial risk of loss. Always paper trade for at least 30 days before using real capital. The authors are not responsible for any financial losses.

## 📄 License
MIT License — free to use and modify.
