import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.order import OrderSource
from app.models.user import User
from app.repositories.message_repository import MessageRepository
from app.schemas.message import (
    ThreadAsideUpdate,
    ThreadDetailRead,
    ThreadRead,
    ThreadReplyRequest,
    ThreadReplyResult,
)
from app.services.message_writes import MessageWrites

# Every endpoint here requires a logged-in user, same as the orders router.
router = APIRouter(prefix="/messages", tags=["Messages"], dependencies=[Depends(get_current_user)])


def _get_thread(db: Session, thread_id: uuid.UUID):
    thread = MessageRepository(db).get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    return thread


@router.get("/threads", response_model=list[ThreadRead])
def list_threads(
    source: OrderSource | None = Query(default=None),
    aside: bool | None = Query(default=None),
    unread_only: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """The unified inbox: every thread, newest activity first.

    Threads set aside are excluded unless `aside=true` is asked for
    explicitly, so the default view is what still needs attention.
    """
    return MessageRepository(db).list_threads(
        source=source,
        aside=aside if aside is not None else False,
        unread_only=unread_only,
    )


@router.get("/threads/{thread_id}", response_model=ThreadDetailRead)
def get_thread(thread_id: uuid.UUID, db: Session = Depends(get_db)):
    return _get_thread(db, thread_id)


@router.patch("/threads/{thread_id}/aside", response_model=ThreadRead)
def set_thread_aside(thread_id: uuid.UUID, body: ThreadAsideUpdate, db: Session = Depends(get_db)):
    """Put a thread aside to come back to later, or bring it back."""
    thread = _get_thread(db, thread_id)
    return MessageRepository(db).set_aside(thread, body.aside)


@router.post("/threads/{thread_id}/reply", response_model=ThreadReplyResult)
def reply_to_thread(
    thread_id: uuid.UUID,
    body: ThreadReplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    thread = _get_thread(db, thread_id)
    try:
        _, result = MessageWrites(db).reply(thread, body.text, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.refresh(thread)
    return ThreadReplyResult(
        thread=ThreadDetailRead.model_validate(thread), marketplace_write=result.record
    )
