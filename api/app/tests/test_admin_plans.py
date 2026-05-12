"""Unit tests for admin plan and subscription endpoints"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.models import User, Tenant, Plan, Subscription
from app.services.auth import hash_password, create_access_token
from sqlalchemy.orm import Session
from datetime import datetime


@pytest.fixture
def admin_user(db_session: Session):
    """Create an admin user for testing"""
    # Use a pre-hashed password to avoid bcrypt initialization issues in tests
    user = User(
        email="admin@example.com",
        password_hash="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5NU7DeoyW4.eW",  # "testpass"
        role="admin"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_token(admin_user: User):
    """Generate JWT token for admin user"""
    return create_access_token({"sub": str(admin_user.id), "email": admin_user.email})


@pytest.fixture
def test_tenant(db_session: Session):
    """Create a test tenant"""
    tenant = Tenant(name="Test Tenant", email="tenant@example.com")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def test_plan(db_session: Session):
    """Create a test plan"""
    plan = Plan(
        name="Test Plan",
        plan_type="fixed",
        price_cents=1000,
        rpm_limit=10,
        monthly_token_quota=100000
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan


@pytest.fixture
def test_client():
    """Create test client"""
    return TestClient(app)


# Plan Tests
def test_create_plan_success(test_client: TestClient, admin_token: str):
    """Test creating a new plan"""
    response = test_client.post(
        "/admin/plans",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Premium Plan",
            "plan_type": "fixed",
            "price_cents": 2000,
            "rpm_limit": 60,
            "daily_token_quota": 50000,
            "monthly_token_quota": 1000000
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Premium Plan"
    assert data["plan_type"] == "fixed"
    assert data["price_cents"] == 2000
    assert data["rpm_limit"] == 60


def test_create_plan_invalid_type(test_client: TestClient, admin_token: str):
    """Test creating plan with invalid type fails"""
    response = test_client.post(
        "/admin/plans",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Invalid Plan",
            "plan_type": "invalid",
            "price_cents": 1000,
            "rpm_limit": 10,
            "monthly_token_quota": 100000
        }
    )
    
    assert response.status_code == 400
    assert "plan_type" in response.json()["detail"].lower()


def test_create_metered_plan(test_client: TestClient, admin_token: str):
    """Test creating a metered plan"""
    response = test_client.post(
        "/admin/plans",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": "Metered Plan",
            "plan_type": "metered",
            "price_cents": 0,
            "rpm_limit": 100,
            "monthly_token_quota": 500000
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["plan_type"] == "metered"


def test_list_plans(test_client: TestClient, admin_token: str, db_session: Session):
    """Test listing all plans"""
    # Create test plans
    plan1 = Plan(
        name="Plan 1",
        plan_type="fixed",
        price_cents=1000,
        rpm_limit=10,
        monthly_token_quota=100000
    )
    plan2 = Plan(
        name="Plan 2",
        plan_type="metered",
        price_cents=2000,
        rpm_limit=20,
        monthly_token_quota=200000
    )
    db_session.add_all([plan1, plan2])
    db_session.commit()
    
    response = test_client.get(
        "/admin/plans",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2


def test_get_plan(test_client: TestClient, admin_token: str, test_plan: Plan):
    """Test getting a single plan by ID"""
    response = test_client.get(
        f"/admin/plans/{test_plan.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_plan.id)
    assert data["name"] == "Test Plan"


def test_get_plan_not_found(test_client: TestClient, admin_token: str):
    """Test getting non-existent plan returns 404"""
    import uuid
    fake_id = uuid.uuid4()
    
    response = test_client.get(
        f"/admin/plans/{fake_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 404


# Subscription Tests
def test_create_subscription_success(
    test_client: TestClient, 
    admin_token: str, 
    test_tenant: Tenant, 
    test_plan: Plan
):
    """Test creating a new subscription"""
    response = test_client.post(
        "/admin/subscriptions",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "tenant_id": str(test_tenant.id),
            "plan_id": str(test_plan.id)
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["tenant_id"] == str(test_tenant.id)
    assert data["plan_id"] == str(test_plan.id)
    assert data["status"] == "active"


def test_create_subscription_with_stripe_id(
    test_client: TestClient,
    admin_token: str,
    test_tenant: Tenant,
    test_plan: Plan
):
    """Test creating subscription with Stripe subscription ID"""
    response = test_client.post(
        "/admin/subscriptions",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "tenant_id": str(test_tenant.id),
            "plan_id": str(test_plan.id),
            "stripe_subscription_id": "sub_123456"
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["stripe_subscription_id"] == "sub_123456"


def test_create_subscription_tenant_not_found(test_client: TestClient, admin_token: str, test_plan: Plan):
    """Test creating subscription for non-existent tenant fails"""
    import uuid
    fake_tenant_id = uuid.uuid4()
    
    response = test_client.post(
        "/admin/subscriptions",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "tenant_id": str(fake_tenant_id),
            "plan_id": str(test_plan.id)
        }
    )
    
    assert response.status_code == 404
    assert "tenant" in response.json()["detail"].lower()


def test_create_subscription_plan_not_found(test_client: TestClient, admin_token: str, test_tenant: Tenant):
    """Test creating subscription with non-existent plan fails"""
    import uuid
    fake_plan_id = uuid.uuid4()
    
    response = test_client.post(
        "/admin/subscriptions",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "tenant_id": str(test_tenant.id),
            "plan_id": str(fake_plan_id)
        }
    )
    
    assert response.status_code == 404
    assert "plan" in response.json()["detail"].lower()


def test_create_subscription_duplicate_active(
    test_client: TestClient,
    admin_token: str,
    test_tenant: Tenant,
    test_plan: Plan,
    db_session: Session
):
    """Test creating duplicate active subscription fails"""
    # Create first subscription
    subscription = Subscription(
        tenant_id=test_tenant.id,
        plan_id=test_plan.id,
        status="active"
    )
    db_session.add(subscription)
    db_session.commit()
    
    # Try to create second active subscription
    response = test_client.post(
        "/admin/subscriptions",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "tenant_id": str(test_tenant.id),
            "plan_id": str(test_plan.id)
        }
    )
    
    assert response.status_code == 409
    assert "active subscription" in response.json()["detail"].lower()


def test_list_subscriptions(
    test_client: TestClient,
    admin_token: str,
    test_tenant: Tenant,
    test_plan: Plan,
    db_session: Session
):
    """Test listing all subscriptions"""
    # Create test subscriptions
    sub1 = Subscription(tenant_id=test_tenant.id, plan_id=test_plan.id, status="active")
    sub2 = Subscription(tenant_id=test_tenant.id, plan_id=test_plan.id, status="canceled")
    db_session.add_all([sub1, sub2])
    db_session.commit()
    
    response = test_client.get(
        "/admin/subscriptions",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2


def test_list_subscriptions_filtered_by_tenant(
    test_client: TestClient,
    admin_token: str,
    test_tenant: Tenant,
    test_plan: Plan,
    db_session: Session
):
    """Test listing subscriptions filtered by tenant"""
    # Create another tenant
    other_tenant = Tenant(name="Other Tenant", email="other@example.com")
    db_session.add(other_tenant)
    db_session.commit()
    
    # Create subscriptions for both tenants
    sub1 = Subscription(tenant_id=test_tenant.id, plan_id=test_plan.id, status="active")
    sub2 = Subscription(tenant_id=other_tenant.id, plan_id=test_plan.id, status="active")
    db_session.add_all([sub1, sub2])
    db_session.commit()
    
    response = test_client.get(
        f"/admin/subscriptions?tenant_id={test_tenant.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert all(sub["tenant_id"] == str(test_tenant.id) for sub in data)


def test_cancel_subscription(
    test_client: TestClient,
    admin_token: str,
    test_tenant: Tenant,
    test_plan: Plan,
    db_session: Session
):
    """Test canceling a subscription"""
    subscription = Subscription(
        tenant_id=test_tenant.id,
        plan_id=test_plan.id,
        status="active"
    )
    db_session.add(subscription)
    db_session.commit()
    db_session.refresh(subscription)
    
    response = test_client.patch(
        f"/admin/subscriptions/{subscription.id}/cancel",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "canceled"
    
    # Verify in database
    db_session.refresh(subscription)
    assert subscription.status == "canceled"


def test_cancel_already_canceled_subscription(
    test_client: TestClient,
    admin_token: str,
    test_tenant: Tenant,
    test_plan: Plan,
    db_session: Session
):
    """Test canceling an already canceled subscription fails"""
    subscription = Subscription(
        tenant_id=test_tenant.id,
        plan_id=test_plan.id,
        status="canceled"
    )
    db_session.add(subscription)
    db_session.commit()
    db_session.refresh(subscription)
    
    response = test_client.patch(
        f"/admin/subscriptions/{subscription.id}/cancel",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 400
    assert "already canceled" in response.json()["detail"].lower()


def test_cancel_subscription_not_found(test_client: TestClient, admin_token: str):
    """Test canceling non-existent subscription returns 404"""
    import uuid
    fake_id = uuid.uuid4()
    
    response = test_client.patch(
        f"/admin/subscriptions/{fake_id}/cancel",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 404
