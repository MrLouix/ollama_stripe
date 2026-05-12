"""Admin API endpoints"""

from fastapi import APIRouter
from . import tenants, keys, plans, usage

router = APIRouter()

# Include all admin sub-routers
router.include_router(tenants.router, tags=["admin-tenants"])
router.include_router(keys.router, tags=["admin-keys"])
router.include_router(plans.router, tags=["admin-plans"])
router.include_router(usage.router, tags=["admin-usage"])
