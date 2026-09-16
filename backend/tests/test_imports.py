from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserRead
from app.services.user_service import UserService


def test_imports():
    assert User is not None
    assert UserRepository is not None
    assert UserService is not None
    assert UserCreate is not None
    assert UserRead is not None
