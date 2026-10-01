from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.permissions import require_admin
from app.core.security import get_current_user
from app.db.session import get_db
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services.user_service import UserService

if TYPE_CHECKING:
    from app.models.user import User

router = APIRouter(prefix="/users", tags=["Users"])

# There is deliberately no registration endpoint. With one, anyone who can
# reach the API could create an account and pass every login check. Accounts
# are created here by an administrator, or with scripts/create_user.py.


@router.get("/me", response_model=UserRead)
def read_users_me(current_user: "User" = Depends(get_current_user)):
    return current_user


@router.get("", response_model=list[UserRead], dependencies=[Depends(require_admin)])
def list_users(db: Session = Depends(get_db)):
    return UserService(UserRepository(db)).list_users()


# The administrator is a parameter, not only a dependency, so the security log can say who made the
# change (`actor`, app/core/security_log.py).
@router.post("", response_model=UserRead, status_code=201)
def create_user(data: UserCreate, db: Session = Depends(get_db), admin: "User" = Depends(require_admin)):
    return UserService(UserRepository(db)).create_user(data, actor_id=admin.id)


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int, data: UserUpdate, db: Session = Depends(get_db), admin: "User" = Depends(require_admin)
):
    return UserService(UserRepository(db)).update_user(user_id, data, actor_id=admin.id)
