import logging

from fastapi import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core import security_log

# in-memory storage is fine for a single-process deployment; switch to a
# redis storage_uri here if the app ever runs with multiple workers/instances
limiter = Limiter(key_func=get_remote_address)


def route_template(request: Request) -> str:
    """The path called, with what a path parameter stood for named instead: `/orders/{order_id}`.

    The matched route's own path is not used: FastAPI gives it without the `/api/v1` prefix. A
    segment equal to a parameter's value is replaced whole, so the `1` of `v1` is not touched by
    an order whose id is 1.
    """
    names = {str(value): name for name, value in request.scope.get("path_params", {}).items()}
    return "/".join("{" + names[part] + "}" if part in names else part for part in request.url.path.split("/"))


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """slowapi's own answer (429), after a line in the security log.

    A burst of refused logins from one address is what a guessing attack looks like, and the
    refusals themselves are not otherwise recorded. An identifier in the path is not copied into
    the log (`route_template`).
    """
    security_log.record(
        security_log.RATE_LIMITED,
        logging.WARNING,
        ip=get_remote_address(request),
        method=request.method,
        route=route_template(request),
        limit=exc.detail,
    )
    return _rate_limit_exceeded_handler(request, exc)
