from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, Token
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


# slowapi needs the Request object bound to the route to key/track hits per IP
#
# curl example to verify (run 6x within a minute, the 6th call returns 429):
#   for i in 1 2 3 4 5 6; do
#     curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8000/api/v1/auth/login \
#       -H "Content-Type: application/json" \
#       -d '{"email": "test@example.com", "password": "wrong"}'
#   done
@router.post("/login", response_model=Token)
@limiter.limit(settings.rate_limit_login)
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    service = AuthService(UserRepository(db))
    return service.login(
        email=body.email,
        password=body.password,
    )
