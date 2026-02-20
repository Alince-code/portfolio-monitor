"""Price fetching service — uses Yahoo Finance v8 chart API via curl_cffi.

curl_cffi provides browser-impersonation TLS fingerprints to avoid
Yahoo Finance's aggressive bot detection and rate limiting.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List

from curl_cffi import requests as cffi_requests

logger = logging.getLogger(__name__)

# Yahoo Finance v8 chart API
YF_BASE = "https://query2.finance.yahoo.com/v8/finance/chart"

# Persistent session with browser impersonation
_session = cffi_requests.Session(impersonate="chrome")


def _fetch_chart(symbol: str) -> Dict[str, Any]:
    """Fetch price data from Yahoo Finance v8 chart API with browser impersonation."""
    url = f"{YF_BASE}/{symbol}"
    params = {"range": "2d", "interval": "1d"}

    try:
        resp = _session.get(url, params=params, timeout=15)

        if resp.status_code == 429:
            logger.warning(f"Rate limited for {symbol}")
            return {"symbol": symbol, "error": "Rate limited"}

        if resp.status_code != 200:
            return {"symbol": symbol, "error": f"HTTP {resp.status_code}"}

        data = resp.json()
        chart = data.get("chart", {})

        if chart.get("error"):
            err = chart["error"]
            return {"symbol": symbol, "error": f"{err.get('code')}: {err.get('description')}"}

        results = chart.get("result", [])
        if not results:
            return {"symbol": symbol, "error": "No data returned"}

        meta = results[0].get("meta", {})
        indicators = results[0].get("indicators", {})
        quotes = indicators.get("quote", [{}])[0]

        # Current price from meta (most reliable)
        current_price = meta.get("regularMarketPrice")
        previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")

        if current_price is None:
            closes = [c for c in quotes.get("close", []) if c is not None]
            current_price = closes[-1] if closes else None

        if current_price is None:
            return {"symbol": symbol, "error": "No price data available"}

        change = round(current_price - previous_close, 4) if previous_close else None
        change_pct = round(change / previous_close * 100, 2) if previous_close and change else None

        volume = meta.get("regularMarketVolume")
        if volume is None:
            vols = [v for v in quotes.get("volume", []) if v is not None]
            volume = vols[-1] if vols else None

        return {
            "symbol": symbol,
            "name": meta.get("longName") or meta.get("shortName") or symbol,
            "price": round(current_price, 4),
            "previous_close": round(previous_close, 4) if previous_close else None,
            "change": change,
            "change_pct": change_pct,
            "volume": volume,
            "market_cap": None,
            "currency": meta.get("currency", "USD"),
        }

    except Exception as e:
        logger.error(f"Failed to fetch {symbol}: {e}")
        return {"symbol": symbol, "error": str(e)}


def fetch_price(symbol: str) -> Dict[str, Any]:
    """Fetch current price for a single symbol."""
    return _fetch_chart(symbol.strip())


def fetch_cn_price(symbol: str) -> Dict[str, Any]:
    """Fetch A-share price. Yahoo Finance supports .SS/.SZ suffix."""
    return fetch_price(symbol)


def fetch_prices_batch(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """Fetch prices for multiple symbols with concurrent batches.

    Uses ThreadPoolExecutor with max_workers=3 to fetch in parallel.
    Adds 1s sleep between batches to avoid rate limits.

    Returns a dict keyed by symbol.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = {}
    batch_size = 3

    for batch_start in range(0, len(symbols), batch_size):
        if batch_start > 0:
            time.sleep(1)  # Inter-batch delay to avoid rate limits

        batch = symbols[batch_start:batch_start + batch_size]
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {pool.submit(fetch_price, sym): sym for sym in batch}
            for future in as_completed(futures):
                sym = futures[future]
                try:
                    results[sym] = future.result()
                except Exception as e:
                    results[sym] = {"symbol": sym, "error": str(e)}

    return results
