from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1.router import router as api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.rate_limit import limiter

setup_logging()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
)

# state.limiter + exception handler + middleware are all required for
# the @limiter.limit(...) decorators on individual routes to take effect
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.include_router(api_router, prefix=settings.api_v1_prefix)
