"""Database engine and session management."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

logger = logging.getLogger(__name__)

_engine = None
_SessionFactory = None


def init_db(database_url: str) -> None:
    """Create the engine, session factory, and all tables."""
    global _engine, _SessionFactory
    _engine = create_engine(database_url)
    _SessionFactory = sessionmaker(bind=_engine)
    Base.metadata.create_all(_engine)
    logger.info("Database initialized: %s", database_url.split("@")[-1] if "@" in database_url else "(local)")


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a session that auto-commits on success and rolls back on error."""
    if _SessionFactory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
