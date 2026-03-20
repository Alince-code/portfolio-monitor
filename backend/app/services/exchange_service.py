"""Exchange rate service — centralized USD/CNY/HKD rates with 5-minute cache."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

_FALLBACK_USD_CNY = 7.2
_FALLBACK_USD_HKD = 7.8
_CACHE_TTL = 300  # 5 minutes

_cache_usd_cny: float = _FALLBACK_USD_CNY
_cache_usd_hkd: float = _FALLBACK_USD_HKD
_cache_time: float = 0


def get_usd_to_cny() -> float:
    """Get real-time USD/CNY exchange rate from Yahoo Finance.

    Returns cached value if within 5 minutes. Falls back to 7.2 on error.
    """
    global _cache_usd_cny, _cache_time

    now = time.time()
    if now - _cache_time < _CACHE_TTL:
        return _cache_usd_cny

    try:
        from curl_cffi import requests as cffi_requests
        session = cffi_requests.Session(impersonate="chrome")
        url = "https://query2.finance.yahoo.com/v8/finance/chart/CNY=X"
        resp = session.get(url, params={"range": "1d", "interval": "1d"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            rate = meta.get("regularMarketPrice")
            if rate and 5 < rate < 10:  # Sanity check
                _cache_usd_cny = round(rate, 4)
                _cache_time = now
                logger.info(f"FX rate updated: USD/CNY = {_cache_usd_cny}")
    except Exception as e:
        logger.warning(f"FX rate fetch error: {e}")

    return _cache_usd_cny


def get_usd_to_hkd() -> float:
    """Get real-time USD/HKD exchange rate from Yahoo Finance.

    Hong Kong Dollar pegged to USD around 7.75-7.85.
    Returns cached value if within 5 minutes. Falls back to 7.8 on error.
    """
    global _cache_usd_hkd, _cache_time

    now = time.time()
    if now - _cache_time < _CACHE_TTL:
        return _cache_usd_hkd

    try:
        from curl_cffi import requests as cffi_requests
        session = cffi_requests.Session(impersonate="chrome")
        url = "https://query2.finance.yahoo.com/v8/finance/chart/HKD=X"
        resp = session.get(url, params={"range": "1d", "interval": "1d"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            result = data.get("chart", {}).get("result", [{}])[0]
            meta = result.get("meta", {})
            rate = meta.get("regularMarketPrice")
            if rate and 7.5 < rate < 8.0:  # Sanity check for HKD peg
                _cache_usd_hkd = round(rate, 4)
                _cache_time = now
                logger.info(f"FX rate updated: USD/HKD = {_cache_usd_hkd}")
    except Exception as e:
        logger.warning(f"HKD FX rate fetch error: {e}")

    return _cache_usd_hkd


def get_cny_to_hkd() -> float:
    """Get CNY/HKD cross rate calculated from USD rates.

    Formula: CNY/HKD = (CNY/USD) ÷ (HKD/USD)
    """
    usd_to_cny = get_usd_to_cny()
    usd_to_hkd = get_usd_to_hkd()
    return round(usd_to_hkd / usd_to_cny, 4)


def refresh_all_rates() -> dict:
    """Force refresh all exchange rates and return current values.
    
    Useful for manual refresh triggers or scheduled updates.
    """
    global _cache_time
    _cache_time = 0  # Force cache expiration
    
    return {
        "usd_to_cny": get_usd_to_cny(),
        "usd_to_hkd": get_usd_to_hkd(),
        "cny_to_hkd": get_cny_to_hkd(),
    }
