from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import ADMIN_ROLE, User
from app.models.user_permission import UserPermission
from app.schemas.user import PermissionGrant


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_email(self, email: str) -> User | None:
        return self.db.query(User).filter(User.email == email).first()

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()

    def list_all(self) -> list[User]:
        return list(self.db.execute(select(User).order_by(User.email)).scalars())

    def create(self, user: User) -> User:
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def save(self, user: User) -> User:
        self.db.commit()
        self.db.refresh(user)
        return user

    def replace_permissions(self, user: User, grants: list[PermissionGrant]) -> None:
        """Set the whole grant list at once: the settings page always sends the full grid.

        Deletes and re-inserts in two steps, flushing between them: clearing the
        relationship and appending replacements in one flush queues the inserts
        before the deletes, and a kept area (e.g. "orders" before and after)
        collides with itself on (user_id, area) before the old row is gone.
        """
        user.permissions.clear()
        self.db.flush()
        for grant in grants:
            user.permissions.append(UserPermission(area=grant.area.value, level=grant.level.value))
        self.db.commit()
        self.db.refresh(user)

    def count_other_active_admins(self, excluding_user_id: int) -> int:
        return (
            self.db.query(User)
            .filter(
                User.role == ADMIN_ROLE,
                User.is_active.is_(True),
                User.id != excluding_user_id,
            )
            .count()
        )
