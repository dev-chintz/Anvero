from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenPayload

if TYPE_CHECKING:
    from app.models.user import User

password_hash = PasswordHash.recommended()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/login")

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(user_id: int) -> str:
    issued = datetime.now(timezone.utc)
    payload: dict[str, str | datetime] = {
        "sub": str(user_id),
        "exp": issued + timedelta(minutes=settings.access_token_expire_minutes),
        "iat": issued,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        return TokenPayload(sub=int(user_id))
    except jwt.ExpiredSignatureError:
        raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> "User":
    payload = decode_access_token(token)
    user_repository = UserRepository(db)
    user = user_repository.get_by_id(payload.sub)
    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise credentials_exception
    return user
