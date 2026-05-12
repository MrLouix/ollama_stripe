"""Pytest configuration and fixtures"""

import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from redis import Redis
import fakeredis

# Set test environment variables before importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_test_fake")
os.environ.setdefault("ADMIN_SECRET", "test_admin_secret_key_12345")
os.environ.setdefault("DOMAIN", "test.example.com")
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")

# Patch UUID type before importing models
from sqlalchemy import TypeDecorator, CHAR
import uuid as uuid_module
import sqlalchemy.dialects.postgresql as pg_dialects

class SQLiteUUID(TypeDecorator):
    """Platform-independent UUID type.
    Uses PostgreSQL's UUID type, otherwise uses CHAR(36), storing as stringified hex values.
    """
    impl = CHAR
    cache_ok = True

    def __init__(self, as_uuid=True):
        self.as_uuid = as_uuid
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(CHAR(36))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        else:
            if isinstance(value, uuid_module.UUID):
                return str(value)
            else:
                return str(uuid_module.UUID(value))

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        else:
            if not self.as_uuid:
                return value
            if isinstance(value, uuid_module.UUID):
                return value
            else:
                return uuid_module.UUID(value)

# Replace PostgreSQL UUID with our SQLite-compatible version
_original_UUID = pg_dialects.UUID
pg_dialects.UUID = SQLiteUUID

# Also patch JSONB and INET for SQLite compatibility
from sqlalchemy import JSON, String

class SQLiteJSONB(TypeDecorator):
    """SQLite-compatible JSONB type (uses JSON)"""
    impl = JSON
    cache_ok = True

class SQLiteINET(TypeDecorator):
    """SQLite-compatible INET type (uses String)"""
    impl = String
    cache_ok = True
    
    def __init__(self):
        super().__init__(length=45)  # Max length for IPv6

pg_dialects.JSONB = SQLiteJSONB
pg_dialects.INET = SQLiteINET

from app.db.database import Base, get_db
from app.dependencies import get_redis
from app.main import app
from app.db.models import Tenant, ApiKey, Plan, User
from app.services.auth import generate_api_key, hash_password


# Test database URL (in-memory SQLite)
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"

# Create test engine with StaticPool to share the same connection across threads
from sqlalchemy.pool import StaticPool

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)

# Create test session factory
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="function")
def db_session():
    """
    Create a fresh database session for each test.
    Creates all tables before test and drops them after.
    """
    # Create all tables
    Base.metadata.create_all(bind=test_engine)
    
    # Create session
    session = TestingSessionLocal()
    
    try:
        yield session
    finally:
        session.close()
        # Drop all tables
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def redis_client():
    """
    Create a fake Redis client for testing.
    """
    fake_redis = fakeredis.FakeStrictRedis(decode_responses=True)
    return fake_redis


@pytest.fixture(scope="function")
def client(db_session, redis_client):
    """
    Create a test client with database and Redis overrides.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    def override_get_redis():
        return redis_client
    
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    
    with TestClient(app) as test_client:
        yield test_client
    
    app.dependency_overrides.clear()


@pytest.fixture
def test_tenant(db_session):
    """Create a test tenant."""
    tenant = Tenant(
        name="Test Tenant",
        email="test@example.com",
        status="active"
    )
    db_session.add(tenant)
    db_session.commit()
    db_session.refresh(tenant)
    return tenant


@pytest.fixture
def test_plan(db_session):
    """Create a test plan."""
    plan = Plan(
        name="Test Plan",
        plan_type="fixed",
        price_cents=2900,
        rpm_limit=10,
        monthly_token_quota=100000,
        daily_token_quota=10000
    )
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    return plan


@pytest.fixture
def test_api_key(db_session, test_tenant):
    """Create a test API key."""
    key, key_hash, key_prefix = generate_api_key()
    
    api_key = ApiKey(
        tenant_id=test_tenant.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name="Test Key",
        status="active"
    )
    db_session.add(api_key)
    db_session.commit()
    db_session.refresh(api_key)
    
    # Return both the key object and the actual key string
    api_key.plain_key = key
    return api_key


@pytest.fixture
def test_admin(db_session):
    """Create a test admin user."""
    user = User(
        email="admin@test.com",
        password_hash=hash_password("testpassword"),
        role="super_admin"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
