"""Quant signal endpoints — fundamental valuation analysis."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import QuantSignal, QuantSignalOut, QuantSignalSummary, AlertSetting

logger = logging.getLogger("quant")

router = APIRouter(prefix="/api/quant", tags=["quant"])

# Symbol name mapping
SYMBOL_NAMES = {
    "BABA": "阿里巴巴",
    "TME": "腾讯音乐",
    "GOOGL": "谷歌",
    "MSFT": "微软",
    "NVDA": "英伟达",
    "META": "Meta",
    "510300.SS": "沪深300ETF",
}

SYMBOL_MARKETS = {
    "BABA": "us",
    "TME": "us",
    "GOOGL": "us",
    "MSFT": "us",
    "NVDA": "us",
    "META": "us",
    "510300.SS": "cn",
}

# Metric weights for composite score (lower percentile = cheaper = higher score)
METRIC_WEIGHTS = {
    "pe_ttm": 0.35,
    "pb": 0.25,
    "roe": 0.15,       # Higher is better (invert in scoring)
    "gross_margin": 0.10,  # Higher is better
    "revenue_growth": 0.15,  # Higher is better
}

# Metrics where higher = better (invert percentile for scoring)
HIGHER_IS_BETTER = {"roe", "gross_margin", "revenue_growth"}


def compute_composite_score(metrics: dict) -> Optional[float]:
    """Compute composite valuation score (0-100, lower = cheaper/better value).
    
    For PE/PB: lower percentile = cheaper = better value
    For ROE/margins/growth: higher percentile = better fundamentals
    
    Final score: 0 = very cheap, 100 = very expensive
    """
    if not metrics:
        return None
    
    weighted_sum = 0.0
    total_weight = 0.0
    
    for metric_name, weight in METRIC_WEIGHTS.items():
        if metric_name in metrics and metrics[metric_name].get("percentile") is not None:
            pct = metrics[metric_name]["percentile"]
            if metric_name in HIGHER_IS_BETTER:
                # Invert: high ROE/growth is good -> should lower the "expensiveness" score
                pct = 100 - pct
            weighted_sum += pct * weight
            total_weight += weight
    
    if total_weight == 0:
        return None
    
    return round(weighted_sum / total_weight, 1)


@router.get("/signals", response_model=List[QuantSignalSummary])
def get_all_signals(db: Session = Depends(get_db)):
    """Get latest quant signals for all symbols."""
    
    # Get all unique symbols with their latest data
    symbols = db.query(QuantSignal.symbol).distinct().all()
    symbol_list = [s[0] for s in symbols]
    
    if not symbol_list:
        return []
    
    results = []
    for symbol in sorted(symbol_list):
        # Get latest entry for each metric
        metrics = {}
        for metric_name in ["pe_ttm", "pb", "roe", "gross_margin", "revenue_growth"]:
            latest = db.query(QuantSignal).filter(
                QuantSignal.symbol == symbol,
                QuantSignal.metric == metric_name,
            ).order_by(desc(QuantSignal.date)).first()
            
            if latest and latest.value is not None:
                metrics[metric_name] = {
                    "value": latest.value,
                    "percentile": latest.percentile,
                }
        
        if not metrics:
            continue
        
        score = compute_composite_score(metrics)
        
        results.append(QuantSignalSummary(
            symbol=symbol,
            name=SYMBOL_NAMES.get(symbol, symbol),
            market=SYMBOL_MARKETS.get(symbol, "us"),
            metrics=metrics,
            score=score,
        ))
    
    return results


@router.get("/signals/{symbol}", response_model=List[QuantSignalOut])
def get_symbol_signals(symbol: str, metric: Optional[str] = None, db: Session = Depends(get_db)):
    """Get historical signal data for a specific symbol."""
    symbol = symbol.upper()
    
    q = db.query(QuantSignal).filter(QuantSignal.symbol == symbol)
    if metric:
        q = q.filter(QuantSignal.metric == metric)
    
    signals = q.order_by(QuantSignal.date.asc()).all()
    
    if not signals:
        raise HTTPException(status_code=404, detail=f"No signals found for {symbol}")
    
    return signals


@router.post("/refresh")
def refresh_signals(db: Session = Depends(get_db)):
    """Manually trigger a data refresh — runs synchronously and returns result."""
    import sys
    import os
    # 确保 scripts 目录在 path 里
    scripts_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'scripts')
    scripts_dir = os.path.abspath(scripts_dir)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    
    try:
        from fetch_fundamentals import refresh_all_signals
        count = refresh_all_signals()
        logger.info(f"Manual refresh completed: {count} signals updated")
        return {"status": "ok", "count": count, "message": f"Updated {count} signals"}
    except Exception as e:
        logger.error(f"Manual refresh failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
