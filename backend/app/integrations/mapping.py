"""Reading a marketplace's JSON defensively, shared by every adapter's mapper.

A malformed part of an order costs that part, not the order: these helpers
turn anything unexpected into "absent" and log by field name only, since the
values are buyers' personal data.
"""

import logging
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.schemas.order import OrderCreate

logger = logging.getLogger(__name__)

# what an adapter is given to ask which pictures Anvero already holds: the offer
# ids it has met, answered with the address of the picture stored for each
KnownImages = Callable[[list[str]], dict[str, str]]

Part = TypeVar("Part", bound=BaseModel)


def obj(value: Any) -> dict[str, Any]:
    """The value if it is a JSON object, otherwise an empty one.

    Details are read defensively: a malformed part costs that part, not the
    order.
    """
    return value if isinstance(value, dict) else {}


def text(value: Any) -> str | None:
    """A trimmed string, or None for anything absent, blank or not text."""
    if isinstance(value, bool) or not isinstance(value, str | int):
        return None
    return str(value).strip() or None


def attach_item_images(
    orders: Iterable[OrderCreate],
    fetch: Callable[[str], str | None],
    known: KnownImages | None = None,
) -> None:
    """Give each item its offer's picture, asking the marketplace as little as possible.

    A picture Anvero already holds for an offer (`known`) is reused, since an
    offer's picture hardly ever changes and re-reading it for every open order on
    every import was most of an import's requests. Only offers with none stored
    are fetched, once each however many items carry them. `fetch` never raises,
    so an offer whose picture could not be read leaves its items without one.
    """
    orders = list(orders)
    offer_ids = sorted({item.offer_id for order in orders for item in order.items if item.offer_id})
    images: dict[str, str | None] = dict(known(offer_ids)) if known and offer_ids else {}
    for order in orders:
        for item in order.items:
            if not item.offer_id:
                continue
            if item.offer_id not in images:
                images[item.offer_id] = fetch(item.offer_id)
            item.image_url = images[item.offer_id]


def build(
    model: type[Part], external_id: Any, part: str, fields: dict, label: str = "Order"
) -> Part | None:
    """Build one part of the details, keeping as much of it as is valid.

    An optional field that fails validation (a phone number longer than any
    real one, an unreadable date) is dropped and the rest kept. If a required
    field fails, such as a line item without a name, the part is dropped.
    Either way it is logged by field name only: the values are buyers'
    personal data, which do not belong in logs. `label` names what
    `external_id` identifies in the log line - every caller but the messaging
    mapper is building part of an order.
    """
    try:
        return model(**fields)
    except ValidationError as exc:
        bad = sorted({str(err["loc"][0]) for err in exc.errors() if err["loc"]})
        required = [name for name in bad if model.model_fields[name].is_required()]
        if required:
            logger.warning(
                "%s %s: skipping %s, unreadable %s",
                label,
                external_id,
                part,
                ", ".join(required),
            )
            return None
        logger.warning(
            "%s %s: ignoring unreadable %s in %s", label, external_id, ", ".join(bad), part
        )
        return model(**{k: v for k, v in fields.items() if k not in bad})
