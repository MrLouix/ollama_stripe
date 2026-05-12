"""Admin endpoints for usage monitoring and quota status"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from redis import Redis
from app.dependencies import get_db, get_redis, get_current_admin
from app.db.models import UsageEvent, UsageDaily, Tenant, Subscription, User
from app.services.quota import get_quota_status
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date
import uuid


router = APIRouter()


class UsageEventResponse(BaseModel):
    """Response model for usage event"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    api_key_id: uuid.UUID
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    status_code: int
    error_message: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class UsageDailyResponse(BaseModel):
    """Response model for daily usage aggregation"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    date: date
    total_requests: int
    total_tokens: int
    total_cost_cents: int
    
    class Config:
        from_attributes = True


class QuotaStatusResponse(BaseModel):
    """Response model for quota status"""
    tenant_id: uuid.UUID
    tenant_name: str
    plan_name: str
    rpm_limit: int
    daily_used: int
    daily_limit: Optional[int]
    daily_remaining: Optional[int]
    daily_percentage: Optional[float]
    monthly_used: int
    monthly_limit: int
    monthly_remaining: int
    monthly_percentage: float


class UsageStatsResponse(BaseModel):
    """Response model for usage statistics"""
    tenant_id: uuid.UUID
    total_requests: int
    total_tokens: int
    avg_latency_ms: float
    error_rate: float


@router.get("/usage/events", response_model=List[UsageEventResponse])
async def list_usage_events(
    tenant_id: Optional[uuid.UUID] = None,
    api_key_id: Optional[uuid.UUID] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    skip: int = 0,
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    List usage events with optional filters.
    
    Filters:
    - tenant_id: Filter by tenant
    - api_key_id: Filter by API key
    - start_date: Filter events after this date
    - end_date: Filter events before this date
    
    Requires admin authentication.
    """
    query = db.query(UsageEvent)
    
    if tenant_id:
        query = query.filter(UsageEvent.tenant_id == tenant_id)
    if api_key_id:
        query = query.filter(UsageEvent.api_key_id == api_key_id)
    if start_date:
        query = query.filter(UsageEvent.created_at >= start_date)
    if end_date:
        query = query.filter(UsageEvent.created_at <= end_date)
    
    events = query.order_by(UsageEvent.created_at.desc()).offset(skip).limit(limit).all()
    return events


@router.get("/usage/daily", response_model=List[UsageDailyResponse])
async def list_daily_usage(
    tenant_id: Optional[uuid.UUID] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    skip: int = 0,
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    List daily usage aggregations with optional filters.
    
    Requires admin authentication.
    """
    query = db.query(UsageDaily)
    
    if tenant_id:
        query = query.filter(UsageDaily.tenant_id == tenant_id)
    if start_date:
        query = query.filter(UsageDaily.date >= start_date)
    if end_date:
        query = query.filter(UsageDaily.date <= end_date)
    
    daily = query.order_by(UsageDaily.date.desc()).offset(skip).limit(limit).all()
    return daily


@router.get("/usage/stats/{tenant_id}", response_model=UsageStatsResponse)
async def get_usage_stats(
    tenant_id: uuid.UUID,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Get usage statistics for a tenant.
    
    Returns total requests, tokens, average latency, and error rate.
    Requires admin authentication.
    """
    # Verify tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )
    
    query = db.query(
        func.count(UsageEvent.id).label('total_requests'),
        func.sum(UsageEvent.total_tokens).label('total_tokens'),
        func.avg(UsageEvent.latency_ms).label('avg_latency_ms'),
        func.sum(func.cast(UsageEvent.status_code >= 400, db.Integer)).label('error_count')
    ).filter(UsageEvent.tenant_id == tenant_id)
    
    if start_date:
        query = query.filter(UsageEvent.created_at >= start_date)
    if end_date:
        query = query.filter(UsageEvent.created_at <= end_date)
    
    result = query.first()
    
    total_requests = result.total_requests or 0
    total_tokens = result.total_tokens or 0
    avg_latency_ms = float(result.avg_latency_ms or 0)
    error_count = result.error_count or 0
    
    error_rate = (error_count / total_requests * 100) if total_requests > 0 else 0.0
    
    return UsageStatsResponse(
        tenant_id=tenant_id,
        total_requests=total_requests,
        total_tokens=total_tokens,
        avg_latency_ms=avg_latency_ms,
        error_rate=error_rate
    )


@router.get("/quota/{tenant_id}", response_model=QuotaStatusResponse)
async def get_tenant_quota_status(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    admin: User = Depends(get_current_admin)
):
    """
    Get current quota status for a tenant.
    
    Shows daily and monthly usage with percentages.
    Requires admin authentication.
    """
    # Verify tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )
    
    # Get active subscription and plan
    subscription = db.query(Subscription).filter(
        Subscription.tenant_id == tenant_id,
        Subscription.status == "active"
    ).first()
    
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active subscription found for tenant {tenant_id}"
        )
    
    plan = subscription.plan
    
    # Get quota status from Redis
    quota_status = get_quota_status(redis, str(tenant_id), plan)
    
    return QuotaStatusResponse(
        tenant_id=tenant_id,
        tenant_name=tenant.name,
        plan_name=plan.name,
        rpm_limit=quota_status["rpm_limit"],
        daily_used=quota_status["daily_used"],
        daily_limit=quota_status["daily_limit"],
        daily_remaining=quota_status["daily_remaining"],
        daily_percentage=quota_status["daily_percentage"],
        monthly_used=quota_status["monthly_used"],
        monthly_limit=quota_status["monthly_limit"],
        monthly_remaining=quota_status["monthly_remaining"],
        monthly_percentage=quota_status["monthly_percentage"]
    )
