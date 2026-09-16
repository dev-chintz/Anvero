from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import RateLimiter
from app.db.session import get_db
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, Token
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])
limiter = RateLimiter(
    max_attempts=settings.rate_limit_max_attempts,
    window_seconds=settings.rate_limit_window_seconds,
)


@router.post("/login", response_model=Token)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    if not limiter.is_allowed(request.email):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
        )

    service = AuthService(UserRepository(db))
    return service.login(
        email=request.email,
        password=request.password,
    )
