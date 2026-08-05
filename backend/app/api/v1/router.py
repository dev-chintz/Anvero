from app.api.v1.endpoints import health, root
from fastapi import APIRouter

router = APIRouter()

router.include_router(root.router)
router.include_router(health.router)
