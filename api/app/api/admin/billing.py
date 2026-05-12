"""Admin billing endpoints for Stripe management"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_admin
from app.db.models import User, Tenant, Subscription
from app.services import stripe_client
from pydantic import BaseModel, HttpUrl
from typing import Optional
import uuid


router = APIRouter()


class CreateCustomerRequest(BaseModel):
    """Request to create Stripe customer"""
    tenant_id: uuid.UUID


class CreateSubscriptionRequest(BaseModel):
    """Request to create Stripe subscription"""
    tenant_id: uuid.UUID
    stripe_price_id: str


class BillingPortalRequest(BaseModel):
    """Request to create billing portal session"""
    tenant_id: uuid.UUID
    return_url: HttpUrl


class SubscriptionResponse(BaseModel):
    """Response with subscription details"""
    subscription_id: str
    status: str
    current_period_start: Optional[int]
    current_period_end: Optional[int]


@router.post("/customers")
async def create_stripe_customer(
    request: CreateCustomerRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Create a Stripe customer for a tenant.
    
    Requires admin authentication.
    """
    # Get tenant
    tenant = db.query(Tenant).filter(Tenant.id == request.tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {request.tenant_id} not found"
        )
    
    # Check if customer already exists
    if tenant.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant already has Stripe customer: {tenant.stripe_customer_id}"
        )
    
    # Create Stripe customer
    customer_id = await stripe_client.create_customer(
        email=tenant.email,
        name=tenant.name,
        metadata={"tenant_id": str(tenant.id)}
    )
    
    # Update tenant
    tenant.stripe_customer_id = customer_id
    db.commit()
    
    return {
        "customer_id": customer_id,
        "tenant_id": str(tenant.id)
    }


@router.post("/subscriptions", response_model=SubscriptionResponse)
async def create_stripe_subscription(
    request: CreateSubscriptionRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Create a Stripe subscription for a tenant.
    
    Requires admin authentication.
    """
    # Get tenant
    tenant = db.query(Tenant).filter(Tenant.id == request.tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {request.tenant_id} not found"
        )
    
    # Check if tenant has Stripe customer
    if not tenant.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant does not have a Stripe customer. Create one first."
        )
    
    # Create Stripe subscription
    subscription_data = await stripe_client.create_subscription(
        customer_id=tenant.stripe_customer_id,
        price_id=request.stripe_price_id,
        metadata={"tenant_id": str(tenant.id)}
    )
    
    # Update or create Subscription record
    subscription = db.query(Subscription).filter(
        Subscription.tenant_id == tenant.id,
        Subscription.status.in_(["active", "trialing", "past_due"])
    ).first()
    
    if subscription:
        # Update existing
        subscription.stripe_subscription_id = subscription_data["subscription_id"]
        subscription.status = subscription_data["status"]
    else:
        # Create new - need to link to a Plan
        # For now, just update the stripe_subscription_id if subscription exists
        subscription = db.query(Subscription).filter(
            Subscription.tenant_id == tenant.id
        ).first()
        
        if subscription:
            subscription.stripe_subscription_id = subscription_data["subscription_id"]
            subscription.status = subscription_data["status"]
    
    db.commit()
    
    return SubscriptionResponse(
        subscription_id=subscription_data["subscription_id"],
        status=subscription_data["status"],
        current_period_start=subscription_data.get("current_period_start"),
        current_period_end=subscription_data.get("current_period_end")
    )


@router.post("/portal")
async def create_billing_portal_session(
    request: BillingPortalRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Create a Stripe billing portal session for a tenant.
    
    Allows customers to manage their subscription, payment methods, and invoices.
    Requires admin authentication.
    """
    # Get tenant
    tenant = db.query(Tenant).filter(Tenant.id == request.tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {request.tenant_id} not found"
        )
    
    # Check if tenant has Stripe customer
    if not tenant.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant does not have a Stripe customer"
        )
    
    # Create portal session
    portal_url = await stripe_client.create_billing_portal_session(
        customer_id=tenant.stripe_customer_id,
        return_url=str(request.return_url)
    )
    
    return {
        "url": portal_url,
        "tenant_id": str(tenant.id)
    }


@router.delete("/subscriptions/{subscription_id}")
async def cancel_stripe_subscription(
    subscription_id: str,
    immediately: bool = False,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Cancel a Stripe subscription.
    
    Args:
        subscription_id: Stripe subscription ID
        immediately: If True, cancel immediately. Otherwise, cancel at period end.
    
    Requires admin authentication.
    """
    # Find subscription in database
    subscription = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription_id
    ).first()
    
    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription {subscription_id} not found"
        )
    
    # Cancel in Stripe
    result = await stripe_client.cancel_subscription(
        subscription_id=subscription_id,
        immediately=immediately
    )
    
    # Update local status
    if immediately:
        subscription.status = "canceled"
    else:
        subscription.status = "active"  # Still active until period end
    
    db.commit()
    
    return {
        "subscription_id": subscription_id,
        "status": result["status"],
        "cancel_at_period_end": result["cancel_at_period_end"],
        "message": "Subscription canceled immediately" if immediately else "Subscription will cancel at period end"
    }


@router.get("/prices")
async def list_stripe_prices(
    admin: User = Depends(get_current_admin)
):
    """
    List available Stripe prices.
    
    Requires admin authentication.
    """
    prices = await stripe_client.list_prices(active=True)
    return {"prices": prices}
