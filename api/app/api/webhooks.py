"""Stripe webhook handlers"""

import logging
import stripe
from fastapi import APIRouter, Request, HTTPException, Depends, status
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.db.models import Tenant, Subscription, BillingEvent, ApiKey
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handle Stripe webhook events.
    
    Supported events:
    - invoice.paid: Confirm subscription activation
    - invoice.payment_failed: Handle payment failure
    - customer.subscription.created: New subscription
    - customer.subscription.updated: Subscription changes
    - customer.subscription.deleted: Subscription cancellation
    """
    # Get raw payload and signature
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not sig_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe signature header"
        )
    
    # Verify webhook signature
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payload"
        )
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid signature"
        )
    
    # Extract event data
    event_type = event["type"]
    event_data = event["data"]["object"]
    
    logger.info(f"Received Stripe webhook: {event_type} (ID: {event['id']})")
    
    # Get tenant from customer ID
    customer_id = event_data.get("customer")
    tenant = None
    
    if customer_id:
        tenant = db.query(Tenant).filter(
            Tenant.stripe_customer_id == customer_id
        ).first()
    
    # Log billing event if tenant found
    if tenant:
        billing_event = BillingEvent(
            tenant_id=tenant.id,
            event_type=event_type,
            stripe_event_id=event["id"],
            payload=event_data
        )
        db.add(billing_event)
        db.commit()
        logger.info(f"Logged billing event for tenant {tenant.id}")
    else:
        logger.warning(f"Tenant not found for customer {customer_id}")
    
    # Handle specific event types
    try:
        if event_type == "invoice.paid":
            await handle_invoice_paid(db, event_data, tenant)
        
        elif event_type == "invoice.payment_failed":
            await handle_payment_failed(db, event_data, tenant)
        
        elif event_type == "customer.subscription.created":
            await handle_subscription_created(db, event_data, tenant)
        
        elif event_type == "customer.subscription.updated":
            await handle_subscription_updated(db, event_data, tenant)
        
        elif event_type == "customer.subscription.deleted":
            await handle_subscription_deleted(db, event_data, tenant)
        
        else:
            logger.info(f"Unhandled event type: {event_type}")
    
    except Exception as e:
        logger.error(f"Error handling webhook event {event_type}: {str(e)}")
        # Don't raise - return 200 to Stripe to avoid retries
    
    return {"status": "success"}


async def handle_invoice_paid(db: Session, event_data: dict, tenant: Tenant):
    """Handle successful invoice payment"""
    if not tenant:
        return
    
    subscription_id = event_data.get("subscription")
    if not subscription_id:
        return
    
    # Activate subscription
    subscription = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription_id
    ).first()
    
    if subscription:
        subscription.status = "active"
        db.commit()
        logger.info(f"Activated subscription {subscription_id} for tenant {tenant.id}")


async def handle_payment_failed(db: Session, event_data: dict, tenant: Tenant):
    """Handle failed payment"""
    if not tenant:
        return
    
    subscription_id = event_data.get("subscription")
    
    # Mark subscription as past_due
    if subscription_id:
        subscription = db.query(Subscription).filter(
            Subscription.stripe_subscription_id == subscription_id
        ).first()
        
        if subscription:
            subscription.status = "past_due"
            db.commit()
            logger.warning(f"Subscription {subscription_id} marked as past_due for tenant {tenant.id}")
    
    # TODO: Send alert email to tenant and admin


async def handle_subscription_created(db: Session, event_data: dict, tenant: Tenant):
    """Handle new subscription creation"""
    if not tenant:
        return
    
    subscription_id = event_data["id"]
    logger.info(f"New subscription {subscription_id} created for tenant {tenant.id}")
    
    # Update subscription status if exists
    subscription = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription_id
    ).first()
    
    if subscription:
        subscription.status = event_data.get("status", "active")
        subscription.current_period_start = event_data.get("current_period_start")
        subscription.current_period_end = event_data.get("current_period_end")
        db.commit()


async def handle_subscription_updated(db: Session, event_data: dict, tenant: Tenant):
    """Handle subscription updates"""
    if not tenant:
        return
    
    subscription_id = event_data["id"]
    new_status = event_data.get("status")
    
    subscription = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription_id
    ).first()
    
    if subscription:
        subscription.status = new_status
        subscription.current_period_start = event_data.get("current_period_start")
        subscription.current_period_end = event_data.get("current_period_end")
        db.commit()
        logger.info(f"Updated subscription {subscription_id} status to {new_status}")


async def handle_subscription_deleted(db: Session, event_data: dict, tenant: Tenant):
    """Handle subscription cancellation"""
    if not tenant:
        return
    
    subscription_id = event_data["id"]
    
    # Cancel subscription
    subscription = db.query(Subscription).filter(
        Subscription.stripe_subscription_id == subscription_id
    ).first()
    
    if subscription:
        subscription.status = "canceled"
        db.commit()
        logger.info(f"Canceled subscription {subscription_id} for tenant {tenant.id}")
        
        # Suspend all API keys for this tenant
        api_keys = db.query(ApiKey).filter(
            ApiKey.tenant_id == tenant.id,
            ApiKey.status == "active"
        ).all()
        
        for api_key in api_keys:
            api_key.status = "suspended"
        
        db.commit()
        logger.info(f"Suspended {len(api_keys)} API keys for tenant {tenant.id}")
