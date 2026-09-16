from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserRead
from app.services.user_service import UserService

if TYPE_CHECKING:
    from app.models.user import User

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/register", response_model=UserRead)
def register(user: UserCreate, db: Session = Depends(get_db)):
    service = UserService(UserRepository(db))
    new_user = service.create_user(user)
    return new_user


@router.get("/me", response_model=UserRead)
def read_users_me(current_user: "User" = Depends(get_current_user)):
    return current_user
