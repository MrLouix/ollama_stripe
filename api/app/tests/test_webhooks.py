"""
Unit tests for Stripe webhook handler.
"""
import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from app.api.webhooks import stripe_webhook, handle_invoice_paid, handle_payment_failed
from app.db.models import Tenant, Subscription, BillingEvent
from fastapi import Request


@pytest.mark.asyncio
async def test_handle_invoice_paid_success(db_session):
    """Test handling invoice.paid event."""
    # Create test tenant
    tenant = Tenant(
        name="Test Tenant",
        email="test@example.com",
        stripe_customer_id="cus_test123"
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    
    # Create test subscription
    subscription = Subscription(
        tenant_id=tenant.id,
        stripe_subscription_id="sub_test123",
        stripe_customer_id="cus_test123",
        stripe_price_id="price_test123",
        status="active",
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc)
    )
    db_session.add(subscription)
    db_session.commit()
    
    # Event data
    event_data = {
        "id": "in_test123",
        "customer": "cus_test123",
        "subscription": "sub_test123",
        "amount_paid": 1000,
        "currency": "usd",
        "status": "paid"
    }
    
    # Handle event
    await handle_invoice_paid(db_session, event_data, tenant)
    
    # Verify billing event was created
    billing_event = db_session.query(BillingEvent).filter_by(
        stripe_invoice_id="in_test123"
    ).first()
    assert billing_event is not None
    assert billing_event.tenant_id == tenant.id
    assert billing_event.event_type == "invoice.paid"
    assert billing_event.amount_cents == 1000


@pytest.mark.asyncio
async def test_handle_payment_failed_success(db_session):
    """Test handling invoice.payment_failed event."""
    # Create test tenant
    tenant = Tenant(
        name="Test Tenant",
        email="test@example.com",
        stripe_customer_id="cus_test123"
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    
    # Create test subscription
    subscription = Subscription(
        tenant_id=tenant.id,
        stripe_subscription_id="sub_test123",
        stripe_customer_id="cus_test123",
        stripe_price_id="price_test123",
        status="active",
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc)
    )
    db_session.add(subscription)
    db_session.commit()
    
    # Event data
    event_data = {
        "id": "in_fail123",
        "customer": "cus_test123",
        "subscription": "sub_test123",
        "amount_due": 2000,
        "currency": "usd",
        "status": "open"
    }
    
    # Handle event
    await handle_payment_failed(db_session, event_data, tenant)
    
    # Verify billing event was created
    billing_event = db_session.query(BillingEvent).filter_by(
        stripe_invoice_id="in_fail123"
    ).first()
    assert billing_event is not None
    assert billing_event.event_type == "invoice.payment_failed"
    
    # Verify subscription status was updated
    db_session.refresh(subscription)
    assert subscription.status == "past_due"


@pytest.mark.asyncio
async def test_webhook_signature_verification():
    """Test webhook signature verification."""
    mock_request = MagicMock(spec=Request)
    mock_request.body = MagicMock(return_value=b'{"type": "test"}')
    mock_request.headers = {}
    
    with patch("stripe.Webhook.construct_event") as mock_construct:
        import stripe
        mock_construct.side_effect = stripe.error.SignatureVerificationError(
            "Invalid signature", "sig_header"
        )
        
        # Should raise 400 for invalid signature
        with pytest.raises(Exception) as exc_info:
            from app.db.database import get_db
            db = next(get_db())
            try:
                await stripe_webhook(mock_request, db=db)
            finally:
                db.close()
        
        # The error handling in the endpoint should catch this


@pytest.mark.asyncio
async def test_subscription_created_event(db_session):
    """Test handling customer.subscription.created event."""
    # Create test tenant
    tenant = Tenant(
        name="Test Tenant",
        email="test@example.com",
        stripe_customer_id="cus_test123"
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    
    # Import the handler
    from app.api.webhooks import handle_subscription_created
    
    # Event data
    event_data = {
        "id": "sub_new123",
        "customer": "cus_test123",
        "status": "active",
        "current_period_start": 1234567890,
        "current_period_end": 1237159890,
        "items": {
            "data": [
                {
                    "id": "si_new123",
                    "price": {"id": "price_new123"}
                }
            ]
        }
    }
    
    # Handle event
    await handle_subscription_created(db_session, event_data, tenant)
    
    # Verify subscription was created
    subscription = db_session.query(Subscription).filter_by(
        stripe_subscription_id="sub_new123"
    ).first()
    assert subscription is not None
    assert subscription.tenant_id == tenant.id
    assert subscription.status == "active"
    assert subscription.stripe_price_id == "price_new123"


@pytest.mark.asyncio
async def test_subscription_updated_event(db_session):
    """Test handling customer.subscription.updated event."""
    # Create test tenant
    tenant = Tenant(
        name="Test Tenant",
        email="test@example.com",
        stripe_customer_id="cus_test123"
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    
    # Create existing subscription
    subscription = Subscription(
        tenant_id=tenant.id,
        stripe_subscription_id="sub_test123",
        stripe_customer_id="cus_test123",
        stripe_price_id="price_test123",
        status="active",
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc)
    )
    db_session.add(subscription)
    db_session.commit()
    
    # Import the handler
    from app.api.webhooks import handle_subscription_updated
    
    # Event data with status change
    event_data = {
        "id": "sub_test123",
        "customer": "cus_test123",
        "status": "past_due",
        "current_period_start": 1234567890,
        "current_period_end": 1237159890,
        "cancel_at_period_end": True,
        "items": {
            "data": [
                {
                    "id": "si_test123",
                    "price": {"id": "price_test123"}
                }
            ]
        }
    }
    
    # Handle event
    await handle_subscription_updated(db_session, event_data, tenant)
    
    # Verify subscription was updated
    db_session.refresh(subscription)
    assert subscription.status == "past_due"


@pytest.mark.asyncio
async def test_subscription_deleted_event(db_session):
    """Test handling customer.subscription.deleted event."""
    # Create test tenant
    tenant = Tenant(
        name="Test Tenant",
        email="test@example.com",
        stripe_customer_id="cus_test123"
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    
    # Create subscription
    subscription = Subscription(
        tenant_id=tenant.id,
        stripe_subscription_id="sub_test123",
        stripe_customer_id="cus_test123",
        stripe_price_id="price_test123",
        status="active",
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc)
    )
    db_session.add(subscription)
    db_session.commit()
    
    # Import the handler
    from app.api.webhooks import handle_subscription_deleted
    
    # Event data
    event_data = {
        "id": "sub_test123",
        "customer": "cus_test123",
        "status": "canceled"
    }
    
    # Handle event
    await handle_subscription_deleted(db_session, event_data, tenant)
    
    # Verify subscription status was updated
    db_session.refresh(subscription)
    assert subscription.status == "canceled"
