"""Dashboard endpoint — aggregates data for the main view."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    PriceCache, AlertHistory, Transaction, CashAccount,
    DashboardOut, PriceOut, AlertHistoryOut, TransactionOut, CashAccountOut, TotalAssetsOut,
)
from ..services.portfolio_service import get_holdings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# Exchange rate with cache
_fx_cache: dict = {"rate": 7.2, "ts": 0}
_FX_CACHE_TTL = 300  # 5 minutes


def _get_usd_to_cny() -> float:
    """Fetch real-time USD/CNY rate from Yahoo Finance, with cache."""
    global _fx_cache
    now = time.time()
    if now - _fx_cache["ts"] < _FX_CACHE_TTL:
        return _fx_cache["rate"]

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
                _fx_cache["rate"] = round(rate, 4)
                _fx_cache["ts"] = now
                logger.info(f"FX rate updated: USD/CNY = {_fx_cache['rate']}")
    except Exception as e:
        logger.warning(f"FX rate fetch error: {e}")

    return _fx_cache["rate"]


@router.get("", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db)):
    """Get dashboard data: prices, portfolio, cash accounts, total assets, recent alerts, recent transactions."""
    prices = db.query(PriceCache).order_by(PriceCache.symbol).all()
    recent_alerts = (
        db.query(AlertHistory)
        .order_by(AlertHistory.triggered_at.desc())
        .limit(10)
        .all()
    )
    recent_transactions = (
        db.query(Transaction)
        .order_by(Transaction.date.desc())
        .limit(10)
        .all()
    )
    portfolio = get_holdings(db)

    # Get real-time FX rate
    usd_to_cny = _get_usd_to_cny()

    # Get cash accounts
    cash_accounts = db.query(CashAccount).all()
    cash_map = {acc.currency: acc.balance for acc in cash_accounts}
    cash_usd = cash_map.get("USD", 0.0)
    cash_cny = cash_map.get("CNY", 0.0)

    # Separate stock values by currency
    stock_value_usd = 0.0
    stock_value_cny = 0.0
    if portfolio and portfolio.holdings:
        for h in portfolio.holdings:
            # Check if the symbol is a CN stock
            cached = db.query(PriceCache).filter(PriceCache.symbol == h.symbol).first()
            if cached and cached.currency == "CNY":
                stock_value_cny += h.market_value
            else:
                stock_value_usd += h.market_value

    # Calculate total in USD equivalent
    total_assets_usd = (
        stock_value_usd
        + cash_usd
        + (stock_value_cny / usd_to_cny)
        + (cash_cny / usd_to_cny)
    )

    total_assets_data = TotalAssetsOut(
        total_assets_usd=round(total_assets_usd, 2),
        stock_value_usd=round(stock_value_usd, 2),
        stock_value_cny=round(stock_value_cny, 2),
        cash_usd=round(cash_usd, 2),
        cash_cny=round(cash_cny, 2),
        usd_to_cny=usd_to_cny,
    )

    return DashboardOut(
        prices=[PriceOut.model_validate(p) for p in prices],
        portfolio=portfolio,
        cash_accounts=[CashAccountOut.model_validate(c) for c in cash_accounts],
        total_assets=total_assets_data,
        recent_alerts=[AlertHistoryOut.model_validate(a) for a in recent_alerts],
        recent_transactions=[TransactionOut.model_validate(t) for t in recent_transactions],
    )
