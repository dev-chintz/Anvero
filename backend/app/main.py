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
from app.services.allegro_sync import scheduler
from app.services.message_sync import message_scheduler

setup_logging()

# before anything can sign or accept a token
ensure_secret_key(settings.secret_key)



@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # imports and message syncs the backend starts by itself; each is a no-op
    # unless its interval is set
    tasks = [asyncio.create_task(scheduler()), asyncio.create_task(message_scheduler())]
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
