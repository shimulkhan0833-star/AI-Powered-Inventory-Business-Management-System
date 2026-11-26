"""SQLAlchemy connection and session management for MySQL."""

import os
from functools import lru_cache
from typing import Iterator

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()


class Base(DeclarativeBase):
    """Base for the application's SQLAlchemy models."""


@lru_cache
def get_engine() -> Engine:
    """Create the engine on first use, without opening a connection at startup."""
    required = ("DB_USER", "DB_PASSWORD", "DB_NAME")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing database settings: {', '.join(missing)}")

    url = URL.create(
        drivername="mysql+pymysql",
        username=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.environ["DB_NAME"],
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, pool_pre_ping=True)


def get_db() -> Iterator[Session]:
    """Provide a session to a request and close it afterwards."""
    session_factory = sessionmaker(bind=get_engine())
    with session_factory() as session:
        yield session
