"""Alert settings & history endpoints.

Supports multi-level alerts: each symbol can have a primary alert (is_primary=True)
and multiple sub-level alerts (is_primary=False) for different price targets.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    AlertSetting, AlertHistory, PriceCache,
    AlertSettingCreate, AlertSettingUpdate, AlertSettingOut, AlertHistoryOut,
)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# ── Grouped response schema ──────────────────────────────────────────────────

class AlertGroupOut(BaseModel):
    """A stock symbol with its primary alert and sub-level alerts."""
    symbol: str
    name: str
    market: str
    current_price: Optional[float] = None
    change_pct: Optional[float] = None
    primary: Optional[AlertSettingOut] = None
    levels: List[AlertSettingOut] = []


# ── Alert Settings ────────────────────────────────────────────────────────────

@router.get("", response_model=List[AlertSettingOut])
def list_alerts(db: Session = Depends(get_db)):
    """List all alert settings (flat list)."""
    return db.query(AlertSetting).order_by(AlertSetting.symbol, AlertSetting.is_primary.desc()).all()


@router.get("/grouped", response_model=List[AlertGroupOut])
def list_alerts_grouped(db: Session = Depends(get_db)):
    """List alerts grouped by stock symbol, with current prices."""
    alerts = db.query(AlertSetting).order_by(AlertSetting.symbol, AlertSetting.is_primary.desc()).all()

    # Group by symbol
    groups: Dict[str, AlertGroupOut] = {}
    for alert in alerts:
        sym = alert.symbol
        if sym not in groups:
            cached = db.query(PriceCache).filter(PriceCache.symbol == sym).first()
            groups[sym] = AlertGroupOut(
                symbol=sym,
                name=alert.name or sym,
                market=alert.market.value,
                current_price=cached.price if cached else None,
                change_pct=cached.change_pct if cached else None,
            )

        alert_out = AlertSettingOut.model_validate(alert)
        if getattr(alert, 'is_primary', True):
            groups[sym].primary = alert_out
            # Use primary's name as the group name
            groups[sym].name = alert.name or sym
        else:
            groups[sym].levels.append(alert_out)

    return list(groups.values())


@router.post("", response_model=AlertSettingOut, status_code=201)
def create_alert(payload: AlertSettingCreate, db: Session = Depends(get_db)):
    """Create an alert setting.

    If is_primary=True and a primary alert for the same symbol already exists,
    the existing one is updated instead.
    For sub-level alerts (is_primary=False), a new record is always created.
    """
    symbol = payload.symbol.upper()

    if payload.is_primary:
        existing = db.query(AlertSetting).filter(
            AlertSetting.symbol == symbol,
            AlertSetting.is_primary == True,
        ).first()

        if existing:
            for field, value in payload.model_dump(exclude_unset=True).items():
                if field == "symbol":
                    value = value.upper()
                setattr(existing, field, value)
            db.commit()
            db.refresh(existing)
            return existing

    alert = AlertSetting(
        symbol=symbol,
        name=payload.name,
        market=payload.market,
        target_buy=payload.target_buy,
        target_sell=payload.target_sell,
        stop_loss=payload.stop_loss,
        enabled=payload.enabled,
        is_primary=payload.is_primary,
        label=payload.label,
        amount=payload.amount,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


@router.put("/{alert_id}", response_model=AlertSettingOut)
def update_alert(alert_id: int, payload: AlertSettingUpdate, db: Session = Depends(get_db)):
    """Update alert settings. Explicitly set fields to null to clear them."""
    alert = db.query(AlertSetting).filter(AlertSetting.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(alert, field, value)
    db.commit()
    db.refresh(alert)
    return alert


@router.delete("/{alert_id}", status_code=204)
def delete_alert(alert_id: int, db: Session = Depends(get_db)):
    """Delete an alert setting."""
    alert = db.query(AlertSetting).filter(AlertSetting.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    db.delete(alert)
    db.commit()


# ── Test Alert ────────────────────────────────────────────────────────────────

@router.post("/test-send")
def test_alert_send():
    """Send a test alert to verify Telegram integration."""
    from ..services.alert_service import send_telegram_alert
    msg = "🧪 Portfolio Monitor 告警推送测试\n\n如果你能看到这条消息，说明告警推送配置正确！"
    sent = send_telegram_alert(msg)
    return {"sent": sent, "message": "Test alert sent" if sent else "Test alert failed"}


# ── Alert History ─────────────────────────────────────────────────────────────

@router.get("/history", response_model=List[AlertHistoryOut])
def alert_history(
    symbol: Optional[str] = None,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """Get alert history."""
    q = db.query(AlertHistory).order_by(AlertHistory.triggered_at.desc())
    if symbol:
        q = q.filter(AlertHistory.symbol == symbol.upper())
    return q.limit(limit).all()
