"""Cash account management endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CashAccount, CashAccountOut, CashAccountUpdate, CurrencyType, gen_id, utcnow

router = APIRouter(prefix="/api/cash", tags=["cash"])


@router.get("", response_model=List[CashAccountOut])
def list_cash_accounts(db: Session = Depends(get_db)):
    """Get all cash account balances."""
    accounts = db.query(CashAccount).all()
    return accounts


@router.get("/{currency}", response_model=CashAccountOut)
def get_cash_account(currency: CurrencyType, db: Session = Depends(get_db)):
    """Get a specific cash account balance."""
    account = db.query(CashAccount).filter(CashAccount.currency == currency.value).first()
    if not account:
        raise HTTPException(status_code=404, detail=f"Cash account for {currency.value} not found")
    return account


@router.post("/adjust", response_model=CashAccountOut)
def adjust_cash(payload: CashAccountUpdate, db: Session = Depends(get_db)):
    """Adjust cash balance (deposit or withdraw).
    
    - amount > 0: deposit (存入)
    - amount < 0: withdraw (取出)
    """
    account = db.query(CashAccount).filter(CashAccount.currency == payload.currency.value).first()
    
    if not account:
        # Create new account if not exists
        account = CashAccount(
            currency=payload.currency.value,
            balance=max(0.0, payload.amount),  # Can't have negative initial balance
            updated_at=utcnow(),
        )
        db.add(account)
    else:
        new_balance = account.balance + payload.amount
        if new_balance < 0:
            raise HTTPException(
                status_code=400, 
                detail=f"Insufficient balance. Current: {account.balance}, Requested: {payload.amount}"
            )
        account.balance = new_balance
        account.updated_at = utcnow()
    
    db.commit()
    db.refresh(account)
    return account


@router.post("/init", status_code=201)
def init_cash_accounts(db: Session = Depends(get_db)):
    """Initialize default cash accounts with zero balance."""
    currencies = [CurrencyType.usd, CurrencyType.cny]
    created = []
    
    for curr in currencies:
        existing = db.query(CashAccount).filter(CashAccount.currency == curr.value).first()
        if not existing:
            account = CashAccount(
                currency=curr.value,
                balance=0.0,
                updated_at=utcnow(),
            )
            db.add(account)
            created.append(curr.value)
    
    db.commit()
    return {"message": f"Created cash accounts: {created}"}
