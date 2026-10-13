"""
Database engine, session factory, and init_db().

Database path is read from the EVOCA_DB_PATH environment variable.
Default: data/evoca.db (relative to the repo root).

Usage:
    from core.db import SessionLocal, init_db

    init_db()               # creates tables if they don't exist
    with SessionLocal() as db:
        ...
"""

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.models import Base

# Resolve DB path -----------------------------------------------------------
_default_path = Path(__file__).parent.parent / "data" / "evoca.db"
_db_path = os.environ.get("EVOCA_DB_PATH", str(_default_path))

# SQLite URL — three slashes for a relative path, four for absolute.
# We always convert to absolute so the URL is unambiguous.
_abs_path = Path(_db_path).resolve()
DATABASE_URL = f"sqlite:///{_abs_path}"

# Engine — check_same_thread=False is required for SQLite when the session
# may be used across request threads (e.g. FastAPI).
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

# Session factory ------------------------------------------------------------
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def init_db() -> None:
    """Create all tables declared in core.models if they do not yet exist."""
    _abs_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
