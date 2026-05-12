"""Admin endpoints for plan and subscription management"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_admin
from app.db.models import Plan, Subscription, Tenant, User
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid


router = APIRouter()


class PlanCreate(BaseModel):
    """Request body for creating a plan"""
    name: str
    plan_type: str  # "fixed" or "metered"
    price_cents: int
    rpm_limit: int
    daily_token_quota: Optional[int] = None
    monthly_token_quota: int


class PlanResponse(BaseModel):
    """Response model for plan"""
    id: uuid.UUID
    name: str
    plan_type: str
    price_cents: int
    rpm_limit: int
    daily_token_quota: Optional[int]
    monthly_token_quota: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class SubscriptionCreate(BaseModel):
    """Request body for creating a subscription"""
    tenant_id: uuid.UUID
    plan_id: uuid.UUID
    stripe_subscription_id: Optional[str] = None


class SubscriptionResponse(BaseModel):
    """Response model for subscription"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    plan_id: uuid.UUID
    stripe_subscription_id: Optional[str]
    status: str
    current_period_start: Optional[datetime]
    current_period_end: Optional[datetime]
    created_at: datetime
    
    class Config:
        from_attributes = True


# Plan endpoints
@router.post("/plans", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    plan_data: PlanCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Create a new plan.
    
    Requires admin authentication.
    """
    # Validate plan_type
    if plan_data.plan_type not in ["fixed", "metered"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="plan_type must be 'fixed' or 'metered'"
        )
    
    plan = Plan(
        name=plan_data.name,
        plan_type=plan_data.plan_type,
        price_cents=plan_data.price_cents,
        rpm_limit=plan_data.rpm_limit,
        daily_token_quota=plan_data.daily_token_quota,
        monthly_token_quota=plan_data.monthly_token_quota
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    
    return plan


@router.get("/plans", response_model=List[PlanResponse])
async def list_plans(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    List all plans.
    
    Requires admin authentication.
    """
    plans = db.query(Plan).offset(skip).limit(limit).all()
    return plans


@router.get("/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Get plan details by ID.
    
    Requires admin authentication.
    """
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {plan_id} not found"
        )
    return plan


# Subscription endpoints
@router.post("/subscriptions", response_model=SubscriptionResponse, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    sub_data: SubscriptionCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Create a new subscription for a tenant.
    
    Requires admin authentication.
    """
    # Verify tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == sub_data.tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {sub_data.tenant_id} not found"
        )
    
    # Verify plan exists
    plan = db.query(Plan).filter(Plan.id == sub_data.plan_id).first()
    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan {sub_data.plan_id} not found"
        )
    
    # Check if tenant already has an active subscription
    existing = db.query(Subscription).filter(
        Subscription.tenant_id == sub_data.tenant_id,
        Subscription.status == "active"
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant already has an active subscription (id: {existing.id})"
        )
    
    subscription = Subscription(
        tenant_id=sub_data.tenant_id,
        plan_id=sub_data.plan_id,
        stripe_subscription_id=sub_data.stripe_subscription_id,
        status="active",
        current_period_start=datetime.utcnow(),
        current_period_end=None  # Will be set by Stripe webhook or manual update
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    
    return subscription


@router.get("/subscriptions", response_model=List[SubscriptionResponse])
async def list_subscriptions(
    tenant_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    List subscriptions, optionally filtered by tenant.
    
    Requires admin authentication.
    """
    query = db.query(Subscription)
    
    if tenant_id:
        query = query.filter(Subscription.tenant_id == tenant_id)
    
    subscriptions = query.offset(skip).limit(limit).all()
    return subscriptions


@router.patch("/subscriptions/{subscription_id}/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    subscription_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Cancel a subscription (sets status to 'canceled').
    
    Requires admin authentication.
    """
    subscription = db.query(Subscription).filter(Subscription.id == subscription_id).first()
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription {subscription_id} not found"
        )
    
    if subscription.status == "canceled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription is already canceled"
        )
    
    subscription.status = "canceled"
    db.commit()
    db.refresh(subscription)
    
    return subscription
