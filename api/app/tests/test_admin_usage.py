"""Unit tests for admin usage monitoring endpoints"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.models import User, Tenant, Plan, Subscription, ApiKey, UsageEvent, UsageDaily
from app.services.auth import hash_password, create_access_token, generate_api_key
from app.services.quota import increment_usage
from sqlalchemy.orm import Session
from redis import Redis
from datetime import datetime, date, timedelta
import uuid


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
        daily_token_quota=50000,
        monthly_token_quota=1000000
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan


@pytest.fixture
def test_subscription(db_session: Session, test_tenant: Tenant, test_plan: Plan):
    """Create a test subscription"""
    subscription = Subscription(
        tenant_id=test_tenant.id,
        plan_id=test_plan.id,
        status="active"
    )
    db_session.add(subscription)
    db_session.commit()
    db_session.refresh(subscription)
    return subscription


@pytest.fixture
def test_api_key(db_session: Session, test_tenant: Tenant):
    """Create a test API key"""
    key, key_hash, key_prefix = generate_api_key()
    api_key = ApiKey(
        tenant_id=test_tenant.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name="Test Key"
    )
    db_session.add(api_key)
    db_session.commit()
    db_session.refresh(api_key)
    return api_key


@pytest.fixture
def test_client():
    """Create test client"""
    return TestClient(app)


def test_list_usage_events(
    test_client: TestClient,
    admin_token: str,
    test_tenant: Tenant,
    test_api_key: ApiKey,
    db_session: Session
):
    """Test listing usage events"""
    # Create test usage events
    event1 = UsageEvent(
        tenant_id=test_tenant.id,
        api_key_id=test_api_key.id,
        model="llama3",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        latency_ms=500,
        status_code=200
    )
    event2 = UsageEvent(
        tenant_id=test_tenant.id,
        api_key_id=test_api_key.id,
        model="llama3",
        input_tokens=200,
        output_tokens=100,
        total_tokens=300,
        latency_ms=600,
        status_code=200
    )
    db_session.add_all([event1, event2])
    db_session.commit()
    
    response = test_client.get(
        "/admin/usage/events",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2


def test_list_usage_events_filtered_by_tenant(
    test_client: TestClient,
    admin_token: str,
    test_tenant: Tenant,
    test_api_key: ApiKey,
    db_session: Session
):
    """Test listing usage events filtered by tenant"""
    # Create another tenant and its events
    other_tenant = Tenant(name="Other Tenant", email="other@example.com")
    db_session.add(other_tenant)
    db_session.commit()
    
    key, hash, prefix = generate_api_key()
    other_key = ApiKey(tenant_id=other_tenant.id, key_hash=hash, key_prefix=prefix, name="Other Key")
    db_session.add(other_key)
    db_session.commit()
    
    event1 = UsageEvent(
        tenant_id=test_tenant.id,
        api_key_id=test_api_key.id,
        model="llama3",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        latency_ms=500,
        status_code=200
    )
    event2 = UsageEvent(
        tenant_id=other_tenant.id,
        api_key_id=other_key.id,
        model="llama3",
        input_tokens=200,
        output_tokens=100,
        total_tokens=300,
        latency_ms=600,
        status_code=200
    )
    db_session.add_all([event1, event2])
    db_session.commit()
    
    response = test_client.get(
        f"/admin/usage/events?tenant_id={test_tenant.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert all(event["tenant_id"] == str(test_tenant.id) for event in data)


def test_list_usage_events_filtered_by_date(
    test_client: TestClient,
    admin_token: str,
    test_tenant: Tenant,
    test_api_key: ApiKey,
    db_session: Session
):
    """Test listing usage events filtered by date range"""
    # Create events with different timestamps
    old_event = UsageEvent(
        tenant_id=test_tenant.id,
        api_key_id=test_api_key.id,
        model="llama3",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        latency_ms=500,
        status_code=200,
        created_at=datetime.utcnow() - timedelta(days=5)
    )
    recent_event = UsageEvent(
        tenant_id=test_tenant.id,
        api_key_id=test_api_key.id,
        model="llama3",
        input_tokens=200,
        output_tokens=100,
        total_tokens=300,
        latency_ms=600,
        status_code=200
    )
    db_session.add_all([old_event, recent_event])
    db_session.commit()
    
    # Query for recent events only
    start_date = (datetime.utcnow() - timedelta(days=2)).isoformat()
    response = test_client.get(
        f"/admin/usage/events?start_date={start_date}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    # Should only return recent event
    assert all(
        datetime.fromisoformat(event["created_at"].replace("Z", "+00:00")) >= 
        datetime.fromisoformat(start_date) 
        for event in data
    )


def test_list_daily_usage(
    test_client: TestClient,
    admin_token: str,
    test_tenant: Tenant,
    db_session: Session
):
    """Test listing daily usage aggregations"""
    # Create test daily usage records
    daily1 = UsageDaily(
        tenant_id=test_tenant.id,
        date=date.today(),
        total_requests=100,
        total_tokens=15000,
        total_cost_cents=500
    )
    daily2 = UsageDaily(
        tenant_id=test_tenant.id,
        date=date.today() - timedelta(days=1),
        total_requests=80,
        total_tokens=12000,
        total_cost_cents=400
    )
    db_session.add_all([daily1, daily2])
    db_session.commit()
    
    response = test_client.get(
        "/admin/usage/daily",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2


def test_get_usage_stats(
    test_client: TestClient,
    admin_token: str,
    test_tenant: Tenant,
    test_api_key: ApiKey,
    db_session: Session
):
    """Test getting usage statistics for a tenant"""
    # Create test events
    events = [
        UsageEvent(
            tenant_id=test_tenant.id,
            api_key_id=test_api_key.id,
            model="llama3",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            latency_ms=500,
            status_code=200
        ),
        UsageEvent(
            tenant_id=test_tenant.id,
            api_key_id=test_api_key.id,
            model="llama3",
            input_tokens=200,
            output_tokens=100,
            total_tokens=300,
            latency_ms=600,
            status_code=200
        ),
        UsageEvent(
            tenant_id=test_tenant.id,
            api_key_id=test_api_key.id,
            model="llama3",
            input_tokens=50,
            output_tokens=25,
            total_tokens=75,
            latency_ms=400,
            status_code=500  # Error
        )
    ]
    db_session.add_all(events)
    db_session.commit()
    
    response = test_client.get(
        f"/admin/usage/stats/{test_tenant.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == str(test_tenant.id)
    assert data["total_requests"] == 3
    assert data["total_tokens"] == 525  # 150 + 300 + 75
    assert data["error_rate"] > 0  # 1 error out of 3 requests


def test_get_usage_stats_tenant_not_found(test_client: TestClient, admin_token: str):
    """Test getting usage stats for non-existent tenant"""
    fake_id = uuid.uuid4()
    
    response = test_client.get(
        f"/admin/usage/stats/{fake_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 404


def test_get_quota_status(
    test_client: TestClient,
    admin_token: str,
    test_tenant: Tenant,
    test_plan: Plan,
    test_subscription: Subscription,
    redis_client: Redis
):
    """Test getting quota status for a tenant"""
    # Set some usage in Redis
    increment_usage(redis_client, str(test_tenant.id), 10000)
    
    response = test_client.get(
        f"/admin/quota/{test_tenant.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["tenant_id"] == str(test_tenant.id)
    assert data["tenant_name"] == "Test Tenant"
    assert data["plan_name"] == "Test Plan"
    assert data["rpm_limit"] == 10
    assert "daily_used" in data
    assert "monthly_used" in data
    assert "monthly_percentage" in data


def test_get_quota_status_no_subscription(
    test_client: TestClient,
    admin_token: str,
    db_session: Session
):
    """Test getting quota status for tenant without subscription"""
    # Create tenant without subscription
    tenant = Tenant(name="No Sub Tenant", email="nosub@example.com")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    
    response = test_client.get(
        f"/admin/quota/{tenant.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 404
    assert "subscription" in response.json()["detail"].lower()


def test_get_quota_status_tenant_not_found(test_client: TestClient, admin_token: str):
    """Test getting quota status for non-existent tenant"""
    fake_id = uuid.uuid4()
    
    response = test_client.get(
        f"/admin/quota/{fake_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 404


def test_list_usage_events_pagination(
    test_client: TestClient,
    admin_token: str,
    test_tenant: Tenant,
    test_api_key: ApiKey,
    db_session: Session
):
    """Test pagination of usage events"""
    # Create 10 events
    events = [
        UsageEvent(
            tenant_id=test_tenant.id,
            api_key_id=test_api_key.id,
            model="llama3",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            latency_ms=500,
            status_code=200
        )
        for _ in range(10)
    ]
    db_session.add_all(events)
    db_session.commit()
    
    # Get first page
    response = test_client.get(
        "/admin/usage/events?skip=0&limit=5",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 5
    
    # Get second page
    response = test_client.get(
        "/admin/usage/events?skip=5&limit=5",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 5
