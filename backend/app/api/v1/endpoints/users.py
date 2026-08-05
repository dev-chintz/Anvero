from fastapi import APIRouter

from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/register")
def register(user: UserCreate):
    service = UserService(UserRepository(None))

    new_user = service.create_user(user)

    return {
    "message": "User registered successfully",
    "email": new_user.email,
}