import threading

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

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
    if not _import_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An Allegro import is already running",
        )
    try:
        service = build_allegro_import_service(db)
        result = service.sync_orders()
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
