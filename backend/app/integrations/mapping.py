"""Reading a marketplace's JSON defensively, shared by every adapter's mapper.

A malformed part of an order costs that part, not the order: these helpers
turn anything unexpected into "absent" and log by field name only, since the
values are buyers' personal data.
"""

import logging
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

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
