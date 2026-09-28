from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health")
def health() -> dict[str, str | None]:
    return {
        "status": "ok",
        "service": "Anvero API",
        # the commit this backend was built from, short; null off an image.
        # Settings waits for it to change after asking for an update.
        "commit": settings.app_commit[:7] or None,
    }
