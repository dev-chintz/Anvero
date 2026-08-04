from fastapi import APIRouter

from app.api.v1.endpoints import health, root

router = APIRouter()

router.include_router(root.router)
router.include_router(health.router)