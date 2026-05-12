"""Tests for rate limiting service"""

import pytest
import time
from app.services.rate_limit import (
    check_rate_limit,
    increment_usage,
    get_usage,
    reset_daily_usage,
    reset_monthly_usage
)


def test_check_rate_limit_allows_within_limit(redis_client):
    """Test that requests within RPM limit are allowed"""
    api_key_id = "test_key_1"
    rpm_limit = 5
    
    # Should allow 5 requests
    for i in range(5):
        allowed, retry_after = check_rate_limit(redis_client, api_key_id, rpm_limit)
        assert allowed is True
        assert retry_after == 0


def test_check_rate_limit_blocks_over_limit(redis_client):
    """Test that requests exceeding RPM limit are blocked"""
    api_key_id = "test_key_2"
    rpm_limit = 3
    
    # Allow 3 requests
    for i in range(3):
        allowed, _ = check_rate_limit(redis_client, api_key_id, rpm_limit)
        assert allowed is True
    
    # 4th request should be blocked
    allowed, retry_after = check_rate_limit(redis_client, api_key_id, rpm_limit)
    assert allowed is False
    assert retry_after > 0
    assert retry_after <= 60


def test_check_rate_limit_sliding_window(redis_client):
    """Test that sliding window works correctly"""
    api_key_id = "test_key_3"
    rpm_limit = 2
    
    # First request
    allowed, _ = check_rate_limit(redis_client, api_key_id, rpm_limit)
    assert allowed is True
    
    # Second request
    allowed, _ = check_rate_limit(redis_client, api_key_id, rpm_limit)
    assert allowed is True
    
    # Third should fail
    allowed, retry_after = check_rate_limit(redis_client, api_key_id, rpm_limit)
    assert allowed is False


def test_increment_usage(redis_client):
    """Test usage increment function"""
    tenant_id = "tenant_123"
    
    # Increment twice
    increment_usage(redis_client, tenant_id, 100)
    increment_usage(redis_client, tenant_id, 50)
    
    # Check totals
    daily, monthly = get_usage(redis_client, tenant_id)
    assert daily == 150
    assert monthly == 150


def test_get_usage_empty(redis_client):
    """Test get_usage returns 0 for new tenant"""
    tenant_id = "tenant_new"
    
    daily, monthly = get_usage(redis_client, tenant_id)
    assert daily == 0
    assert monthly == 0


def test_reset_daily_usage(redis_client):
    """Test daily usage reset"""
    tenant_id = "tenant_reset_daily"
    
    # Add usage
    increment_usage(redis_client, tenant_id, 500)
    
    # Reset daily
    reset_daily_usage(redis_client, tenant_id)
    
    # Daily should be 0, monthly should remain
    daily, monthly = get_usage(redis_client, tenant_id)
    assert daily == 0
    assert monthly == 500


def test_reset_monthly_usage(redis_client):
    """Test monthly usage reset"""
    tenant_id = "tenant_reset_monthly"
    
    # Add usage
    increment_usage(redis_client, tenant_id, 500)
    
    # Reset monthly
    reset_monthly_usage(redis_client, tenant_id)
    
    # Monthly should be 0, daily should remain
    daily, monthly = get_usage(redis_client, tenant_id)
    assert daily == 500
    assert monthly == 0


def test_multiple_tenants_isolated(redis_client):
    """Test that different tenants have isolated counters"""
    tenant1 = "tenant_a"
    tenant2 = "tenant_b"
    
    increment_usage(redis_client, tenant1, 100)
    increment_usage(redis_client, tenant2, 200)
    
    daily1, monthly1 = get_usage(redis_client, tenant1)
    daily2, monthly2 = get_usage(redis_client, tenant2)
    
    assert daily1 == 100
    assert monthly1 == 100
    assert daily2 == 200
    assert monthly2 == 200
