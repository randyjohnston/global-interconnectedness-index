"""FastAPI dependency injection."""

from collections.abc import Generator

from sqlalchemy.orm import Session

from gii.storage.database import get_session
from gii.storage.repository import Repository


def get_db() -> Generator[Session, None, None]:
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def get_repo(session: Session) -> Repository:
    return Repository(session)
