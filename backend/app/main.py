import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.router import router as api_router
from app.core.config import ensure_secret_key, settings
from app.core.logging import setup_logging
from app.core.rate_limit import limiter
from app.services.retention import run_retention_daily
from app.services.updates import run_update_checks
from app.services.schedule import default_jobs, run_jobs

setup_logging()

# before anything can sign or accept a token
ensure_secret_key(settings.secret_key)



@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # the imports and message syncs the backend starts by itself; the interval
    # is read from the database on every round (services/schedule.py)
    # and, apart from them, the daily erasure of personal data past its
    # retention period (services/retention.py)
    tasks = (
        [
            asyncio.create_task(run_jobs(default_jobs())),
            asyncio.create_task(run_retention_daily()),
        ]
        if settings.scheduler_enabled
        else []
    )
    # and, where the backend runs from an image, whether a newer one is published
    if settings.scheduler_enabled and settings.app_commit and settings.update_check_minutes:
        tasks.append(asyncio.create_task(run_update_checks()))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
)

# state.limiter + exception handler + middleware are all required for
# the @limiter.limit(...) decorators on individual routes to take effect
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(api_router, prefix=settings.api_v1_prefix)
