from sqlalchemy.orm import object_session

from app.models.order import AddressType, Order, OrderAddress, OrderItem, OrderShipment
from app.schemas.order import Address, OrderDetails


def apply_details(order: Order, details: OrderDetails) -> None:
    """Replace the order's details with `details`, without committing.

    Used both for a new order and when a re-import refreshes an existing one:
    the marketplace owns every detail, so an item or address it no longer
    reports goes away rather than lingering. The caller commits.
    """
    customer = details.customer
    order.customer_login = customer.login
    order.customer_first_name = customer.first_name
    order.customer_last_name = customer.last_name
    order.customer_company_name = customer.company_name
    order.customer_phone = customer.phone

    order.buyer_message = details.buyer_message
    order.seller_note = details.seller_note

    delivery = details.delivery
    pickup_point = delivery.pickup_point
    order.delivery_method = delivery.method
    order.delivery_cost = delivery.cost
    order.pickup_point_id = pickup_point.id if pickup_point else None
    order.pickup_point_name = pickup_point.name if pickup_point else None
    order.dispatch_by = details.dispatch_by

    payment = details.payment
    order.payment_type = payment.type
    order.payment_provider = payment.provider
    order.paid_amount = payment.paid_amount
    order.paid_at = payment.paid_at

    order.invoice_required = details.invoice.required

    session = object_session(order)
    if session is not None and (order.items or order.addresses):
        # Remove the old rows before adding the new ones. Within one flush
        # SQLAlchemy inserts before it deletes, so replacing an address in a
        # single step would briefly hold two rows of the same type and break
        # the one-per-type constraint.
        order.items.clear()
        order.addresses.clear()
        session.flush()

    order.items = [
        OrderItem(position=position, **item.model_dump())
        for position, item in enumerate(details.items)
    ]

    if details.shipments is not None:
        _replace_shipments(order, details)

    addresses = {
        AddressType.DELIVERY: delivery.address,
        AddressType.PICKUP_POINT: pickup_point.address if pickup_point else None,
        AddressType.INVOICE: details.invoice.address,
    }
    order.addresses = [
        _address_row(address_type, address)
        for address_type, address in addresses.items()
        if address is not None
    ]


def _replace_shipments(order: Order, details: OrderDetails) -> None:
    # tracking read earlier survives a run that could not read it again
    known = {(s.carrier_id, s.waybill): s for s in order.shipments}
    rows = []
    for position, shipment in enumerate(details.shipments or []):
        data = shipment.model_dump()
        previous = known.get((shipment.carrier_id, shipment.waybill))
        if previous is not None and data["tracking_status"] is None:
            data["tracking_status"] = previous.tracking_status
            data["tracking_updated_at"] = previous.tracking_updated_at
        rows.append(OrderShipment(position=position, **data))
    # a parcel entered in Anvero that the marketplace does not list (yet: it
    # was held back by safe mode, or its sending failed) is kept, not lost
    listed = {(row.carrier_id, row.waybill) for row in rows}
    for kept in order.shipments:
        if kept.added_in_anvero and (kept.carrier_id, kept.waybill) not in listed:
            rows.append(
                OrderShipment(
                    position=len(rows),
                    carrier_id=kept.carrier_id,
                    carrier_name=kept.carrier_name,
                    waybill=kept.waybill,
                    shipped_at=kept.shipped_at,
                    tracking_status=kept.tracking_status,
                    tracking_updated_at=kept.tracking_updated_at,
                    external_id=kept.external_id,
                    added_in_anvero=True,
                )
            )
    order.shipments = rows


def _address_row(address_type: AddressType, address: Address) -> OrderAddress:
    return OrderAddress(type=address_type, **address.model_dump())
