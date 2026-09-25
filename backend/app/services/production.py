"""The "to make today" list: the to-make queue turned around, by product.

The queue answers "which orders wait"; this answers "what do I make, and how
many", with each product's orders beside it so a finished piece can go to the
most urgent one.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.order_number import format_order_number
from app.models.order import Order, OrderItem
from app.models.production_check import ProductionCheck
from app.schemas.order import ProductionLine, ProductionList, ProductionOrder

# a tick nobody touched for this long is dropped: the product is long gone from the list
CHECK_KEEP = timedelta(days=90)


def product_key(item: OrderItem) -> str:
    """What makes two order lines the same product.

    The seller's own code first, since it is the same on every marketplace;
    then the listing, then, for an item with neither, its name.
    """
    if item.sku:
        return f"sku:{item.sku}"
    if item.offer_id:
        return f"offer:{item.offer_id}"
    return f"name:{item.name}"


def build_production_list(orders: list[Order]) -> ProductionList:
    """Group the items of `orders` by product.

    `orders` must come most urgent first: the lines keep the order in which
    their product is first needed, so the line with the earliest dispatch
    deadline leads, and lines whose orders have none follow, oldest order
    first.
    """
    lines: dict[str, ProductionLine] = {}
    for order in orders:
        for item in order.items:
            key = product_key(item)
            line = lines.get(key)
            if line is None:
                line = lines[key] = ProductionLine(
                    key=key,
                    sku=item.sku,
                    offer_id=item.offer_id,
                    name=item.name,
                    image_url=item.image_url,
                    quantity=0,
                    dispatch_by=order.dispatch_by,
                    orders=[],
                )
            line.quantity += item.quantity
            line.image_url = line.image_url or item.image_url
            # two lines of one order for the same product are one entry
            if line.orders and line.orders[-1].id == order.id:
                line.orders[-1].quantity += item.quantity
                continue
            line.orders.append(
                ProductionOrder(
                    id=order.id,
                    order_label=format_order_number(order.order_number),
                    source=order.source,
                    status=order.status,
                    quantity=item.quantity,
                    dispatch_by=order.dispatch_by,
                )
            )
    return ProductionList(lines=list(lines.values()), order_count=len(orders))


def mark_done(db: Session, production: ProductionList) -> ProductionList:
    """Say which lines of `production` have been made.

    A line is made when it was ticked for at least as many as it asks for now;
    an order that came in after the tick, and raised the number, brings it back.
    """
    if not production.lines:
        return production
    ticked = {
        check.key: check.quantity for check in db.scalars(select(ProductionCheck)).all()
    }
    for line in production.lines:
        line.done = ticked.get(line.key, 0) >= line.quantity
    return production


def set_check(
    db: Session, key: str, quantity: int, done: bool, user_id: int | None
) -> ProductionCheck | None:
    """Tick `key` off for `quantity`, or take the tick away; returns the tick, or
    None once it is taken away."""
    # a tick that nobody has touched for months is for a product that has left the list
    db.execute(
        delete(ProductionCheck).where(ProductionCheck.checked_at < datetime.now(UTC) - CHECK_KEEP)
    )
    check = db.get(ProductionCheck, key)
    if not done:
        if check is not None:
            db.delete(check)
        db.commit()
        return None
    if check is None:
        check = ProductionCheck(key=key)
        db.add(check)
    check.quantity = quantity
    check.checked_by_user_id = user_id
    check.checked_at = datetime.now(UTC)
    db.commit()
    return check
