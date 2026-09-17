import threading

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.db.session import get_db
from app.integrations.base import (
    IntegrationAuthError,
    IntegrationError,
    IntegrationNotConfigured,
)
from app.schemas.integration import (
    AllegroImportRequest,
    AllegroImportResult,
    AllegroStatus,
)
from app.services.allegro_import import (
    build_allegro_client,
    build_allegro_import_service,
)

# Every endpoint here requires a logged-in user, same as the orders router.
router = APIRouter(
    prefix="/integrations",
    tags=["Integrations"],
    dependencies=[Depends(get_current_user)],
)

# Allegro rotates the refresh token on every use, so two imports running at
# once would both refresh it and the second refresh invalidates the token the
# first request is still using. Non-blocking: a second click fails fast with
# 409 instead of queueing behind the first import.
_import_lock = threading.Lock()


@router.get("/allegro", response_model=AllegroStatus)
def get_allegro_status(db: Session = Depends(get_db)):
    client = build_allegro_client(db)
    return AllegroStatus(configured=client.is_configured)


@router.post("/allegro/import", response_model=AllegroImportResult)
@limiter.limit("6/minute")
def import_from_allegro(
    request: Request,
    body: AllegroImportRequest,
    db: Session = Depends(get_db),
):
    if not _import_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An Allegro import is already running",
        )
    try:
        service = build_allegro_import_service(db)
        result = service.import_orders(limit=body.limit, offset=body.offset)
    except IntegrationNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Allegro is not configured",
        ) from exc
    except IntegrationAuthError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    finally:
        _import_lock.release()

    return AllegroImportResult(
        created=result.created,
        updated=result.updated,
        cancellation_warnings=result.cancellation_warnings,
    )
