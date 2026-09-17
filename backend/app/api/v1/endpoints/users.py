from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.schemas.user import UserRead

if TYPE_CHECKING:
    from app.models.user import User

router = APIRouter(prefix="/users", tags=["Users"])

# There is deliberately no registration endpoint. With one, anyone who can
# reach the API could create an account and pass every login check. Accounts
# are created with scripts/create_user.py.


@router.get("/me", response_model=UserRead)
def read_users_me(current_user: "User" = Depends(get_current_user)):
    return current_user
