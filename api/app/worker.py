"""Background worker for async tasks"""

import asyncio
import logging
from datetime import datetime, timedelta, date
from sqlalchemy import func, cast, Integer
from app.db.database import SessionLocal
from app.db.models import UsageEvent, UsageDaily

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def aggregate_daily_usage(target_date: date = None, db_session=None):
    """
    Aggregate usage events into daily summaries.
    
    Args:
        target_date: Date to aggregate (defaults to yesterday)
        db_session: Optional database session (for testing)
    """
    # Use provided session or create new one
    db = db_session if db_session is not None else SessionLocal()
    close_db = db_session is None  # Only close if we created it
    
    try:
        # Default to yesterday if no date specified
        if target_date is None:
            target_date = (datetime.utcnow() - timedelta(days=1)).date()
        
        logger.info(f"Aggregating usage for date: {target_date}")
        
        # Query aggregated data by tenant and date
        results = db.query(
            UsageEvent.tenant_id,
            func.date(UsageEvent.created_at).label('date'),
            func.count(UsageEvent.id).label('request_count'),
            func.sum(UsageEvent.input_tokens + UsageEvent.output_tokens).label('total_tokens'),
            func.sum(UsageEvent.input_tokens).label('total_input_tokens'),
            func.sum(UsageEvent.output_tokens).label('total_output_tokens'),
            func.sum(cast(UsageEvent.status_code >= 400, Integer)).label('error_count'),
            func.avg(UsageEvent.latency_ms).label('avg_latency_ms')
        ).filter(
            func.date(UsageEvent.created_at) == target_date
        ).group_by(
            UsageEvent.tenant_id,
            func.date(UsageEvent.created_at)
        ).all()
        
        aggregated_count = 0
        
        for row in results:
            # Convert date to Python date object if it's a string (SQLite behavior)
            row_date = row.date if isinstance(row.date, date) else datetime.strptime(row.date, '%Y-%m-%d').date()
            
            # Check if daily record already exists
            existing = db.query(UsageDaily).filter(
                UsageDaily.tenant_id == row.tenant_id,
                UsageDaily.date == row_date
            ).first()
            
            # Calculate cost estimate (placeholder - should come from pricing config)
            total_cost_cents = int((row.total_tokens or 0) * 0.01)  # $0.0001 per token
            
            if existing:
                # Update existing record
                existing.request_count = row.request_count
                existing.total_input_tokens = row.total_input_tokens or 0
                existing.total_output_tokens = row.total_output_tokens or 0
                existing.error_count = row.error_count or 0
                existing.avg_latency_ms = int(row.avg_latency_ms or 0)
                existing.total_cost_cents = total_cost_cents
                logger.info(f"Updated existing daily record for tenant {row.tenant_id}")
            else:
                # Create new daily record
                daily = UsageDaily(
                    tenant_id=row.tenant_id,
                    api_key_id=None,  # Aggregated by tenant, not by specific key
                    date=row_date,
                    model="aggregated",  # Will be updated when we aggregate per model too
                    request_count=row.request_count,
                    total_input_tokens=row.total_input_tokens or 0,
                    total_output_tokens=row.total_output_tokens or 0,
                    error_count=row.error_count or 0,
                    avg_latency_ms=int(row.avg_latency_ms or 0),
                    total_cost_cents=total_cost_cents
                )
                db.add(daily)
                logger.info(f"Created new daily record for tenant {row.tenant_id}")
            
            aggregated_count += 1
        
        db.commit()
        logger.info(f"Successfully aggregated {aggregated_count} daily records for {target_date}")
        
    except Exception as e:
        logger.error(f"Error during daily aggregation: {str(e)}")
        db.rollback()
        raise
    finally:
        if close_db:
            db.close()


async def cleanup_old_events(days_to_keep: int = 90, db_session=None):
    """
    Delete usage events older than specified days.
    
    Args:
        days_to_keep: Number of days to retain events (default: 90)
        db_session: Optional database session (for testing)
    """
    db = db_session if db_session is not None else SessionLocal()
    close_db = db_session is None
    
    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        logger.info(f"Cleaning up usage events older than {cutoff_date}")
        
        deleted_count = db.query(UsageEvent).filter(
            UsageEvent.created_at < cutoff_date
        ).delete()
        
        db.commit()
        logger.info(f"Deleted {deleted_count} old usage events")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")
        db.rollback()
        raise
    finally:
        if close_db:
            db.close()


async def worker_main():
    """Main worker loop - runs aggregation tasks periodically"""
    logger.info("Worker started - running daily aggregation tasks")
    
    while True:
        try:
            # Run daily aggregation for yesterday
            await aggregate_daily_usage()
            
            # Optionally cleanup old events (run once per day)
            current_hour = datetime.utcnow().hour
            if current_hour == 2:  # Run cleanup at 2 AM UTC
                await cleanup_old_events()
            
        except Exception as e:
            logger.error(f"Worker error: {str(e)}")
        
        # Wait 1 hour before next run
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(worker_main())
