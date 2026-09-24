"""The one door through which Anvero changes anything on a marketplace.

Every write to Allegro or Erli (a status, a tracking number, later messages
and invoices) is to go through `MarketplaceWriter.write`, never straight to a
client. While safe mode is on, which it is until an operator switches it off,
the write is recorded as what *would* have been sent and nothing leaves
Anvero; with it off, it is sent and recorded with the marketplace's answer.
Either way `marketplace_writes` holds the whole story.
"""

import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.marketplace_write import AppSetting, MarketplaceWrite, WriteOutcome
from app.models.order import OrderSource

logger = logging.getLogger(__name__)

SAFE_MODE_KEY = "safe_mode"

# a marketplace's answer or error is kept for reading, not for replay
_MAX_DETAIL_LENGTH = 2000


def safe_mode_setting(db: Session) -> AppSetting | None:
    return db.get(AppSetting, SAFE_MODE_KEY)


def safe_mode_on(db: Session) -> bool:
    """On unless an operator has switched it off: a fresh install sends nothing."""
    setting = safe_mode_setting(db)
    return setting is None or setting.value != "off"


def set_safe_mode(db: Session, enabled: bool, user_id: int | None) -> AppSetting:
    setting = safe_mode_setting(db)
    if setting is None:
        setting = AppSetting(key=SAFE_MODE_KEY)
        db.add(setting)
    setting.value = "on" if enabled else "off"
    setting.updated_by_user_id = user_id
    db.commit()
    db.refresh(setting)
    logger.warning("Safe mode switched %s by user %s", setting.value, user_id)
    return setting


@dataclass(frozen=True)
class WriteResult:
    outcome: WriteOutcome
    record: MarketplaceWrite
    # what `send` returned; None when nothing was sent
    response: Any = None


class MarketplaceWriter:
    def __init__(self, db: Session):
        self.db = db

    def write(
        self,
        source: OrderSource,
        action: str,
        payload: dict[str, Any],
        send: Callable[[], Any],
        order_id: uuid.UUID | None = None,
        user_id: int | None = None,
    ) -> WriteResult:
        """Send one change to a marketplace, unless safe mode holds it back.

        `send` performs the actual request and is only called with safe mode
        off, which is read afresh on every write, so switching it on stops the
        very next one. A failure is recorded and then raised, so the caller
        can tell the operator.
        """
        body = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        if safe_mode_on(self.db):
            record = self._record(source, action, body, WriteOutcome.DRY_RUN, None, order_id, user_id)
            logger.info("Safe mode: %s %s held back, not sent", source.value, action)
            return WriteResult(WriteOutcome.DRY_RUN, record)

        try:
            response = send()
        except Exception as exc:
            self.db.rollback()
            self._record(
                source, action, body, WriteOutcome.FAILED, str(exc) or type(exc).__name__,
                order_id, user_id,
            )
            raise
        detail = None if response is None else json.dumps(response, ensure_ascii=False, default=str)
        record = self._record(source, action, body, WriteOutcome.SENT, detail, order_id, user_id)
        return WriteResult(WriteOutcome.SENT, record, response)

    def _record(
        self,
        source: OrderSource,
        action: str,
        payload: str,
        outcome: WriteOutcome,
        detail: str | None,
        order_id: uuid.UUID | None,
        user_id: int | None,
    ) -> MarketplaceWrite:
        record = MarketplaceWrite(
            # set here rather than by the database: SQLite's clock has whole
            # seconds, and the log is read in order
            created_at=datetime.now(UTC),
            source=source,
            action=action,
            payload=payload,
            outcome=outcome,
            detail=detail[:_MAX_DETAIL_LENGTH] if detail else None,
            order_id=order_id,
            user_id=user_id,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record


def list_writes(
    db: Session, order_id: uuid.UUID | None = None, limit: int = 50
) -> list[MarketplaceWrite]:
    """Newest first; one order's, or everyone's."""
    query = select(MarketplaceWrite)
    if order_id is not None:
        query = query.where(MarketplaceWrite.order_id == order_id)
    query = query.order_by(MarketplaceWrite.created_at.desc(), MarketplaceWrite.id).limit(limit)
    return list(db.scalars(query))
