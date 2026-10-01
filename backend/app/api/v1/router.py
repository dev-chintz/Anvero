from fastapi import APIRouter

from app.api.v1.endpoints import (
    after_sales,
    app_status,
    auth,
    catalog,
    finance,
    health,
    inpost,
    integrations,
    marketplace_writes,
    messages,
    non_invoiced,
    orders,
    root,
    shipping,
    updates,
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
router.include_router(finance.router)
router.include_router(catalog.router)
router.include_router(catalog.public_router)
router.include_router(non_invoiced.router)
router.include_router(updates.router)
