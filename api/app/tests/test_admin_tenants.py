"""Unit tests for admin tenant endpoints"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.models import User, Tenant
from app.services.auth import hash_password, create_access_token
from sqlalchemy.orm import Session


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
def test_client():
    """Create test client"""
    return TestClient(app)


def test_create_tenant_success(test_client: TestClient, admin_token: str):
    """Test creating a new tenant"""
    response = test_client.post(
        "/admin/tenants",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "Test Tenant", "email": "tenant@example.com"}
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Tenant"
    assert data["email"] == "tenant@example.com"
    assert data["status"] == "active"
    assert "id" in data


def test_create_tenant_duplicate_email(test_client: TestClient, admin_token: str, db_session: Session):
    """Test creating tenant with duplicate email fails"""
    # Create first tenant
    tenant = Tenant(name="Existing", email="duplicate@example.com")
    db_session.add(tenant)
    db_session.commit()
    
    # Try to create second tenant with same email
    response = test_client.post(
        "/admin/tenants",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "New Tenant", "email": "duplicate@example.com"}
    )
    
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_create_tenant_no_auth(test_client: TestClient):
    """Test creating tenant without authentication fails"""
    response = test_client.post(
        "/admin/tenants",
        json={"name": "Test", "email": "test@example.com"}
    )
    
    assert response.status_code == 422  # Missing header


def test_create_tenant_invalid_token(test_client: TestClient):
    """Test creating tenant with invalid token fails"""
    response = test_client.post(
        "/admin/tenants",
        headers={"Authorization": "Bearer invalid_token"},
        json={"name": "Test", "email": "test@example.com"}
    )
    
    assert response.status_code == 401


def test_list_tenants(test_client: TestClient, admin_token: str, db_session: Session):
    """Test listing all tenants"""
    # Create test tenants
    tenant1 = Tenant(name="Tenant 1", email="tenant1@example.com")
    tenant2 = Tenant(name="Tenant 2", email="tenant2@example.com")
    db_session.add_all([tenant1, tenant2])
    db_session.commit()
    
    response = test_client.get(
        "/admin/tenants",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    assert any(t["name"] == "Tenant 1" for t in data)


def test_list_tenants_pagination(test_client: TestClient, admin_token: str, db_session: Session):
    """Test tenant list pagination"""
    # Create 5 tenants
    for i in range(5):
        tenant = Tenant(name=f"Tenant {i}", email=f"tenant{i}@example.com")
        db_session.add(tenant)
    db_session.commit()
    
    response = test_client.get(
        "/admin/tenants?skip=2&limit=2",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 2


def test_get_tenant(test_client: TestClient, admin_token: str, db_session: Session):
    """Test getting a single tenant by ID"""
    tenant = Tenant(name="Get Test", email="get@example.com")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    
    response = test_client.get(
        f"/admin/tenants/{tenant.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(tenant.id)
    assert data["name"] == "Get Test"


def test_get_tenant_not_found(test_client: TestClient, admin_token: str):
    """Test getting non-existent tenant returns 404"""
    import uuid
    fake_id = uuid.uuid4()
    
    response = test_client.get(
        f"/admin/tenants/{fake_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 404


def test_update_tenant(test_client: TestClient, admin_token: str, db_session: Session):
    """Test updating tenant information"""
    tenant = Tenant(name="Old Name", email="old@example.com")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    
    response = test_client.patch(
        f"/admin/tenants/{tenant.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"name": "New Name", "email": "new@example.com"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["email"] == "new@example.com"


def test_update_tenant_status(test_client: TestClient, admin_token: str, db_session: Session):
    """Test updating tenant status"""
    tenant = Tenant(name="Status Test", email="status@example.com")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    
    response = test_client.patch(
        f"/admin/tenants/{tenant.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "suspended"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "suspended"


def test_update_tenant_invalid_status(test_client: TestClient, admin_token: str, db_session: Session):
    """Test updating tenant with invalid status fails"""
    tenant = Tenant(name="Status Test", email="status@example.com")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    
    response = test_client.patch(
        f"/admin/tenants/{tenant.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "invalid_status"}
    )
    
    assert response.status_code == 400


def test_delete_tenant(test_client: TestClient, admin_token: str, db_session: Session):
    """Test soft deleting a tenant"""
    tenant = Tenant(name="Delete Test", email="delete@example.com")
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    
    response = test_client.delete(
        f"/admin/tenants/{tenant.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 204
    
    # Verify tenant status is 'deleted'
    db_session.refresh(tenant)
    assert tenant.status == "deleted"


def test_delete_tenant_not_found(test_client: TestClient, admin_token: str):
    """Test deleting non-existent tenant returns 404"""
    import uuid
    fake_id = uuid.uuid4()
    
    response = test_client.delete(
        f"/admin/tenants/{fake_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 404
