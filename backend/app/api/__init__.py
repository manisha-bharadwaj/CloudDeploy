"""API package."""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.deployments import router as deployments_router
from app.api.projects import router as projects_router

api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(projects_router)
api_router.include_router(deployments_router)

__all__ = ["api_router"]
