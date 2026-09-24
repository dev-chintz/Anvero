"""Labels through "Wysyłam z Allegro", and the settings they need."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.order_number import format_order_number
from app.core.security import get_current_user
from app.db.session import get_db
from app.integrations.base import IntegrationError, IntegrationNotConfigured
from app.models.user import User
from app.repositories.order_repository import OrderRepository
from app.schemas.marketplace_write import MarketplaceWriteRead
from app.schemas.shipping import (
    LabelChangeResult,
    LabelPrintRequest,
    LabelView,
    PackageSize,
    PickupChangeResult,
    PickupOption,
    PickupOrderRequest,
    PickupProposalRequest,
    PickupRead,
    PrintableLabel,
    ShippingLabelRead,
    ShippingSettings,
)
from app.services.courier_pickups import CourierPickups
from app.services.order_service import OrderService
from app.services.sample_label import build_sample_label
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
    OrderService.ensure_not_deleted(order)
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


def _printable(label) -> PrintableLabel:
    order = label.order
    buyer = " ".join(p for p in (order.customer_first_name, order.customer_last_name) if p)
    return PrintableLabel(
        **ShippingLabelRead.model_validate(label).model_dump(),
        order_id=order.id,
        order_label=format_order_number(order.order_number),
        buyer=buyer or order.customer_login or order.customer_email,
        delivery_method=order.delivery_method,
        pickup=PickupRead.model_validate(label.pickup) if label.pickup else None,
    )


@router.get("/labels", response_model=list[PrintableLabel])
def printable_labels(
    view: LabelView = Query("to_print", description="to_print, no_pickup or all"),
    db: Session = Depends(get_db),
):
    """Bought labels across every order, oldest first; not yet printed by default."""
    return [_printable(label) for label in ShippingLabels(db).printable(view)]


@router.get("/labels/test-pdf")
def test_label_pdf(db: Session = Depends(get_db)):
    """A sample A6 label drawn by Anvero, for checking that a label can be shown
    and printed: nothing is bought, nothing is sent, safe mode does not matter."""
    return Response(
        content=build_sample_label(get_shipping_settings(db)),
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="test-label.pdf"'},
    )


@router.post("/labels/pdf")
def labels_pdf(payload: LabelPrintRequest, db: Session = Depends(get_db)):
    """Several labels as one A6 PDF, in the order asked; notes them printed."""
    try:
        content = ShippingLabels(db).pdf_many(payload.label_ids)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (LabelRefused, IntegrationError) as exc:
        raise _refused(exc) from exc
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="labels.pdf"'},
    )


@router.post("/pickups/proposals", response_model=list[PickupOption])
def pickup_proposals(payload: PickupProposalRequest, db: Session = Depends(get_db)):
    """When a courier could come for these parcels on that day; changes nothing."""
    try:
        options = CourierPickups(db).proposals(payload.label_ids, payload.ready_date)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (LabelRefused, IntegrationError) as exc:
        raise _refused(exc) from exc
    return [PickupOption(id=o.id, label=o.label) for o in options]


@router.post("/pickups", response_model=PickupChangeResult)
def order_pickup(
    payload: PickupOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Order the courier for one of the proposed slots (safe mode permitting)."""
    try:
        pickup, write = CourierPickups(db).order(
            payload.label_ids,
            payload.ready_date,
            payload.proposal_id,
            payload.proposal_label,
            current_user.id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (LabelRefused, IntegrationError) as exc:
        raise _refused(exc) from exc
    return PickupChangeResult(
        pickup=PickupRead.model_validate(pickup) if pickup else None,
        marketplace_write=MarketplaceWriteRead.model_validate(write.record),
    )


@router.post("/pickups/{pickup_id}/refresh", response_model=PickupRead)
def refresh_pickup(pickup_id: uuid.UUID, db: Session = Depends(get_db)):
    pickups = CourierPickups(db)
    pickup = pickups.get(pickup_id)
    if pickup is None:
        raise HTTPException(status_code=404, detail="Pickup not found")
    return pickups.refresh(pickup)

