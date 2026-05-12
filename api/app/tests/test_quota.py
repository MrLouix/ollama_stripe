"""Tests for quota service"""

import pytest
from app.services.quota import (
    check_quota,
    get_quota_status,
    is_quota_warning_threshold
)
from app.services.rate_limit import increment_usage
from app.db.models import Plan


@pytest.fixture
def test_plan_with_limits():
    """Create a test plan with quotas"""
    return Plan(
        name="Test Plan",
        plan_type="fixed",
        price_cents=1000,
        rpm_limit=10,
        daily_token_quota=1000,
        monthly_token_quota=10000
    )


@pytest.fixture
def test_plan_no_daily():
    """Create a test plan without daily quota"""
    return Plan(
        name="Unlimited Daily",
        plan_type="fixed",
        price_cents=2000,
        rpm_limit=20,
        daily_token_quota=None,  # No daily limit
        monthly_token_quota=50000
    )


def test_check_quota_allows_within_limit(redis_client, test_plan_with_limits):
    """Test that requests within quota are allowed"""
    tenant_id = "tenant_quota_1"
    
    allowed, msg = check_quota(redis_client, tenant_id, test_plan_with_limits, 500)
    assert allowed is True
    assert msg == ""


def test_check_quota_blocks_daily_exceeded(redis_client, test_plan_with_limits):
    """Test that daily quota is enforced"""
    tenant_id = "tenant_quota_2"
    
    # Use 900 tokens
    increment_usage(redis_client, tenant_id, 900)
    
    # Try to use 200 more (would exceed 1000 daily limit)
    allowed, msg = check_quota(redis_client, tenant_id, test_plan_with_limits, 200)
    assert allowed is False
    assert "Daily quota exceeded" in msg
    assert "900/1000" in msg


def test_check_quota_blocks_monthly_exceeded(redis_client, test_plan_no_daily):
    """Test that monthly quota is enforced when no daily limit"""
    tenant_id = "tenant_quota_3"
    
    # Use 49500 tokens (no daily limit on this plan)
    increment_usage(redis_client, tenant_id, 49500)
    
    # Try to use 600 more (would exceed 50000 monthly limit)
    allowed, msg = check_quota(redis_client, tenant_id, test_plan_no_daily, 600)
    assert allowed is False
    assert "Monthly quota exceeded" in msg
    assert "49500/50000" in msg


def test_check_quota_no_daily_limit(redis_client, test_plan_no_daily):
    """Test plan without daily quota only checks monthly"""
    tenant_id = "tenant_quota_4"
    
    # Use 40000 tokens (no daily limit)
    increment_usage(redis_client, tenant_id, 40000)
    
    # Should still allow (monthly is 50000)
    allowed, msg = check_quota(redis_client, tenant_id, test_plan_no_daily, 5000)
    assert allowed is True
    
    # But block if exceeding monthly
    allowed, msg = check_quota(redis_client, tenant_id, test_plan_no_daily, 11000)
    assert allowed is False
    assert "Monthly quota exceeded" in msg


def test_get_quota_status(redis_client, test_plan_with_limits):
    """Test quota status reporting"""
    tenant_id = "tenant_status_1"
    
    # Use some tokens
    increment_usage(redis_client, tenant_id, 300)
    
    status = get_quota_status(redis_client, tenant_id, test_plan_with_limits)
    
    assert status["daily_used"] == 300
    assert status["daily_limit"] == 1000
    assert status["daily_remaining"] == 700
    assert status["daily_percentage"] == 30.0
    
    assert status["monthly_used"] == 300
    assert status["monthly_limit"] == 10000
    assert status["monthly_remaining"] == 9700
    assert status["monthly_percentage"] == 3.0
    
    assert status["rpm_limit"] == 10


def test_get_quota_status_no_daily_limit(redis_client, test_plan_no_daily):
    """Test quota status with no daily limit"""
    tenant_id = "tenant_status_2"
    
    increment_usage(redis_client, tenant_id, 1000)
    
    status = get_quota_status(redis_client, tenant_id, test_plan_no_daily)
    
    assert status["daily_used"] == 1000
    assert status["daily_limit"] is None
    assert status["daily_remaining"] is None
    assert status["daily_percentage"] is None


def test_is_quota_warning_threshold_80(redis_client, test_plan_with_limits):
    """Test 80% warning threshold"""
    tenant_id = "tenant_warning_80"
    
    # Use 80% of monthly quota
    increment_usage(redis_client, tenant_id, 8000)
    
    at_threshold, pct = is_quota_warning_threshold(redis_client, tenant_id, test_plan_with_limits)
    assert at_threshold is True
    assert pct == 80


def test_is_quota_warning_threshold_90(redis_client, test_plan_with_limits):
    """Test 90% warning threshold"""
    tenant_id = "tenant_warning_90"
    
    # Use 90% of monthly quota
    increment_usage(redis_client, tenant_id, 9000)
    
    at_threshold, pct = is_quota_warning_threshold(redis_client, tenant_id, test_plan_with_limits)
    assert at_threshold is True
    assert pct == 90


def test_is_quota_warning_threshold_100(redis_client, test_plan_with_limits):
    """Test 100% warning threshold"""
    tenant_id = "tenant_warning_100"
    
    # Use 100% of monthly quota
    increment_usage(redis_client, tenant_id, 10000)
    
    at_threshold, pct = is_quota_warning_threshold(redis_client, tenant_id, test_plan_with_limits)
    assert at_threshold is True
    assert pct == 100


def test_is_quota_warning_threshold_below(redis_client, test_plan_with_limits):
    """Test no warning below 80%"""
    tenant_id = "tenant_warning_below"
    
    # Use 70% of monthly quota (700 tokens = 70% of daily too, so within limits)
    increment_usage(redis_client, tenant_id, 700)
    
    at_threshold, pct = is_quota_warning_threshold(redis_client, tenant_id, test_plan_with_limits)
    assert at_threshold is False
    assert pct == 0
