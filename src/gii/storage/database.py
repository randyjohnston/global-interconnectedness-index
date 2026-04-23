from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import Session, sessionmaker

from gii.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
metadata = MetaData()
metadata.reflect(engine)  # Autoloads EVERYTHING
SessionLocal = sessionmaker(bind=engine)


def get_session() -> Session:
    return SessionLocal()
