"""Database migration script to add HKD support for Hong Kong stocks.

This script adds:
1. New columns to asset_snapshots table for HKD values
2. Initializes HKD cash account if not exists
3. Updates existing data structures to support three currencies

Run this script after deploying the backend code changes.
"""

import sys
import os

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app.database import engine, SessionLocal, init_db
from app.models import CashAccount, CurrencyType, utcnow
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_asset_snapshots_table():
    """Add new columns to asset_snapshots table for HKD support."""
    logger.info("Checking asset_snapshots table structure...")
    
    with engine.connect() as conn:
        # Get PRAGMA table_info to check existing columns
        result = conn.execute(text("PRAGMA table_info(asset_snapshots)"))
        rows = result.fetchall()
        existing_columns = [row[1] for row in rows]  # Second element is column name
        
        migrations_needed = []
        
        if 'stock_value_hkd' not in existing_columns:
            migrations_needed.append("ADD COLUMN stock_value_hkd REAL DEFAULT 0.0")
            
        if 'cash_hkd' not in existing_columns:
            migrations_needed.append("ADD COLUMN cash_hkd REAL DEFAULT 0.0")
        
        if migrations_needed:
            alter_sql = f"ALTER TABLE asset_snapshots {', '.join(migrations_needed)}"
            logger.info(f"Executing SQL: {alter_sql}")
            conn.execute(text(alter_sql))
            conn.commit()
            logger.info("✅ Added HKD columns to asset_snapshots table")
        else:
            logger.info("ℹ️  HKD columns already exist in asset_snapshots table")


def initialize_hkd_cash_account():
    """Initialize HKD cash account if it doesn't exist."""
    logger.info("Initializing HKD cash account...")
    
    db = SessionLocal()
    try:
        existing = db.query(CashAccount).filter(CashAccount.currency == CurrencyType.hkd.value).first()
        
        if not existing:
            account = CashAccount(
                currency=CurrencyType.hkd.value,
                balance=0.0,
                updated_at=utcnow(),
            )
            db.add(account)
            db.commit()
            logger.info("✅ Created HKD cash account with zero balance")
        else:
            logger.info("ℹ️  HKD cash account already exists")
            
    except Exception as e:
        logger.error(f"❌ Failed to initialize HKD cash account: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def verify_migration():
    """Verify that all migrations were applied successfully."""
    logger.info("\nVerifying migration...")
    
    with engine.connect() as conn:
        # Verify asset_snapshots columns using PRAGMA
        result = conn.execute(text("PRAGMA table_info(asset_snapshots)"))
        rows = result.fetchall()
        columns = [row[1] for row in rows]
        
        required_columns = ['stock_value_hkd', 'cash_hkd']
        missing = [col for col in required_columns if col not in columns]
        
        if missing:
            logger.error(f"❌ Missing columns in asset_snapshots: {missing}")
            return False
            
        logger.info("✅ All required database columns present")
    
    # Verify HKD cash account
    db = SessionLocal()
    try:
        hkd_account = db.query(CashAccount).filter(CashAccount.currency == CurrencyType.hkd.value).first()
        if hkd_account:
            logger.info(f"✅ HKD cash account verified (balance: {hkd_account.balance:.2f})")
            return True
        else:
            logger.error("❌ HKD cash account not found")
            return False
    finally:
        db.close()


def main():
    """Main migration function."""
    print("=" * 60)
    logger.info("Starting HKD Support Migration")
    print("=" * 60)
    
    try:
        # Step 0: Initialize database if not exists
        logger.info("Ensuring database tables exist...")
        init_db()
        logger.info("✅ Database initialized")
        
        # Step 1: Migrate database schema
        migrate_asset_snapshots_table()
        
        # Step 2: Initialize HKD cash account
        initialize_hkd_cash_account()
        
        # Step 3: Verify migration
        if verify_migration():
            print("\n" + "=" * 60)
            logger.info("✅ HKD SUPPORT MIGRATION COMPLETED SUCCESSFULLY!")
            print("=" * 60)
            logger.info("\nThe system now supports:")
            logger.info("  • Three markets: US (.ss/.sz), China (.CN), Hong Kong (.HK)")
            logger.info("  • Three currencies: USD, CNY, HKD")
            logger.info("  • Automatic currency detection from stock codes")
            logger.info("  • Real-time exchange rates for all currency pairs")
            logger.info("\nNext steps:")
            logger.info("  1. Restart the backend service")
            logger.info("  2. Test adding HK stocks (e.g., 0700.HK for Tencent)")
            logger.info("  3. Verify dashboard shows separate HK stock section")
            logger.info("  4. Check that HKD cash account appears in cash management")
            return 0
        else:
            logger.error("\n❌ Migration verification failed!")
            return 1
            
    except Exception as e:
        logger.error(f"\n❌ Migration failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())