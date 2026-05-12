"""Authentication service for API keys and JWT tokens"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from app.db.models import ApiKey, User
from app.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.
    
    Returns:
        tuple: (full_key, key_hash, key_prefix)
            - full_key: The complete key to show to user (once only)
            - key_hash: SHA-256 hash to store in database
            - key_prefix: First 12 chars for identification (osg_abc1...)
    
    Example:
        >>> key, hash, prefix = generate_api_key()
        >>> key.startswith("osg_")
        True
        >>> len(key) >= 48
        True
        >>> len(hash) == 64  # SHA-256 hex length
        True
    """
    # Generate secure random key with prefix
    key = "osg_" + secrets.token_urlsafe(36)  # ~48 chars total
    
    # Hash for storage
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    
    # Prefix for identification
    key_prefix = key[:12]  # osg_abc1...
    
    return key, key_hash, key_prefix


def verify_api_key(db: Session, key: str) -> Optional[ApiKey]:
    """
    Verify an API key and return the ApiKey object if valid.
    
    Args:
        db: Database session
        key: The full API key to verify
    
    Returns:
        ApiKey object if valid and active, None otherwise
    
    Side effects:
        Updates last_used_at timestamp if key is valid
    """
    # Hash the provided key
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    
    # Lookup in database
    api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
    
    if not api_key:
        return None
    
    # Check status
    if api_key.status != "active":
        return None
    
    # Check expiration
    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        return None
    
    # Update last used timestamp
    api_key.last_used_at = datetime.utcnow()
    db.commit()
    
    return api_key


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: Plain text password
    
    Returns:
        Hashed password string
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.
    
    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password from database
    
    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Payload data to encode in token (typically {"sub": user_id})
        expires_delta: Optional custom expiration time
    
    Returns:
        Encoded JWT token string
    
    Example:
        >>> token = create_access_token({"sub": "user123"})
        >>> isinstance(token, str)
        True
    """
    to_encode = data.copy()
    
    # Set expiration
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expiration_minutes)
    
    to_encode.update({"exp": expire})
    
    # Encode token
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.admin_secret, 
        algorithm=settings.jwt_algorithm
    )
    
    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    """
    Verify and decode a JWT token.
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded payload dict if valid, None otherwise
    """
    try:
        payload = jwt.decode(
            token, 
            settings.admin_secret, 
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except JWTError:
        return None
