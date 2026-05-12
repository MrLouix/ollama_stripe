"""FastAPI dependencies for database, Redis, and authentication"""

from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from redis import Redis
from typing import Optional
from app.db.database import get_db
from app.services.auth import verify_api_key, verify_token
from app.db.models import ApiKey, User
from app.config import settings
import redis as redis_lib


def get_redis() -> Redis:
    """
    Get Redis client connection.
    
    Returns:
        Redis client instance
    """
    return redis_lib.from_url(settings.redis_url, decode_responses=True)


async def get_current_api_key(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
) -> ApiKey:
    """
    Dependency to verify Bearer token (API key) and return ApiKey object.
    
    Args:
        authorization: Authorization header (format: "Bearer <key>")
        db: Database session
    
    Returns:
        ApiKey object if valid
    
    Raises:
        HTTPException: 401 if authorization header invalid or key not found/inactive
    
    Example:
        @app.get("/protected")
        async def protected_route(api_key: ApiKey = Depends(get_current_api_key)):
            return {"tenant_id": str(api_key.tenant_id)}
    """
    # Check header format
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected: Bearer <key>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract token
    token = authorization.replace("Bearer ", "").strip()
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify key
    api_key = verify_api_key(db, token)
    
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return api_key


async def get_current_admin(
    authorization: str = Header(...),
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to verify JWT token and return admin User object.
    
    Args:
        authorization: Authorization header (format: "Bearer <jwt>")
        db: Database session
    
    Returns:
        User object if valid admin
    
    Raises:
        HTTPException: 401 if token invalid or user not found
    
    Example:
        @app.post("/admin/users")
        async def create_user(admin: User = Depends(get_current_admin)):
            return {"admin": admin.email}
    """
    # Check header format
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected: Bearer <jwt>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract token
    token = authorization.replace("Bearer ", "").strip()
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing JWT token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify token
    payload = verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired JWT token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get user from payload
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Lookup user in database
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def get_optional_api_key(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
) -> Optional[ApiKey]:
    """
    Optional dependency for API key (doesn't raise error if missing).
    
    Args:
        authorization: Optional authorization header
        db: Database session
    
    Returns:
        ApiKey object if valid, None if missing or invalid
    
    Example:
        @app.get("/public")
        async def public_route(api_key: Optional[ApiKey] = Depends(get_optional_api_key)):
            if api_key:
                return {"authenticated": True, "tenant": str(api_key.tenant_id)}
            return {"authenticated": False}
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        return None
    
    return verify_api_key(db, token)
