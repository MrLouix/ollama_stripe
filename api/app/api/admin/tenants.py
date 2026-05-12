"""Admin endpoints for tenant management"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.dependencies import get_db, get_current_admin
from app.db.models import Tenant, User
from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime
import uuid


router = APIRouter()


class TenantCreate(BaseModel):
    """Request body for creating a tenant"""
    name: str
    email: EmailStr


class TenantUpdate(BaseModel):
    """Request body for updating a tenant"""
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    status: Optional[str] = None


class TenantResponse(BaseModel):
    """Response model for tenant"""
    id: uuid.UUID
    name: str
    email: str
    status: str
    stripe_customer_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


@router.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    tenant_data: TenantCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Create a new tenant.
    
    Requires admin authentication.
    """
    # Check if email already exists
    existing = db.query(Tenant).filter(Tenant.email == tenant_data.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with email {tenant_data.email} already exists"
        )
    
    tenant = Tenant(
        name=tenant_data.name,
        email=tenant_data.email,
        status="active"
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    
    return tenant


@router.get("/tenants", response_model=List[TenantResponse])
async def list_tenants(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    List all tenants with pagination.
    
    Requires admin authentication.
    """
    tenants = db.query(Tenant).offset(skip).limit(limit).all()
    return tenants


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Get tenant details by ID.
    
    Requires admin authentication.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )
    return tenant


@router.patch("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: uuid.UUID,
    tenant_data: TenantUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Update tenant information.
    
    Requires admin authentication.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )
    
    # Update fields if provided
    if tenant_data.name is not None:
        tenant.name = tenant_data.name
    if tenant_data.email is not None:
        tenant.email = tenant_data.email
    if tenant_data.status is not None:
        if tenant_data.status not in ["active", "suspended", "deleted"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Status must be 'active', 'suspended', or 'deleted'"
            )
        tenant.status = tenant_data.status
    
    db.commit()
    db.refresh(tenant)
    
    return tenant


@router.delete("/tenants/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: uuid.UUID,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin)
):
    """
    Soft delete a tenant (sets status to 'deleted').
    
    Requires admin authentication.
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )
    
    tenant.status = "deleted"
    db.commit()
    
    return None
