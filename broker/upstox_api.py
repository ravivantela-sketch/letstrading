"""
broker/upstox_api.py — Upstox v2 API wrapper for LetsTrading.

Paper mode:  No real orders are placed; simulated responses are returned.
Live mode:   Real API calls are made via https://api.upstox.com/v2.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import requests
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta

import config

logger = logging.getLogger(__name__)

BASE_URL = "https://api.upstox.com/v2"


class UpstoxBroker:
    """
    Wrapper around the Upstox API v2.

    Usage (paper mode):
        broker = UpstoxBroker(api_key, api_secret, access_token)
        quote  = broker.get_live_quote("NSE_INDEX|Nifty Bank")
        df     = broker.get_historical_data("NSE_INDEX|Nifty Bank")
    """

    def __init__(self, api_key: str, api_secret: str, access_token: str):
        self.api_key      = api_key
        self.api_secret   = api_secret
        self.access_token = access_token
        self.paper_mode   = config.TRADING_MODE.lower() != "live"

        # Common headers required by Upstox v2
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept":        "application/json",
            "Content-Type":  "application/json",
        }
        mode_label = "PAPER" if self.paper_mode else "LIVE"
        logger.info("UpstoxBroker initialised in %s mode", mode_label)

    # ------------------------------------------------------------------
    # Internal request helpers
    # ------------------------------------------------------------------

    def _get(self, endpoint: str, params: dict = None) -> dict:
        """
        Internal GET request to the Upstox API.
        Returns parsed JSON dict or raises on HTTP error.
        """
        url = f"{BASE_URL}{endpoint}"
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("GET %s failed: %s", endpoint, exc)
            raise

    def _post(self, endpoint: str, payload: dict = None) -> dict:
        """
        Internal POST request to the Upstox API.
        Returns parsed JSON dict or raises on HTTP error.
        """
        url = f"{BASE_URL}{endpoint}"
        try:
            resp = requests.post(url, headers=self.headers, json=payload, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("POST %s failed: %s", endpoint, exc)
            raise

    # ------------------------------------------------------------------
    # Market Data
    # ------------------------------------------------------------------

    def get_live_quote(self, instrument_key: str) -> dict:
        """
        Fetch the live market quote for a given instrument.

        Returns dict with keys: ltp, open, high, low, close, volume.
        Falls back to dummy data if the API call fails (e.g. market closed).
        """
        if not self.access_token:
            logger.debug("No access token — using dummy quote")
            return self._get_dummy_quote()

        try:
            data = self._get(
                "/market-quote/quotes",
                params={"instrument_key": instrument_key},
            )
            q = data["data"][instrument_key]["ohlc"]
            return {
                "ltp":    data["data"][instrument_key].get("last_price", q.get("close", 0)),
                "open":   q.get("open",  0),
                "high":   q.get("high",  0),
                "low":    q.get("low",   0),
                "close":  q.get("close", 0),
                "volume": data["data"][instrument_key].get("volume", 0),
            }
        except Exception as exc:
            logger.warning("Live quote failed (%s) — using dummy data", exc)
            return self._get_dummy_quote()

    def get_historical_data(
        self,
        instrument_key: str,
        interval: str = "15minute",
        days_back: int = 30,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV candles from Upstox v2.

        Endpoint: GET /historical-candle/{instrument_key}/{interval}/{to_date}/{from_date}
        Returns DataFrame with columns: timestamp, open, high, low, close, volume.
        Falls back to dummy data on failure.
        """
        if not self.access_token:
            return self._get_dummy_historical_data()

        try:
            to_date   = datetime.today().strftime("%Y-%m-%d")
            from_date = (datetime.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")

            # URL-encode the instrument key (pipe character must be percent-encoded)
            instrument_key_urlencoded = requests.utils.quote(instrument_key, safe="")
            data = self._get(
                f"/historical-candle/{instrument_key_urlencoded}/{interval}/{to_date}/{from_date}",
            )

            candles = data.get("data", {}).get("candles", [])
            if not candles:
                logger.warning("No candles returned — using dummy data")
                return self._get_dummy_historical_data()

            df = pd.DataFrame(candles, columns=[
                "timestamp", "open", "high", "low", "close", "volume", "oi"
            ])
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values("timestamp").reset_index(drop=True)
            return df[["timestamp", "open", "high", "low", "close", "volume"]]

        except Exception as exc:
            logger.warning("Historical data failed (%s) — using dummy data", exc)
            return self._get_dummy_historical_data()

    def get_option_chain(self, expiry_date: str) -> pd.DataFrame:
        """
        Fetch the Bank Nifty option chain for a given expiry date.

        Endpoint: GET /option/chain
        Returns DataFrame with: strike, call_oi, put_oi, call_ltp, put_ltp.
        Returns empty DataFrame on failure.
        """
        if not self.access_token:
            logger.debug("No access token — returning empty option chain")
            return pd.DataFrame(columns=["strike", "call_oi", "put_oi", "call_ltp", "put_ltp"])

        try:
            data = self._get(
                "/option/chain",
                params={
                    "instrument_key": config.INSTRUMENT_KEY,
                    "expiry_date":    expiry_date,
                },
            )
            records = []
            for item in data.get("data", []):
                records.append({
                    "strike":   item.get("strike_price", 0),
                    "call_oi":  item.get("call_options", {}).get("market_data", {}).get("oi", 0),
                    "put_oi":   item.get("put_options",  {}).get("market_data", {}).get("oi", 0),
                    "call_ltp": item.get("call_options", {}).get("market_data", {}).get("ltp", 0),
                    "put_ltp":  item.get("put_options",  {}).get("market_data", {}).get("ltp", 0),
                })
            return pd.DataFrame(records)
        except Exception as exc:
            logger.error("Option chain failed: %s", exc)
            return pd.DataFrame(columns=["strike", "call_oi", "put_oi", "call_ltp", "put_ltp"])

    # ------------------------------------------------------------------
    # Portfolio & Orders
    # ------------------------------------------------------------------

    def get_positions(self) -> list:
        """
        Fetch current short-term positions.
        Returns list of position dicts.
        """
        if not self.access_token:
            return []
        try:
            data = self._get("/portfolio/short-term-positions")
            return data.get("data", [])
        except Exception as exc:
            logger.error("get_positions failed: %s", exc)
            return []

    def place_order(
        self,
        tradingsymbol:  str,
        qty:            int,
        transaction_type: str,
        order_type:     str = "MARKET",
        price:          float = 0,
    ) -> dict:
        """
        Place a buy or sell order.

        In PAPER mode: logs the order and returns a simulated response.
        In LIVE  mode: sends the order to Upstox v2 /order/place endpoint.

        transaction_type: 'BUY' or 'SELL'
        order_type:       'MARKET' or 'LIMIT'
        """
        if self.paper_mode:
            order_id = f"PAPER-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            logger.info(
                "[PAPER] %s %d %s @ %s  |  order_id=%s",
                transaction_type, qty, tradingsymbol, price or "MARKET", order_id,
            )
            return {
                "status":   "success",
                "order_id": order_id,
                "mode":     "paper",
                "symbol":   tradingsymbol,
                "qty":      qty,
                "type":     transaction_type,
            }

        # Live order
        payload = {
            "quantity":         qty,
            "product":          "D",          # Intraday
            "validity":         "DAY",
            "price":            price,
            "tag":              "letstrading",
            "instrument_token": tradingsymbol,
            "order_type":       order_type,
            "transaction_type": transaction_type,
            "disclosed_quantity": 0,
            "trigger_price":    0,
            "is_amo":           False,
        }
        try:
            data = self._post("/order/place", payload)
            logger.info("Live order placed: %s", data)
            return data
        except Exception as exc:
            logger.error("place_order failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    def cancel_order(self, order_id: str) -> dict:
        """Cancel an existing order by order_id."""
        if self.paper_mode:
            logger.info("[PAPER] Cancel order %s", order_id)
            return {"status": "success", "order_id": order_id}
        try:
            return self._post(f"/order/cancel?order_id={order_id}")
        except Exception as exc:
            logger.error("cancel_order failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    def get_order_history(self) -> list:
        """Fetch today's order history."""
        if not self.access_token:
            return []
        try:
            data = self._get("/order/history")
            return data.get("data", [])
        except Exception as exc:
            logger.error("get_order_history failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Dummy / fallback data
    # ------------------------------------------------------------------

    def _get_dummy_quote(self) -> dict:
        """
        Return realistic Bank Nifty dummy quote around ₹48,000.
        Used when access_token is absent or API call fails.
        """
        base = 48000
        noise = np.random.uniform(-200, 200)
        ltp   = round(base + noise, 2)
        return {
            "ltp":    ltp,
            "open":   round(base - 150, 2),
            "high":   round(ltp + 80,  2),
            "low":    round(ltp - 120, 2),
            "close":  round(ltp - 30,  2),
            "volume": int(np.random.uniform(50000, 200000)),
        }

    def _get_dummy_historical_data(self, n_candles: int = 200) -> pd.DataFrame:
        """
        Generate a realistic Bank Nifty OHLCV DataFrame for testing.
        Uses a simple random-walk simulation around ₹48,000.
        """
        np.random.seed(42)
        base   = 48000
        closes = [base]
        for _ in range(n_candles - 1):
            change = np.random.normal(0, 0.003)  # ~0.3% std per candle
            closes.append(round(closes[-1] * (1 + change), 2))

        rows = []
        now  = datetime.now()
        for i, close in enumerate(closes):
            high   = round(close * (1 + abs(np.random.normal(0, 0.002))), 2)
            low    = round(close * (1 - abs(np.random.normal(0, 0.002))), 2)
            open_  = round(close + np.random.normal(0, 50), 2)
            volume = int(np.random.uniform(5000, 25000))
            ts     = now - timedelta(minutes=(n_candles - i) * 15)
            rows.append({
                "timestamp": ts,
                "open":      open_,
                "high":      high,
                "low":       low,
                "close":     close,
                "volume":    volume,
            })

        return pd.DataFrame(rows)
