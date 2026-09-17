from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator


def _as_utc(value: datetime) -> datetime:
    """Treat a naive timestamp as UTC and normalise an aware one to UTC.

    Every timestamp is stored in UTC, but SQLite returns them without a zone.
    Serialized as-is, "2026-09-16T13:24:37" is read by a browser as local
    time, which shifted every date in the interface by the UTC offset. With a
    zone attached it goes out as "...Z" and the browser converts it correctly.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


UtcDateTime = Annotated[datetime, AfterValidator(_as_utc)]
