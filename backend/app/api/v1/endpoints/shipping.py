"""Labels through "Wysyłam z Allegro", and the settings they need."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.integrations.base import IntegrationError, IntegrationNotConfigured
from app.models.user import User
from app.repositories.order_repository import OrderRepository
from app.schemas.marketplace_write import MarketplaceWriteRead
from app.schemas.shipping import (
    LabelChangeResult,
    PackageSize,
    ShippingLabelRead,
    ShippingSettings,
)
from app.services.order_service import OrderService
from app.services.shipping_labels import LabelRefused, ShippingLabels
from app.services.shipping_settings import get_shipping_settings, save_shipping_settings

router = APIRouter(tags=["Shipping"], dependencies=[Depends(get_current_user)])


@router.get("/settings/shipping", response_model=ShippingSettings)
def get_settings(db: Session = Depends(get_db)):
    return get_shipping_settings(db)


@router.put("/settings/shipping", response_model=ShippingSettings)
def put_settings(
    payload: ShippingSettings,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return save_shipping_settings(db, payload, current_user.id)


def _order(db: Session, order_id: uuid.UUID):
    return OrderService(OrderRepository(db)).get_order(order_id)


def _label(labels: ShippingLabels, order, label_id: uuid.UUID):
    label = labels.get(order, label_id)
    if label is None:
        raise HTTPException(status_code=404, detail="Label not found")
    return label


def _refused(exc: Exception) -> HTTPException:
    if isinstance(exc, LabelRefused):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, IntegrationNotConfigured):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Allegro is not configured")
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.get("/orders/{order_id}/labels", response_model=list[ShippingLabelRead])
def list_labels(order_id: uuid.UUID, db: Session = Depends(get_db)):
    return ShippingLabels(db).for_order(_order(db, order_id))


@router.post("/orders/{order_id}/labels", response_model=LabelChangeResult)
def buy_label(
    order_id: uuid.UUID,
    package: PackageSize,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = _order(db, order_id)
    try:
        label, write = ShippingLabels(db).buy(order, package, current_user.id)
    except (LabelRefused, IntegrationError) as exc:
        raise _refused(exc) from exc
    return LabelChangeResult(
        label=ShippingLabelRead.model_validate(label) if label else None,
        marketplace_write=MarketplaceWriteRead.model_validate(write.record),
    )


@router.post("/orders/{order_id}/labels/{label_id}/refresh", response_model=ShippingLabelRead)
def refresh_label(
    order_id: uuid.UUID,
    label_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = _order(db, order_id)
    labels = ShippingLabels(db)
    return labels.refresh(order, _label(labels, order, label_id), current_user.id)


@router.post("/orders/{order_id}/labels/{label_id}/cancel", response_model=LabelChangeResult)
def cancel_label(
    order_id: uuid.UUID,
    label_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = _order(db, order_id)
    labels = ShippingLabels(db)
    label = _label(labels, order, label_id)
    try:
        write = labels.cancel(order, label, current_user.id)
    except (LabelRefused, IntegrationError) as exc:
        raise _refused(exc) from exc
    return LabelChangeResult(
        label=ShippingLabelRead.model_validate(label),
        marketplace_write=MarketplaceWriteRead.model_validate(write.record),
    )


@router.get("/orders/{order_id}/labels/{label_id}/pdf")
def label_pdf(order_id: uuid.UUID, label_id: uuid.UUID, db: Session = Depends(get_db)):
    order = _order(db, order_id)
    labels = ShippingLabels(db)
    label = _label(labels, order, label_id)
    try:
        content = labels.pdf(label)
    except (LabelRefused, IntegrationError) as exc:
        raise _refused(exc) from exc
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="label-{label.waybill or label.id}.pdf"'},
    )
