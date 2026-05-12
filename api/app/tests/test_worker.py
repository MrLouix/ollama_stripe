"""Unit tests for worker and aggregation functions"""

import pytest
from datetime import datetime, timedelta, date
from app.worker import aggregate_daily_usage, cleanup_old_events
from app.db.models import UsageEvent, UsageDaily, Tenant, ApiKey
from app.services.auth import generate_api_key
from sqlalchemy.orm import Session


@pytest.fixture
def test_tenant_for_worker(db_session: Session):
    """Create a test tenant for worker tests"""
    tenant = Tenant(name="Worker Test Tenant", email="worker@example.com")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def test_api_key_for_worker(db_session: Session, test_tenant_for_worker: Tenant):
    """Create a test API key for worker tests"""
    key, key_hash, key_prefix = generate_api_key()
    api_key = ApiKey(
        tenant_id=test_tenant_for_worker.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name="Worker Test Key"
    )
    db_session.add(api_key)
    db_session.commit()
    db_session.refresh(api_key)
    return api_key


@pytest.mark.asyncio
async def test_aggregate_daily_usage_creates_new_record(
    db_session: Session,
    test_tenant_for_worker: Tenant,
    test_api_key_for_worker: ApiKey
):
    """Test that aggregation creates a new daily record"""
    yesterday = datetime.utcnow() - timedelta(days=1)
    target_date = yesterday.date()
    
    # Create some usage events for yesterday
    for i in range(5):
        event = UsageEvent(
            tenant_id=test_tenant_for_worker.id,
            api_key_id=test_api_key_for_worker.id,
            model="llama3",
            input_tokens=10,
            output_tokens=20,
            latency_ms=500,
            status_code=200,
            created_at=yesterday
        )
        db_session.add(event)
    db_session.commit()
    
    # Run aggregation
    await aggregate_daily_usage(target_date, db_session=db_session)
    
    # Verify daily record was created
    daily = db_session.query(UsageDaily).filter(
        UsageDaily.tenant_id == test_tenant_for_worker.id,
        UsageDaily.date == target_date
    ).first()
    
    assert daily is not None
    assert daily.request_count == 5
    assert daily.total_input_tokens == 50
    assert daily.total_output_tokens == 100


@pytest.mark.asyncio
async def test_aggregate_daily_usage_updates_existing_record(
    db_session: Session,
    test_tenant_for_worker: Tenant,
    test_api_key_for_worker: ApiKey
):
    """Test that aggregation updates an existing daily record"""
    yesterday = datetime.utcnow() - timedelta(days=1)
    target_date = yesterday.date()
    
    # Create existing daily record
    existing_daily = UsageDaily(
        tenant_id=test_tenant_for_worker.id,
        date=target_date,
        model="llama3",
        request_count=3,
        total_input_tokens=30,
        total_output_tokens=60,
        error_count=0,
        avg_latency_ms=400,
        total_cost_cents=1
    )
    db_session.add(existing_daily)
    db_session.commit()
    
    # Create new usage events
    for i in range(5):
        event = UsageEvent(
            tenant_id=test_tenant_for_worker.id,
            api_key_id=test_api_key_for_worker.id,
            model="llama3",
            input_tokens=10,
            output_tokens=20,
            latency_ms=500,
            status_code=200,
            created_at=yesterday
        )
        db_session.add(event)
    db_session.commit()
    
    # Run aggregation
    await aggregate_daily_usage(target_date, db_session=db_session)
    
    # Verify daily record was updated (not duplicated)
    daily_records = db_session.query(UsageDaily).filter(
        UsageDaily.tenant_id == test_tenant_for_worker.id,
        UsageDaily.date == target_date
    ).all()
    
    assert len(daily_records) == 1
    daily = daily_records[0]
    assert daily.request_count == 5  # Updated to new count
    assert daily.total_input_tokens == 50
    assert daily.total_output_tokens == 100


@pytest.mark.asyncio
async def test_aggregate_daily_usage_with_errors(
    db_session: Session,
    test_tenant_for_worker: Tenant,
    test_api_key_for_worker: ApiKey
):
    """Test aggregation correctly counts error responses"""
    yesterday = datetime.utcnow() - timedelta(days=1)
    target_date = yesterday.date()
    
    # Create events with some errors
    for i in range(3):
        event = UsageEvent(
            tenant_id=test_tenant_for_worker.id,
            api_key_id=test_api_key_for_worker.id,
            model="llama3",
            input_tokens=10,
            output_tokens=20,
            latency_ms=500,
            status_code=200,
            created_at=yesterday
        )
        db_session.add(event)
    
    # Add error events
    for i in range(2):
        event = UsageEvent(
            tenant_id=test_tenant_for_worker.id,
            api_key_id=test_api_key_for_worker.id,
            model="llama3",
            input_tokens=10,
            output_tokens=0,
            latency_ms=100,
            status_code=500,
            error_type="internal_error",
            created_at=yesterday
        )
        db_session.add(event)
    db_session.commit()
    
    # Run aggregation
    await aggregate_daily_usage(target_date, db_session=db_session)
    
    # Verify error count
    daily = db_session.query(UsageDaily).filter(
        UsageDaily.tenant_id == test_tenant_for_worker.id,
        UsageDaily.date == target_date
    ).first()
    
    assert daily is not None
    assert daily.request_count == 5
    assert daily.error_count == 2


@pytest.mark.asyncio
async def test_aggregate_daily_usage_defaults_to_yesterday(
    db_session: Session,
    test_tenant_for_worker: Tenant,
    test_api_key_for_worker: ApiKey
):
    """Test that aggregation defaults to yesterday when no date specified"""
    yesterday = datetime.utcnow() - timedelta(days=1)
    
    # Create event for yesterday
    event = UsageEvent(
        tenant_id=test_tenant_for_worker.id,
        api_key_id=test_api_key_for_worker.id,
        model="llama3",
        input_tokens=10,
        output_tokens=20,
        latency_ms=500,
        status_code=200,
        created_at=yesterday
    )
    db_session.add(event)
    db_session.commit()
    
    # Run aggregation without specifying date
    await aggregate_daily_usage(db_session=db_session)
    
    # Verify daily record was created for yesterday
    daily = db_session.query(UsageDaily).filter(
        UsageDaily.tenant_id == test_tenant_for_worker.id,
        UsageDaily.date == yesterday.date()
    ).first()
    
    assert daily is not None
    assert daily.request_count == 1


@pytest.mark.asyncio
async def test_cleanup_old_events(
    db_session: Session,
    test_tenant_for_worker: Tenant,
    test_api_key_for_worker: ApiKey
):
    """Test that old usage events are deleted"""
    # Create old events (100 days ago)
    old_date = datetime.utcnow() - timedelta(days=100)
    for i in range(5):
        event = UsageEvent(
            tenant_id=test_tenant_for_worker.id,
            api_key_id=test_api_key_for_worker.id,
            model="llama3",
            input_tokens=10,
            output_tokens=20,
            latency_ms=500,
            status_code=200,
            created_at=old_date
        )
        db_session.add(event)
    
    # Create recent events (10 days ago)
    recent_date = datetime.utcnow() - timedelta(days=10)
    for i in range(3):
        event = UsageEvent(
            tenant_id=test_tenant_for_worker.id,
            api_key_id=test_api_key_for_worker.id,
            model="llama3",
            input_tokens=10,
            output_tokens=20,
            latency_ms=500,
            status_code=200,
            created_at=recent_date
        )
        db_session.add(event)
    db_session.commit()
    
    # Run cleanup (keep events from last 90 days)
    await cleanup_old_events(days_to_keep=90, db_session=db_session)
    
    # Verify old events were deleted
    remaining_events = db_session.query(UsageEvent).filter(
        UsageEvent.tenant_id == test_tenant_for_worker.id
    ).all()
    
    assert len(remaining_events) == 3  # Only recent events remain
    for event in remaining_events:
        assert event.created_at >= datetime.utcnow() - timedelta(days=90)


@pytest.mark.asyncio
async def test_cleanup_old_events_custom_retention(
    db_session: Session,
    test_tenant_for_worker: Tenant,
    test_api_key_for_worker: ApiKey
):
    """Test cleanup with custom retention period"""
    # Create events 40 days ago
    date_40_days = datetime.utcnow() - timedelta(days=40)
    for i in range(3):
        event = UsageEvent(
            tenant_id=test_tenant_for_worker.id,
            api_key_id=test_api_key_for_worker.id,
            model="llama3",
            input_tokens=10,
            output_tokens=20,
            latency_ms=500,
            status_code=200,
            created_at=date_40_days
        )
        db_session.add(event)
    
    # Create events 10 days ago
    date_10_days = datetime.utcnow() - timedelta(days=10)
    for i in range(2):
        event = UsageEvent(
            tenant_id=test_tenant_for_worker.id,
            api_key_id=test_api_key_for_worker.id,
            model="llama3",
            input_tokens=10,
            output_tokens=20,
            latency_ms=500,
            status_code=200,
            created_at=date_10_days
        )
        db_session.add(event)
    db_session.commit()
    
    # Run cleanup (keep only last 30 days)
    await cleanup_old_events(days_to_keep=30, db_session=db_session)
    
    # Verify only events from last 30 days remain
    remaining_events = db_session.query(UsageEvent).filter(
        UsageEvent.tenant_id == test_tenant_for_worker.id
    ).all()
    
    assert len(remaining_events) == 2  # Only 10-day-old events remain
