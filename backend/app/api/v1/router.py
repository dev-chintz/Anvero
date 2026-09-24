from fastapi import APIRouter

from app.api.v1.endpoints import (
    after_sales,
    app_status,
    auth,
    health,
    inpost,
    integrations,
    marketplace_writes,
    messages,
    orders,
    root,
    shipping,
    users,
)

router = APIRouter()

router.include_router(root.router)
router.include_router(health.router)
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(orders.router)
router.include_router(integrations.router)
router.include_router(marketplace_writes.router)
router.include_router(app_status.router)
router.include_router(shipping.router)
router.include_router(inpost.router)

router.include_router(messages.router)
router.include_router(after_sales.router)
