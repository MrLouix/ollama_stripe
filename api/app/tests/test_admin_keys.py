"""Unit tests for admin API key endpoints"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.models import User, Tenant, ApiKey
from app.services.auth import hash_password, create_access_token, generate_api_key
from sqlalchemy.orm import Session
from datetime import datetime, timedelta


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
def test_client():
    """Create test client"""
    return TestClient(app)


def test_create_api_key_success(test_client: TestClient, admin_token: str, test_tenant: Tenant):
    """Test creating a new API key"""
    response = test_client.post(
        "/admin/keys",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "tenant_id": str(test_tenant.id),
            "name": "Test Key"
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    assert "key" in data
    assert data["key"].startswith("osg_")
    assert data["name"] == "Test Key"
    assert data["tenant_id"] == str(test_tenant.id)
    assert data["status"] == "active"


def test_create_api_key_with_expiration(test_client: TestClient, admin_token: str, test_tenant: Tenant):
    """Test creating an API key with expiration date"""
    expires_at = (datetime.utcnow() + timedelta(days=30)).isoformat()
    
    response = test_client.post(
        "/admin/keys",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "tenant_id": str(test_tenant.id),
            "name": "Expiring Key",
            "expires_at": expires_at
        }
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["expires_at"] is not None


def test_create_api_key_tenant_not_found(test_client: TestClient, admin_token: str):
    """Test creating API key for non-existent tenant fails"""
    import uuid
    fake_tenant_id = uuid.uuid4()
    
    response = test_client.post(
        "/admin/keys",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "tenant_id": str(fake_tenant_id),
            "name": "Test Key"
        }
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_create_api_key_no_auth(test_client: TestClient, test_tenant: Tenant):
    """Test creating API key without authentication fails"""
    response = test_client.post(
        "/admin/keys",
        json={
            "tenant_id": str(test_tenant.id),
            "name": "Test Key"
        }
    )
    
    assert response.status_code == 422  # Missing header


def test_list_api_keys(test_client: TestClient, admin_token: str, test_tenant: Tenant, db_session: Session):
    """Test listing all API keys"""
    # Create test keys
    key1, hash1, prefix1 = generate_api_key()
    key2, hash2, prefix2 = generate_api_key()
    
    api_key1 = ApiKey(tenant_id=test_tenant.id, key_hash=hash1, key_prefix=prefix1, name="Key 1")
    api_key2 = ApiKey(tenant_id=test_tenant.id, key_hash=hash2, key_prefix=prefix2, name="Key 2")
    db_session.add_all([api_key1, api_key2])
    db_session.commit()
    
    response = test_client.get(
        "/admin/keys",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2


def test_list_api_keys_filtered_by_tenant(
    test_client: TestClient, 
    admin_token: str, 
    test_tenant: Tenant, 
    db_session: Session
):
    """Test listing API keys filtered by tenant"""
    # Create another tenant
    other_tenant = Tenant(name="Other Tenant", email="other@example.com")
    db_session.add(other_tenant)
    db_session.commit()
    
    # Create keys for both tenants
    key1, hash1, prefix1 = generate_api_key()
    key2, hash2, prefix2 = generate_api_key()
    
    api_key1 = ApiKey(tenant_id=test_tenant.id, key_hash=hash1, key_prefix=prefix1, name="Key 1")
    api_key2 = ApiKey(tenant_id=other_tenant.id, key_hash=hash2, key_prefix=prefix2, name="Key 2")
    db_session.add_all([api_key1, api_key2])
    db_session.commit()
    
    response = test_client.get(
        f"/admin/keys?tenant_id={test_tenant.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    # All returned keys should belong to test_tenant
    assert all(key["tenant_id"] == str(test_tenant.id) for key in data)


def test_get_api_key(test_client: TestClient, admin_token: str, test_tenant: Tenant, db_session: Session):
    """Test getting a single API key by ID"""
    key, key_hash, key_prefix = generate_api_key()
    api_key = ApiKey(tenant_id=test_tenant.id, key_hash=key_hash, key_prefix=key_prefix, name="Get Test")
    db_session.add(api_key)
    db_session.commit()
    db_session.refresh(api_key)
    
    response = test_client.get(
        f"/admin/keys/{api_key.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(api_key.id)
    assert data["name"] == "Get Test"
    assert "key" not in data or data["key"] is None  # Key should not be returned


def test_get_api_key_not_found(test_client: TestClient, admin_token: str):
    """Test getting non-existent API key returns 404"""
    import uuid
    fake_id = uuid.uuid4()
    
    response = test_client.get(
        f"/admin/keys/{fake_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 404


def test_revoke_api_key(test_client: TestClient, admin_token: str, test_tenant: Tenant, db_session: Session):
    """Test revoking an API key"""
    key, key_hash, key_prefix = generate_api_key()
    api_key = ApiKey(
        tenant_id=test_tenant.id, 
        key_hash=key_hash, 
        key_prefix=key_prefix, 
        name="Revoke Test",
        status="active"
    )
    db_session.add(api_key)
    db_session.commit()
    db_session.refresh(api_key)
    
    response = test_client.delete(
        f"/admin/keys/{api_key.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 200
    assert "revoked" in response.json()["message"].lower()
    
    # Verify status is 'revoked'
    db_session.refresh(api_key)
    assert api_key.status == "revoked"


def test_revoke_already_revoked_key(
    test_client: TestClient, 
    admin_token: str, 
    test_tenant: Tenant, 
    db_session: Session
):
    """Test revoking an already revoked key fails"""
    key, key_hash, key_prefix = generate_api_key()
    api_key = ApiKey(
        tenant_id=test_tenant.id, 
        key_hash=key_hash, 
        key_prefix=key_prefix, 
        name="Already Revoked",
        status="revoked"
    )
    db_session.add(api_key)
    db_session.commit()
    db_session.refresh(api_key)
    
    response = test_client.delete(
        f"/admin/keys/{api_key.id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 400
    assert "already revoked" in response.json()["detail"].lower()


def test_revoke_api_key_not_found(test_client: TestClient, admin_token: str):
    """Test revoking non-existent API key returns 404"""
    import uuid
    fake_id = uuid.uuid4()
    
    response = test_client.delete(
        f"/admin/keys/{fake_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    assert response.status_code == 404
