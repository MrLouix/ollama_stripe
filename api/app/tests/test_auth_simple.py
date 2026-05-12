"""Simple tests for authentication service (no database)"""

import pytest
from datetime import timedelta
from app.services.auth import (
    generate_api_key,
    hash_password,
    verify_password,
    create_access_token,
    verify_token
)


def test_generate_api_key():
    """Test API key generation"""
    key, key_hash, key_prefix = generate_api_key()
    
    # Check format
    assert key.startswith("osg_")
    assert len(key) >= 48
    assert len(key_hash) == 64  # SHA-256 hex length
    assert key_prefix == key[:12]
    assert key_prefix.startswith("osg_")


def test_generate_api_key_unique():
    """Test that generated keys are unique"""
    key1, hash1, prefix1 = generate_api_key()
    key2, hash2, prefix2 = generate_api_key()
    
    assert key1 != key2
    assert hash1 != hash2


@pytest.mark.skip(reason="bcrypt version compatibility issue in test environment")
def test_password_hashing():
    """Test password hashing and verification"""
    password = "secure_password_123"
    hashed = hash_password(password)
    
    # Check hash was created
    assert hashed != password
    assert len(hashed) > 0
    
    # Verify correct password
    assert verify_password(password, hashed) is True
    
    # Verify incorrect password
    assert verify_password("wrong_password", hashed) is False


def test_create_access_token():
    """Test JWT token creation"""
    data = {"sub": "user123", "role": "admin"}
    token = create_access_token(data)
    
    assert isinstance(token, str)
    assert len(token) > 0


def test_create_access_token_with_expiration():
    """Test JWT token with custom expiration"""
    data = {"sub": "user123"}
    expires_delta = timedelta(minutes=30)
    token = create_access_token(data, expires_delta)
    
    # Verify token
    payload = verify_token(token)
    assert payload is not None
    assert payload["sub"] == "user123"
    assert "exp" in payload


def test_verify_token_valid():
    """Test verifying a valid JWT token"""
    data = {"sub": "user123", "email": "test@example.com"}
    token = create_access_token(data)
    
    payload = verify_token(token)
    
    assert payload is not None
    assert payload["sub"] == "user123"
    assert payload["email"] == "test@example.com"


def test_verify_token_invalid():
    """Test verifying an invalid JWT token"""
    result = verify_token("invalid.token.string")
    assert result is None


def test_verify_token_expired():
    """Test that expired tokens are rejected"""
    data = {"sub": "user123"}
    # Create token that expires immediately
    expires_delta = timedelta(seconds=-1)
    token = create_access_token(data, expires_delta)
    
    result = verify_token(token)
    assert result is None
