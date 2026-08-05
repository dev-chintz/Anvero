from app.api.v1.endpoints import health, root, users
from fastapi import APIRouter

from app.api.v1.endpoints import health, root, users

router = APIRouter()

router.include_router(root.router)
router.include_router(health.router)
router.include_router(users.router)
