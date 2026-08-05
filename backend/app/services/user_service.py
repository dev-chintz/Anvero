from app.models.user import User
from app.repositories.user_repository import UserRepository


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def get_user_by_email(self, email: str) -> User | None:
        return self.repository.get_by_email(email)

    def create_user(self, user: User) -> User:
        return self.repository.create(user)