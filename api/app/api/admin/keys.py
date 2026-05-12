"""Admin endpoints for API key management"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_admin
from app.db.models import ApiKey, Tenant, User
from app.services.auth import generate_api_key
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import uuid


router = APIRouter()


class ApiKeyCreate(BaseModel):
    """Request body for creating an API key"""
    tenant_id: uuid.UUID
    name: str
    expires_at: Optional[datetime] = None


class ApiKeyResponse(BaseModel):
    """Response model for API key"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    key_prefix: str
    name: str
    status: str
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    created_at: datetime
    key: Optional[str] = None  # Only returned on creation
    
    class Config:
        from_attributes = True


@router.post("/keys", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    key_data: ApiKeyCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Create a new API key for a tenant.
    
    The full API key is only returned once during creation.
    Requires admin authentication.
    """
    # Verify tenant exists
    tenant = db.query(Tenant).filter(Tenant.id == key_data.tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {key_data.tenant_id} not found"
        )
    
    # Generate API key
    key, key_hash, key_prefix = generate_api_key()
    
    # Create API key record
    api_key = ApiKey(
        tenant_id=key_data.tenant_id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=key_data.name,
        status="active",
        expires_at=key_data.expires_at
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    
    # Return with the plain key (only time it's shown)
    response = ApiKeyResponse.model_validate(api_key)
    response.key = key
    
    return response


@router.get("/keys", response_model=List[ApiKeyResponse])
async def list_api_keys(
    tenant_id: Optional[uuid.UUID] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    List API keys, optionally filtered by tenant.
    
    Requires admin authentication.
    """
    query = db.query(ApiKey)
    
    if tenant_id:
        query = query.filter(ApiKey.tenant_id == tenant_id)
    
    keys = query.offset(skip).limit(limit).all()
    return keys


@router.get("/keys/{key_id}", response_model=ApiKeyResponse)
async def get_api_key(
    key_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Get API key details by ID.
    
    Requires admin authentication.
    """
    api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key {key_id} not found"
        )
    return api_key


@router.delete("/keys/{key_id}", status_code=status.HTTP_200_OK)
async def revoke_api_key(
    key_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Revoke an API key (sets status to 'revoked').
    
    Requires admin authentication.
    """
    api_key = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key {key_id} not found"
        )
    
    if api_key.status == "revoked":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key is already revoked"
        )
    
    api_key.status = "revoked"
    db.commit()
    
    return {"message": "API key revoked successfully", "key_id": str(key_id)}
