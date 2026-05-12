"""Quota verification service"""

from redis import Redis
from typing import Tuple
from app.services.rate_limit import get_usage
from app.db.models import Plan


def check_quota(redis: Redis, tenant_id: str, plan: Plan, tokens: int) -> Tuple[bool, str]:
    """
    Check if tenant can consume additional tokens without exceeding quotas.
    
    Args:
        redis: Redis client
        tenant_id: UUID of the tenant
        plan: Plan object with quota limits
        tokens: Number of tokens about to be consumed
    
    Returns:
        Tuple of (allowed: bool, error_message: str)
        - allowed: True if within quota, False if would exceed
        - error_message: Description of quota exceeded (empty string if allowed)
    
    Checks:
        1. Daily quota (if plan.daily_token_quota is set)
        2. Monthly quota (always checked)
    
    Example:
        >>> allowed, msg = check_quota(redis, "tenant-123", plan, 1000)
        >>> if not allowed:
        ...     return {"error": msg}, 429
    """
    # Get current usage
    daily_usage, monthly_usage = get_usage(redis, tenant_id)
    
    # Check daily quota (if set)
    if plan.daily_token_quota is not None:
        if daily_usage + tokens > plan.daily_token_quota:
            return False, (
                f"Daily quota exceeded. "
                f"Used {daily_usage}/{plan.daily_token_quota} tokens today. "
                f"Request needs {tokens} more tokens."
            )
    
    # Check monthly quota (always enforced)
    if monthly_usage + tokens > plan.monthly_token_quota:
        return False, (
            f"Monthly quota exceeded. "
            f"Used {monthly_usage}/{plan.monthly_token_quota} tokens this month. "
            f"Request needs {tokens} more tokens."
        )
    
    return True, ""


def get_quota_status(redis: Redis, tenant_id: str, plan: Plan) -> dict:
    """
    Get detailed quota status for a tenant.
    
    Args:
        redis: Redis client
        tenant_id: UUID of the tenant
        plan: Plan object with quota limits
    
    Returns:
        Dictionary with quota usage details
    
    Example:
        >>> status = get_quota_status(redis, "tenant-123", plan)
        >>> print(f"Daily: {status['daily_used']}/{status['daily_limit']}")
    """
    daily_usage, monthly_usage = get_usage(redis, tenant_id)
    
    daily_limit = plan.daily_token_quota if plan.daily_token_quota is not None else None
    monthly_limit = plan.monthly_token_quota
    
    # Calculate percentages
    daily_percentage = None
    if daily_limit is not None and daily_limit > 0:
        daily_percentage = round((daily_usage / daily_limit) * 100, 2)
    
    monthly_percentage = None
    if monthly_limit > 0:
        monthly_percentage = round((monthly_usage / monthly_limit) * 100, 2)
    
    return {
        "daily_used": daily_usage,
        "daily_limit": daily_limit,
        "daily_remaining": (daily_limit - daily_usage) if daily_limit is not None else None,
        "daily_percentage": daily_percentage,
        "monthly_used": monthly_usage,
        "monthly_limit": monthly_limit,
        "monthly_remaining": monthly_limit - monthly_usage,
        "monthly_percentage": monthly_percentage,
        "rpm_limit": plan.rpm_limit
    }


def is_quota_warning_threshold(redis: Redis, tenant_id: str, plan: Plan) -> Tuple[bool, int]:
    """
    Check if tenant is approaching quota limits (80%, 90%, 100%).
    
    Args:
        redis: Redis client
        tenant_id: UUID of the tenant
        plan: Plan object with quota limits
    
    Returns:
        Tuple of (at_threshold: bool, threshold_percentage: int)
        - at_threshold: True if at or above 80% usage
        - threshold_percentage: 80, 90, or 100 if at threshold, 0 otherwise
    
    Use case:
        Send alerts when tenants approach their limits.
    
    Example:
        >>> at_threshold, pct = is_quota_warning_threshold(redis, "tenant-123", plan)
        >>> if at_threshold:
        ...     send_alert(f"You've used {pct}% of your monthly quota")
    """
    daily_usage, monthly_usage = get_usage(redis, tenant_id)
    
    # Check monthly quota (primary metric)
    if plan.monthly_token_quota > 0:
        monthly_pct = (monthly_usage / plan.monthly_token_quota) * 100
        
        if monthly_pct >= 100:
            return True, 100
        elif monthly_pct >= 90:
            return True, 90
        elif monthly_pct >= 80:
            return True, 80
    
    # Check daily quota if set
    if plan.daily_token_quota is not None and plan.daily_token_quota > 0:
        daily_pct = (daily_usage / plan.daily_token_quota) * 100
        
        if daily_pct >= 100:
            return True, 100
        elif daily_pct >= 90:
            return True, 90
        elif daily_pct >= 80:
            return True, 80
    
    return False, 0
