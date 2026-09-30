from fastapi import HTTPException, status

from app.core.security import hash_password
from app.models.user import ADMIN_ROLE, User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, repository: UserRepository):
        self.repository = repository

    def list_users(self) -> list[User]:
        return self.repository.list_all()

    def create_user(self, data: UserCreate) -> User:
        existing_user = self.repository.get_by_email(data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this email already exists",
            )

        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            role=data.role,
        )
        user = self.repository.create(user)
        # an admin can do everything already; stored grants would be dead weight
        if data.role != ADMIN_ROLE and data.permissions:
            self.repository.replace_permissions(user, data.permissions)
        return user

    def update_user(self, user_id: int, data: UserUpdate) -> User:
        user = self.repository.get_by_id(user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        next_role = data.role if data.role is not None else user.role
        next_active = data.is_active if data.is_active is not None else user.is_active
        losing_admin = user.role == ADMIN_ROLE and (next_role != ADMIN_ROLE or not next_active)
        if losing_admin and self.repository.count_other_active_admins(user.id) == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least one active administrator account must remain",
            )

        if data.role is not None:
            user.role = data.role
        if data.is_active is not None:
            user.is_active = data.is_active
        if data.password is not None:
            user.hashed_password = hash_password(data.password)
            # whoever was logged in with the old password is logged out
            user.token_version += 1
        user = self.repository.save(user)

        if data.permissions is not None:
            # an admin can do everything already; stored grants would be dead weight
            self.repository.replace_permissions(user, [] if user.role == ADMIN_ROLE else data.permissions)

        return user

    def set_password(self, email: str, password: str) -> User:
        user = self.repository.get_by_email(email)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No user with this email",
            )

        user.hashed_password = hash_password(password)
        # whoever was logged in with the old password is logged out
        user.token_version += 1
        return self.repository.save(user)

    def get_user_by_email(self, email: str) -> User | None:
        return self.repository.get_by_email(email)
