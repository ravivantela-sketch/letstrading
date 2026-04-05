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

If you want to avoid OneDrive sync issues entirely, keep both the repository and `.venv` under a local path such as `C:\Users\Ravi.Vantela\Projects\letstrading`. That is a sound setup.

### 4. Setup credentials
```bash
cp .env.example .env
# Open .env in VS Code and fill in your Upstox API keys and Telegram bot token
```

On Windows PowerShell, use:

```powershell
Copy-Item .env.example .env
```

Keep `.env` local only. This repository already ignores `.env` and `.venv`, so your real keys and local environment should not be committed.

### 5. Run in Paper Mode (safe — no real orders)
```bash
python main.py --mode paper
```

### 5b. Run in Advisory Mode (real-data suggestions, no execution)
```bash
python main.py --mode advisory
```

Advisory mode fetches data and generates BUY/SELL recommendations with reasons,
but does not place orders.

It now sends plain-language guidance such as:
- Clear action: BUY / SELL / WAIT
- Probability percentage
- Risk level (Lower / Moderate / Higher)
- Next market-open trend bias
- Simple "what to do" line

### 5c. Test Telegram setup
```bash
python main.py --mode telegram-test
```

This validates token and chat ID, and sends a test message when configuration is correct.

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

## 🔐 Public Repo Security
- Never put real API keys, access tokens, chat IDs, or session data into tracked files.
- Keep secrets only in `.env`, which is ignored by Git.
- Commit only `.env.example` with placeholder values.
- If any real secret was ever pushed to GitHub, assume it is compromised and rotate it immediately in Upstox and Telegram.
- Before pushing, run `git status` and confirm `.env`, `.venv`, database files, and logs are not staged.
- If a secret was accidentally tracked in the past, remove it from the repo history before trusting that key again.

### Local Secret Scan Hooks
- This checkout now uses a local Git hooks path at `.githooks`.
- `pre-commit` scans staged files for likely credentials.
- `pre-push` scans tracked committed files before a push leaves your machine.
- The scanner lives at `tools/secret_scan.py` and reports only file, line, and a redacted reason.
- If you clone the repo elsewhere, re-run `git config --local core.hooksPath .githooks` in that clone to enable the same protection.

### Audit Result
- The tracked history reviewed from this checkout showed `.env.example` in Git history, which is expected.
- The review did not show `.env` as a tracked file in the repository history queried here.
- That reduces the chance of public secret exposure through Git, but it does not replace key rotation if you ever pasted real values into GitHub, commits, issues, or other public locations.

## 🧰 Local Environment Recommendation
Using a local `.venv` under `C:` instead of OneDrive is the correct approach for this project. It avoids file locking, background sync churn, slow package installs, and interpreter path breakage caused by cloud-sync moves.

## ⚠️ Disclaimer
This platform is for **educational purposes only**. Trading in financial markets involves substantial risk of loss. Always paper trade for at least 30 days before using real capital. The authors are not responsible for any financial losses.

## 📄 License
MIT License — free to use and modify.
