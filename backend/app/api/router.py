from fastapi import APIRouter
from .routers import auth, admin_orgs_router, org_members_router, admin_users_router

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(admin_orgs_router.router, prefix="/admin/orgs", tags=["Admin Orgs"])
api_router.include_router(org_members_router.router, prefix="/orgs/{org_id}/members", tags=["Org Members"])
api_router.include_router(admin_users_router.router, prefix="/admin/users", tags=["Admin Users"])
