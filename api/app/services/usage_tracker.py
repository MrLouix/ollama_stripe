"""Usage event tracking service"""

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.models import UsageEvent
import uuid


async def track_usage(
    db: Session,
    tenant_id: uuid.UUID,
    api_key_id: uuid.UUID,
    model: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    status_code: int,
    error_message: str = None
) -> UsageEvent:
    """
    Create usage event record
    
    Args:
        db: Database session
        tenant_id: Tenant UUID
        api_key_id: API key UUID
        model: Model name used
        input_tokens: Prompt tokens count
        output_tokens: Completion tokens count
        latency_ms: Response latency in milliseconds
        status_code: HTTP status code
        error_message: Optional error message
    
    Returns:
        Created UsageEvent instance
    """
    usage_event = UsageEvent(
        tenant_id=tenant_id,
        api_key_id=api_key_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        # total_tokens is a generated column in the database
        latency_ms=latency_ms,
        status_code=status_code,
        error_message=error_message,
        created_at=datetime.now(timezone.utc)
    )
    
    db.add(usage_event)
    db.commit()
    db.refresh(usage_event)
    
    return usage_event
