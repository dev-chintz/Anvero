from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.db.session import get_db
from app.integrations.allegro.authorization import (
    AuthorizationDenied,
    AuthorizationExpired,
)
from app.integrations.base import (
    IntegrationAuthError,
    IntegrationError,
    IntegrationNotConfigured,
)
from app.repositories.integration_credential_repository import (
    IntegrationCredentialRepository,
)
from app.schemas.integration import (
    AllegroConnectPoll,
    AllegroConnectStart,
    AllegroImportResult,
    AllegroSettingsRequest,
    AllegroStatus,
)
from app.services import allegro_settings
from app.services.allegro_import import (
    build_allegro_client,
    build_allegro_import_service,
)
from app.services.allegro_sync import ImportAlreadyRunning, import_lock, run_import

# Every endpoint here requires a logged-in user, same as the orders router.
router = APIRouter(
    prefix="/integrations",
    tags=["Integrations"],
    dependencies=[Depends(get_current_user)],
)

# one import at a time, shared with the scheduled ones (see allegro_sync)
_import_lock = import_lock


def _status(db: Session) -> AllegroStatus:
    application = allegro_settings.resolve_application(db)
    credential = IntegrationCredentialRepository(db).get(allegro_settings.PROVIDER)
    return AllegroStatus(
        configured=build_allegro_client(db).is_configured,
        connected=credential is not None or bool(application.seed_refresh_token),
        application_complete=application.is_complete,
        client_id=application.client_id or None,
        user_agent=application.user_agent or None,
        environment=application.environment,
        source=application.source,
        account_login=credential.account_login if credential else None,
        last_import_at=credential.last_import_at if credential else None,
        last_import_created=credential.last_import_created if credential else None,
        last_import_updated=credential.last_import_updated if credential else None,
        last_import_error=credential.last_import_error if credential else None,
        auto_import_interval_minutes=settings.allegro_import_interval_minutes,
    )


@router.get("/allegro", response_model=AllegroStatus)
def get_allegro_status(db: Session = Depends(get_db)):
    return _status(db)


@router.put("/allegro/settings", response_model=AllegroStatus)
def save_allegro_settings(body: AllegroSettingsRequest, db: Session = Depends(get_db)):
    """Store the application's credentials; the secret is never returned."""
    # changing them may disconnect the account, which touches the token an
    # import could be refreshing at this moment
    if not _import_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An Allegro import is running; try again when it has finished",
        )
    try:
        allegro_settings.save_application(
            db,
            client_id=body.client_id.strip(),
            client_secret=body.client_secret.strip() if body.client_secret else None,
            user_agent=body.user_agent.strip(),
            environment=body.environment,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        _import_lock.release()
    return _status(db)


@router.post("/allegro/connect", response_model=AllegroConnectStart)
@limiter.limit("10/minute")
def start_allegro_connection(request: Request, db: Session = Depends(get_db)):
    """Begin connecting a seller: returns the link they must open and confirm."""
    try:
        flow, link = allegro_settings.flows.start(db)
    except IntegrationNotConfigured as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return AllegroConnectStart(
        flow_id=flow.flow_id,
        verification_uri=link,
        user_code=flow.authorization.user_code,
        interval=flow.interval,
        expires_in=flow.authorization.expires_in,
    )


@router.get("/allegro/connect/{flow_id}", response_model=AllegroConnectPoll)
@limiter.limit("60/minute")
def poll_allegro_connection(request: Request, flow_id: str, db: Session = Depends(get_db)):
    """Check whether the seller has confirmed yet."""
    # completing the connection refreshes the token once, like an import does
    if not _import_lock.acquire(blocking=False):
        return AllegroConnectPoll(status="pending")
    try:
        login = allegro_settings.flows.poll(db, flow_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (TimeoutError, AuthorizationExpired) as exc:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc)) from exc
    except AuthorizationDenied as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    finally:
        _import_lock.release()

    if login is None:
        return AllegroConnectPoll(status="pending")
    return AllegroConnectPoll(status="connected", account_login=login or None)


@router.delete("/allegro/connection", response_model=AllegroStatus)
def disconnect_allegro(db: Session = Depends(get_db)):
    """Forget the connected account; the application's credentials stay."""
    if not _import_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An Allegro import is running; try again when it has finished",
        )
    try:
        allegro_settings.flows.cancel()
        IntegrationCredentialRepository(db).disconnect(allegro_settings.PROVIDER)
    finally:
        _import_lock.release()
    return _status(db)


@router.post("/allegro/import", response_model=AllegroImportResult)
@limiter.limit("6/minute")
def import_from_allegro(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        result = run_import(db, lambda: build_allegro_import_service(db))
    except ImportAlreadyRunning as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An Allegro import is already running",
        ) from exc
    except IntegrationNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Allegro is not configured",
        ) from exc
    except IntegrationAuthError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return AllegroImportResult(
        created=result.created,
        updated=result.updated,
        cancellation_warnings=result.cancellation_warnings,
    )
