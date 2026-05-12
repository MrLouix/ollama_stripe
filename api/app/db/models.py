"""SQLAlchemy database models"""

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Integer, DateTime, ForeignKey, 
    TIMESTAMP, Numeric, Date, BIGINT, text
)
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import relationship
from app.db.database import Base


class Tenant(Base):
    """Organisation cliente ou tenant"""
    __tablename__ = "tenants"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    email = Column(String(255))
    stripe_customer_id = Column(String(255), unique=True)
    status = Column(String(20), default="active")  # active, suspended, deleted
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    api_keys = relationship("ApiKey", back_populates="tenant", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="tenant", cascade="all, delete-orphan")
    usage_events = relationship("UsageEvent", back_populates="tenant")
    usage_daily = relationship("UsageDaily", back_populates="tenant")
    billing_events = relationship("BillingEvent", back_populates="tenant")
    audit_logs = relationship("AuditLog", back_populates="tenant")


class User(Base):
    """Utilisateurs admin de la plateforme"""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False)  # super_admin, tenant_admin
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    
    # Relations
    tenant = relationship("Tenant")
    audit_logs = relationship("AuditLog", back_populates="user")


class ApiKey(Base):
    """Clés API clients"""
    __tablename__ = "api_keys"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    key_hash = Column(String(64), unique=True, nullable=False)  # SHA-256
    key_prefix = Column(String(12), nullable=False)  # osg_abc1... pour identification
    name = Column(String(255))
    status = Column(String(20), default="active")  # active, suspended, revoked
    expires_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_used_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    
    # Relations
    tenant = relationship("Tenant", back_populates="api_keys")
    usage_events = relationship("UsageEvent", back_populates="api_key")
    usage_daily = relationship("UsageDaily", back_populates="api_key")


class Plan(Base):
    """Plans commerciaux"""
    __tablename__ = "plans"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    plan_type = Column(String(20), nullable=False)  # fixed, metered, fixed_overage, prepaid
    price_cents = Column(Integer, nullable=False)  # prix mensuel en centimes
    rpm_limit = Column(Integer, nullable=False)  # requêtes par minute
    daily_token_quota = Column(BIGINT, nullable=True)  # tokens par jour (NULL = illimité)
    monthly_token_quota = Column(BIGINT, nullable=False)  # tokens par mois
    max_concurrent = Column(Integer, default=5)  # requêtes simultanées max
    max_input_tokens = Column(Integer, default=4096)
    max_output_tokens = Column(Integer, default=4096)
    overage_price_per_1k_cents = Column(Integer, nullable=True)  # prix dépassement par 1k tokens
    stripe_price_id = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    
    # Relations
    subscriptions = relationship("Subscription", back_populates="plan")


class Subscription(Base):
    """Abonnements"""
    __tablename__ = "subscriptions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False)
    stripe_subscription_id = Column(String(255), unique=True)
    stripe_item_id = Column(String(255))  # pour usage records
    status = Column(String(20), nullable=False)  # active, past_due, canceled, trialing
    current_period_start = Column(TIMESTAMP(timezone=True))
    current_period_end = Column(TIMESTAMP(timezone=True))
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relations
    tenant = relationship("Tenant", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")


class Model(Base):
    """Modèles Ollama exposés"""
    __tablename__ = "models"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False)  # ex: llama3, mistral, codellama
    display_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    
    # Relations
    tenant_access = relationship("TenantModelAccess", back_populates="model")


class TenantModelAccess(Base):
    """Accès modèles par tenant"""
    __tablename__ = "tenant_model_access"
    
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), primary_key=True)
    model_id = Column(UUID(as_uuid=True), ForeignKey("models.id"), primary_key=True)
    enabled = Column(Boolean, default=True)
    
    # Relations
    tenant = relationship("Tenant")
    model = relationship("Model", back_populates="tenant_access")


class UsageEvent(Base):
    """Journal d'usage fin (une ligne par requête API)"""
    __tablename__ = "usage_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    api_key_id = Column(UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=False)
    model = Column(String(255), nullable=False)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    # Colonne générée automatiquement - sera ajoutée manuellement dans la migration
    # total_tokens INTEGER GENERATED ALWAYS AS (input_tokens + output_tokens) STORED
    latency_ms = Column(Integer)
    cost_estimate_cents = Column(Numeric(10, 4))
    status_code = Column(Integer)
    error_type = Column(String(50))  # NULL si succès
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    
    # Relations
    tenant = relationship("Tenant", back_populates="usage_events")
    api_key = relationship("ApiKey", back_populates="usage_events")


class UsageDaily(Base):
    """Agrégats journaliers (matérialisés par worker)"""
    __tablename__ = "usage_daily"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    api_key_id = Column(UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=True)
    model = Column(String(255), nullable=False)
    date = Column(Date, nullable=False)
    request_count = Column(Integer, nullable=False, default=0)
    total_input_tokens = Column(BIGINT, nullable=False, default=0)
    total_output_tokens = Column(BIGINT, nullable=False, default=0)
    total_cost_cents = Column(Numeric(12, 4), default=0)
    error_count = Column(Integer, nullable=False, default=0)
    avg_latency_ms = Column(Integer)
    
    # Relations
    tenant = relationship("Tenant", back_populates="usage_daily")
    api_key = relationship("ApiKey", back_populates="usage_daily")


class BillingEvent(Base):
    """Événements billing (sync Stripe)"""
    __tablename__ = "billing_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    event_type = Column(String(50), nullable=False)  # invoice.paid, payment_failed, etc.
    stripe_event_id = Column(String(255), unique=True)
    payload = Column(JSONB)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    
    # Relations
    tenant = relationship("Tenant", back_populates="billing_events")


class AuditLog(Base):
    """Journal d'audit admin"""
    __tablename__ = "audit_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    action = Column(String(100), nullable=False)  # key.created, plan.updated, tenant.suspended...
    resource_type = Column(String(50))
    resource_id = Column(UUID(as_uuid=True))
    details = Column(JSONB)
    ip_address = Column(INET)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)
    
    # Relations
    user = relationship("User", back_populates="audit_logs")
    tenant = relationship("Tenant", back_populates="audit_logs")
