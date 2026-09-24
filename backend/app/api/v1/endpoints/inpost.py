"""InPost: the connection, and parcel locker shipments made and printed from Anvero."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.core.order_number import format_order_number
from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.db.session import get_db
from app.integrations.base import (
    IntegrationAuthError,
    IntegrationError,
    IntegrationNotConfigured,
)
from app.models.user import User
from app.repositories.order_repository import OrderRepository
from app.schemas.inpost import (
    InpostAwaitingOrder,
    InpostBulkCreateRequest,
    InpostBulkItem,
    InpostBulkResult,
    InpostChangeResult,
    InpostCreateRequest,
    InpostPrintable,
    InpostPrintRequest,
    InpostSettingsRequest,
    InpostShipmentRead,
    InpostStatus,
    InpostTemplateRequest,
)
from app.schemas.marketplace_write import MarketplaceWriteRead
from app.services import inpost_settings
from app.services.inpost_shipments import InpostRefused, InpostShipments, buyer_name
from app.services.marketplace_writes import WriteResult
from app.services.order_service import OrderService

router = APIRouter(tags=["InPost"], dependencies=[Depends(get_current_user)])


def _status(db: Session) -> InpostStatus:
    settings = inpost_settings.get_settings(db)
    return InpostStatus(
        configured=settings.configured,
        environment=settings.environment,  # type: ignore[arg-type]
        organization_id=settings.organization_id or None,
        token_hint=settings.token_hint,
        default_template=settings.default_template,  # type: ignore[arg-type]
    )


def _refused(exc: Exception) -> HTTPException:
    if isinstance(exc, InpostRefused):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, IntegrationNotConfigured):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail="InPost is not configured")
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


def _write(result: WriteResult | None) -> MarketplaceWriteRead | None:
    return MarketplaceWriteRead.model_validate(result.record) if result is not None else None


def _order(db: Session, order_id: uuid.UUID):
    return OrderService(OrderRepository(db)).get_order(order_id)


def _shipment(shipments: InpostShipments, order, shipment_id: uuid.UUID):
    shipment = shipments.get(order, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="InPost shipment not found")
    return shipment


# ---- the connection ------------------------------------------------------------------


@router.get("/integrations/inpost", response_model=InpostStatus)
def get_inpost_status(db: Session = Depends(get_db)):
    return _status(db)


@router.put("/integrations/inpost/settings", response_model=InpostStatus)
@limiter.limit("10/minute")
def save_inpost_settings(
    request: Request,
    body: InpostSettingsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save the token, organization and environment, once InPost has accepted them.

    The token can be left out to keep the one already saved (to change only the
    organization or the environment). A combination InPost refuses, or one that cannot
    be tried because InPost does not answer, is not saved: better to say so now than
    to leave settings that fail at the first parcel.
    """
    token = body.token or inpost_settings.get_settings(db).token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Enter the InPost token"
        )
    try:
        inpost_settings.check(token, body.organization_id, body.environment)
    except IntegrationAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"InPost did not accept this token and organization: {exc}",
        ) from exc
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    inpost_settings.save_settings(
        db, token, body.organization_id, body.environment, body.default_template, current_user.id
    )
    return _status(db)


@router.put("/integrations/inpost/template", response_model=InpostStatus)
def save_inpost_template(
    body: InpostTemplateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change the size offered by default, without asking for the token again."""
    inpost_settings.save_template(db, body.default_template, current_user.id)
    return _status(db)


@router.delete("/integrations/inpost/settings", response_model=InpostStatus)
def forget_inpost_settings(db: Session = Depends(get_db)):
    """Forget the token and the organization."""
    inpost_settings.clear_settings(db)
    return _status(db)


# ---- one order ---------------------------------------------------------------------------


@router.get("/orders/{order_id}/inpost-shipments", response_model=list[InpostShipmentRead])
def list_order_shipments(order_id: uuid.UUID, db: Session = Depends(get_db)):
    return InpostShipments(db).for_order(_order(db, order_id))


@router.post("/orders/{order_id}/inpost-shipments", response_model=InpostChangeResult)
def create_order_shipment(
    order_id: uuid.UUID,
    body: InpostCreateRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = _order(db, order_id)
    OrderService.ensure_not_deleted(order)
    try:
        outcome = InpostShipments(db).create(
            order, body.template if body else None, current_user.id
        )
    except (InpostRefused, IntegrationError) as exc:
        raise _refused(exc) from exc
    return InpostChangeResult(
        shipment=InpostShipmentRead.model_validate(outcome.shipment) if outcome.shipment else None,
        marketplace_write=_write(outcome.write),
        tracking_write=_write(outcome.tracking_write),
    )


@router.post(
    "/orders/{order_id}/inpost-shipments/{shipment_id}/refresh", response_model=InpostChangeResult
)
def refresh_order_shipment(
    order_id: uuid.UUID,
    shipment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = _order(db, order_id)
    shipments = InpostShipments(db)
    shipment = _shipment(shipments, order, shipment_id)
    try:
        tracking_write = shipments.refresh(order, shipment, current_user.id)
    except (InpostRefused, IntegrationError) as exc:
        raise _refused(exc) from exc
    return InpostChangeResult(
        shipment=InpostShipmentRead.model_validate(shipment), tracking_write=_write(tracking_write)
    )


@router.post(
    "/orders/{order_id}/inpost-shipments/{shipment_id}/cancel", response_model=InpostChangeResult
)
def cancel_order_shipment(
    order_id: uuid.UUID,
    shipment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    order = _order(db, order_id)
    shipments = InpostShipments(db)
    shipment = _shipment(shipments, order, shipment_id)
    try:
        result = shipments.cancel(order, shipment, current_user.id)
    except (InpostRefused, IntegrationError) as exc:
        raise _refused(exc) from exc
    return InpostChangeResult(
        shipment=InpostShipmentRead.model_validate(shipment), marketplace_write=_write(result)
    )


# ---- many at once ----------------------------------------------------------------------------


@router.get("/inpost/orders", response_model=list[InpostAwaitingOrder])
def orders_awaiting_a_parcel(db: Session = Depends(get_db)):
    """Orders a locker parcel could be made for now (no tracking number yet)."""
    return [
        InpostAwaitingOrder(
            id=order.id,
            order_label=format_order_number(order.order_number),
            buyer=buyer_name(order),
            target_point=str(order.pickup_point_id),
            pickup_point_name=order.pickup_point_name,
            delivery_method=order.delivery_method,
            status=order.status.value,
            dispatch_by=order.dispatch_by,
        )
        for order in InpostShipments(db).awaiting_parcel()
    ]


@router.post("/inpost/shipments", response_model=InpostBulkResult)
def create_shipments(
    body: InpostBulkCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Make a parcel for each order asked for. One order's refusal does not stop the others."""
    service = OrderService(OrderRepository(db))
    orders = [service.get_order(order_id) for order_id in dict.fromkeys(body.order_ids)]
    outcomes = InpostShipments(db).create_many(orders, body.template, current_user.id)
    return InpostBulkResult(
        items=[
            InpostBulkItem(
                order_id=o.order.id,
                order_label=format_order_number(o.order.order_number),
                outcome=o.outcome,  # type: ignore[arg-type]
                message=o.message,
                shipment=InpostShipmentRead.model_validate(o.shipment) if o.shipment else None,
            )
            for o in outcomes
        ]
    )


@router.get("/inpost/labels", response_model=list[InpostPrintable])
def printable_labels(printed: bool | None = Query(default=False), db: Session = Depends(get_db)):
    """Shipments with a number, oldest first: not yet printed (default), printed, or all."""
    return [
        InpostPrintable(
            **InpostShipmentRead.model_validate(s).model_dump(),
            order_label=format_order_number(s.order.order_number),
            buyer=buyer_name(s.order),
        )
        for s in InpostShipments(db).printable(printed)
    ]


@router.post("/inpost/labels/pdf")
def labels_pdf(body: InpostPrintRequest, db: Session = Depends(get_db)):
    """Several labels as one A6 PDF, in the order asked; notes them printed."""
    try:
        content = InpostShipments(db).pdf_many(body.shipment_ids)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (InpostRefused, IntegrationError) as exc:
        raise _refused(exc) from exc
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="inpost-labels.pdf"'},
    )
