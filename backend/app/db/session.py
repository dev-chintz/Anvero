from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.database_url,
    # Echo used to follow DEBUG, which .env.example turns on, and it printed
    # every statement with its values: buyers' names, addresses and phone
    # numbers, and Allegro refresh tokens as they were stored.
    echo=settings.sql_echo,
    # Values stay out of the echo and out of database error messages, which
    # end up in tracebacks and logs; the statements themselves still show.
    hide_parameters=True,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
