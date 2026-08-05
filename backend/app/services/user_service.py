from app.core.security import hash_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def create_user(self, data: UserCreate) -> User:
        return User(
            email=data.email,
            hashed_password=hash_password(data.password),
        )

    def get_user_by_email(self, email: str) -> User | None:
        return self.repository.get_by_email(email)