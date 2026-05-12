"""Rate limiting and quota management using Redis"""

import time
from redis import Redis
from typing import Tuple
from datetime import datetime


def check_rate_limit(redis: Redis, api_key_id: str, rpm_limit: int) -> Tuple[bool, int]:
    """
    Check RPM (requests per minute) rate limit using sliding window.
    
    Args:
        redis: Redis client
        api_key_id: UUID of the API key
        rpm_limit: Maximum requests per minute allowed
    
    Returns:
        Tuple of (allowed: bool, retry_after_seconds: int)
        - allowed: True if request can proceed, False if rate limited
        - retry_after_seconds: Number of seconds to wait before retry (0 if allowed)
    
    Implementation:
        Uses Redis sorted set with timestamps as scores for sliding window.
        Automatically cleans up old entries outside the window.
    
    Example:
        >>> allowed, retry_after = check_rate_limit(redis, "key-123", 10)
        >>> if not allowed:
        ...     print(f"Rate limited. Retry after {retry_after}s")
    """
    key = f"ratelimit:{api_key_id}:rpm"
    now = time.time()
    window_start = now - 60  # 60 seconds window
    
    # Remove timestamps outside the window (older than 60s)
    redis.zremrangebyscore(key, 0, window_start)
    
    # Count requests in current window
    current_count = redis.zcard(key)
    
    if current_count >= rpm_limit:
        # Rate limit exceeded - calculate retry_after
        # Get the oldest timestamp in the window
        oldest_entries = redis.zrange(key, 0, 0, withscores=True)
        if oldest_entries:
            oldest_timestamp = oldest_entries[0][1]
            retry_after = int(60 - (now - oldest_timestamp)) + 1
        else:
            retry_after = 60
        
        return False, retry_after
    
    # Add current request timestamp
    redis.zadd(key, {str(now): now})
    
    # Set expiration to clean up automatically (61s to be safe)
    redis.expire(key, 61)
    
    return True, 0


def increment_usage(redis: Redis, tenant_id: str, tokens: int) -> None:
    """
    Increment daily and monthly token usage counters.
    
    Args:
        redis: Redis client
        tenant_id: UUID of the tenant
        tokens: Number of tokens to add to counters
    
    Side effects:
        Increments two Redis keys:
        - usage:{tenant_id}:daily:{YYYY-MM-DD}
        - usage:{tenant_id}:monthly:{YYYY-MM}
    
    Example:
        >>> increment_usage(redis, "tenant-123", 500)
        # Adds 500 to today's and this month's counters
    """
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")
    month_str = now.strftime("%Y-%m")
    
    # Daily counter
    daily_key = f"usage:{tenant_id}:daily:{date_str}"
    redis.incrby(daily_key, tokens)
    redis.expire(daily_key, 48 * 3600)  # 48h TTL (keep yesterday's data)
    
    # Monthly counter
    monthly_key = f"usage:{tenant_id}:monthly:{month_str}"
    redis.incrby(monthly_key, tokens)
    redis.expire(monthly_key, 35 * 24 * 3600)  # 35 days TTL


def get_usage(redis: Redis, tenant_id: str) -> Tuple[int, int]:
    """
    Get current daily and monthly token usage.
    
    Args:
        redis: Redis client
        tenant_id: UUID of the tenant
    
    Returns:
        Tuple of (daily_usage: int, monthly_usage: int)
        Returns 0 if no usage recorded yet.
    
    Example:
        >>> daily, monthly = get_usage(redis, "tenant-123")
        >>> print(f"Used {daily} tokens today, {monthly} this month")
    """
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")
    month_str = now.strftime("%Y-%m")
    
    daily_key = f"usage:{tenant_id}:daily:{date_str}"
    monthly_key = f"usage:{tenant_id}:monthly:{month_str}"
    
    daily = int(redis.get(daily_key) or 0)
    monthly = int(redis.get(monthly_key) or 0)
    
    return daily, monthly


def reset_daily_usage(redis: Redis, tenant_id: str) -> None:
    """
    Manually reset daily usage counter (for testing or admin purposes).
    
    Args:
        redis: Redis client
        tenant_id: UUID of the tenant
    
    Warning:
        This is a destructive operation. Use with caution.
    """
    now = datetime.utcnow()
    date_str = now.strftime("%Y-%m-%d")
    daily_key = f"usage:{tenant_id}:daily:{date_str}"
    redis.delete(daily_key)


def reset_monthly_usage(redis: Redis, tenant_id: str) -> None:
    """
    Manually reset monthly usage counter (for testing or admin purposes).
    
    Args:
        redis: Redis client
        tenant_id: UUID of the tenant
    
    Warning:
        This is a destructive operation. Use with caution.
    """
    now = datetime.utcnow()
    month_str = now.strftime("%Y-%m")
    monthly_key = f"usage:{tenant_id}:monthly:{month_str}"
    redis.delete(monthly_key)
