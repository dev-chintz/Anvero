from fastapi import HTTPException, status

from app.core.security import hash_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate
from app.utils.validators import PasswordValidator


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def create_user(self, data: UserCreate) -> User:
        password_error = PasswordValidator.validate(data.password)
        if password_error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=password_error,
            )

        existing_user = self.repository.get_by_email(data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists",
            )

        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
        )
        return self.repository.create(user)

    def get_user_by_email(self, email: str) -> User | None:
        return self.repository.get_by_email(email)
