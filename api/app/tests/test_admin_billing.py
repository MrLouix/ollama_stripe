"""
Unit tests for admin billing endpoints.
"""
import pytest
import uuid
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.db.models import Tenant, User, Subscription


@pytest.fixture
def admin_user_for_billing(db_session):
    """Create an admin user for billing tests."""
    user = User(
        email="billingadmin@example.com",
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7DeoyW4.eW",
        role="admin"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_token_for_billing(admin_user_for_billing):
    """Create a JWT token for admin authentication."""
    from app.services.auth import create_access_token
    return create_access_token(data={"sub": admin_user_for_billing.email})


@pytest.fixture
def test_tenant_for_billing(db_session):
    """Create a test tenant for billing tests."""
    tenant = Tenant(
        name="Billing Test Tenant",
        email="billing@example.com"
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def test_tenant_with_stripe(db_session):
    """Create a test tenant with Stripe customer ID."""
    tenant = Tenant(
        name="Stripe Tenant",
        email="stripe@example.com",
        stripe_customer_id="cus_test123"
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


def test_create_stripe_customer_success(db_session, admin_token_for_billing, test_tenant_for_billing):
    """Test creating a Stripe customer for a tenant."""
    client = TestClient(app)
    
    with patch("app.services.stripe_client.create_customer") as mock_create:
        mock_create.return_value = "cus_new123"
        
        response = client.post(
            "/admin/billing/customers",
            json={"tenant_id": str(test_tenant_for_billing.id)},
            headers={"Authorization": f"Bearer {admin_token_for_billing}"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["customer_id"] == "cus_new123"
        
        # Verify tenant was updated
        db_session.refresh(test_tenant_for_billing)
        assert test_tenant_for_billing.stripe_customer_id == "cus_new123"


def test_create_stripe_customer_already_exists(db_session, admin_token_for_billing, test_tenant_with_stripe):
    """Test creating a Stripe customer when one already exists."""
    client = TestClient(app)
    
    response = client.post(
        "/admin/billing/customers",
        json={"tenant_id": str(test_tenant_with_stripe.id)},
        headers={"Authorization": f"Bearer {admin_token_for_billing}"}
    )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "already has a Stripe customer" in response.json()["detail"]


def test_create_stripe_customer_tenant_not_found(db_session, admin_token_for_billing):
    """Test creating a Stripe customer for non-existent tenant."""
    client = TestClient(app)
    
    fake_tenant_id = str(uuid.uuid4())
    response = client.post(
        "/admin/billing/customers",
        json={"tenant_id": fake_tenant_id},
        headers={"Authorization": f"Bearer {admin_token_for_billing}"}
    )
    
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_create_stripe_customer_unauthorized(db_session, test_tenant_for_billing):
    """Test creating a Stripe customer without authentication."""
    client = TestClient(app)
    
    response = client.post(
        "/admin/billing/customers",
        json={"tenant_id": str(test_tenant_for_billing.id)}
    )
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_create_subscription_success(db_session, admin_token_for_billing, test_tenant_with_stripe):
    """Test creating a Stripe subscription."""
    client = TestClient(app)
    
    with patch("app.services.stripe_client.create_subscription") as mock_create:
        mock_create.return_value = {
            "subscription_id": "sub_new123",
            "item_id": "si_new123",
            "status": "active"
        }
        
        response = client.post(
            "/admin/billing/subscriptions",
            json={
                "tenant_id": str(test_tenant_with_stripe.id),
                "price_id": "price_test123"
            },
            headers={"Authorization": f"Bearer {admin_token_for_billing}"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["subscription_id"] == "sub_new123"
        assert data["status"] == "active"
        
        # Verify subscription was created in DB
        subscription = db_session.query(Subscription).filter_by(
            stripe_subscription_id="sub_new123"
        ).first()
        assert subscription is not None
        assert subscription.tenant_id == test_tenant_with_stripe.id


def test_create_subscription_no_stripe_customer(db_session, admin_token_for_billing, test_tenant_for_billing):
    """Test creating a subscription for tenant without Stripe customer."""
    client = TestClient(app)
    
    response = client.post(
        "/admin/billing/subscriptions",
        json={
            "tenant_id": str(test_tenant_for_billing.id),
            "price_id": "price_test123"
        },
        headers={"Authorization": f"Bearer {admin_token_for_billing}"}
    )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "does not have a Stripe customer" in response.json()["detail"]


def test_create_subscription_tenant_not_found(db_session, admin_token_for_billing):
    """Test creating a subscription for non-existent tenant."""
    client = TestClient(app)
    
    fake_tenant_id = str(uuid.uuid4())
    response = client.post(
        "/admin/billing/subscriptions",
        json={
            "tenant_id": fake_tenant_id,
            "price_id": "price_test123"
        },
        headers={"Authorization": f"Bearer {admin_token_for_billing}"}
    )
    
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_cancel_subscription_immediate(db_session, admin_token_for_billing, test_tenant_with_stripe):
    """Test canceling a subscription immediately."""
    # Create a subscription first
    subscription = Subscription(
        tenant_id=test_tenant_with_stripe.id,
        stripe_subscription_id="sub_cancel123",
        stripe_customer_id="cus_test123",
        stripe_price_id="price_test123",
        status="active",
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc)
    )
    db_session.add(subscription)
    db_session.commit()
    
    client = TestClient(app)
    
    with patch("app.services.stripe_client.cancel_subscription") as mock_cancel:
        mock_cancel.return_value = "canceled"
        
        response = client.delete(
            f"/admin/billing/subscriptions/{subscription.stripe_subscription_id}",
            params={"at_period_end": False},
            headers={"Authorization": f"Bearer {admin_token_for_billing}"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "canceled"
        
        # Verify subscription status was updated
        db_session.refresh(subscription)
        assert subscription.status == "canceled"


def test_cancel_subscription_at_period_end(db_session, admin_token_for_billing, test_tenant_with_stripe):
    """Test canceling a subscription at period end."""
    # Create a subscription first
    subscription = Subscription(
        tenant_id=test_tenant_with_stripe.id,
        stripe_subscription_id="sub_cancel456",
        stripe_customer_id="cus_test123",
        stripe_price_id="price_test123",
        status="active",
        current_period_start=datetime.now(timezone.utc),
        current_period_end=datetime.now(timezone.utc)
    )
    db_session.add(subscription)
    db_session.commit()
    
    client = TestClient(app)
    
    with patch("app.services.stripe_client.cancel_subscription") as mock_cancel:
        mock_cancel.return_value = "active"
        
        response = client.delete(
            f"/admin/billing/subscriptions/{subscription.stripe_subscription_id}",
            params={"at_period_end": True},
            headers={"Authorization": f"Bearer {admin_token_for_billing}"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "active"


def test_cancel_subscription_not_found(db_session, admin_token_for_billing):
    """Test canceling a non-existent subscription."""
    client = TestClient(app)
    
    response = client.delete(
        "/admin/billing/subscriptions/sub_notfound",
        headers={"Authorization": f"Bearer {admin_token_for_billing}"}
    )
    
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_create_billing_portal_session_success(db_session, admin_token_for_billing, test_tenant_with_stripe):
    """Test creating a billing portal session."""
    client = TestClient(app)
    
    with patch("app.services.stripe_client.create_billing_portal_session") as mock_create:
        mock_create.return_value = "https://billing.stripe.com/session/test123"
        
        response = client.post(
            "/admin/billing/portal",
            json={
                "tenant_id": str(test_tenant_with_stripe.id),
                "return_url": "https://example.com/billing"
            },
            headers={"Authorization": f"Bearer {admin_token_for_billing}"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["url"] == "https://billing.stripe.com/session/test123"


def test_create_billing_portal_no_stripe_customer(db_session, admin_token_for_billing, test_tenant_for_billing):
    """Test creating portal session for tenant without Stripe customer."""
    client = TestClient(app)
    
    response = client.post(
        "/admin/billing/portal",
        json={
            "tenant_id": str(test_tenant_for_billing.id),
            "return_url": "https://example.com/billing"
        },
        headers={"Authorization": f"Bearer {admin_token_for_billing}"}
    )
    
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "does not have a Stripe customer" in response.json()["detail"]


def test_list_prices_success(db_session, admin_token_for_billing):
    """Test listing Stripe prices."""
    client = TestClient(app)
    
    with patch("app.services.stripe_client.list_prices") as mock_list:
        mock_list.return_value = [
            {
                "id": "price_1",
                "active": True,
                "unit_amount": 1000,
                "currency": "usd",
                "interval": "month",
                "product": "prod_1"
            },
            {
                "id": "price_2",
                "active": True,
                "unit_amount": 5000,
                "currency": "usd",
                "interval": "year",
                "product": "prod_2"
            }
        ]
        
        response = client.get(
            "/admin/billing/prices",
            headers={"Authorization": f"Bearer {admin_token_for_billing}"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2
        assert data[0]["id"] == "price_1"
        assert data[0]["unit_amount"] == 1000
        assert data[1]["id"] == "price_2"
        assert data[1]["unit_amount"] == 5000


def test_list_prices_active_only(db_session, admin_token_for_billing):
    """Test listing only active Stripe prices."""
    client = TestClient(app)
    
    with patch("app.services.stripe_client.list_prices") as mock_list:
        mock_list.return_value = [
            {
                "id": "price_active",
                "active": True,
                "unit_amount": 2000,
                "currency": "usd",
                "interval": "month",
                "product": "prod_active"
            }
        ]
        
        response = client.get(
            "/admin/billing/prices?active=true",
            headers={"Authorization": f"Bearer {admin_token_for_billing}"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "price_active"


def test_list_prices_unauthorized(db_session):
    """Test listing prices without authentication."""
    client = TestClient(app)
    
    response = client.get("/admin/billing/prices")
    
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
