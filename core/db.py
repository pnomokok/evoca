"""
Database engine, session factory, and init_db().

Database path is read from the EVOCA_DB_PATH environment variable.
Default: data/evoca.db (relative to the repo root).
Set EVOCA_DB_PATH=:memory: for a transient in-memory database (used in tests).

The parent directory of the database file is created at import time so that
callers (e.g. core.seed) can call drop_all() before init_db() without hitting
"unable to open database file".

A "connect" event listener enables SQLite foreign-key enforcement
(PRAGMA foreign_keys=ON) for every new connection.

Usage:
    from core.db import SessionLocal, init_db

    init_db()               # creates tables if they don't exist
    with SessionLocal() as db:
        ...
"""

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from core.models import Base

# Resolve DB path -----------------------------------------------------------
_default_path = Path(__file__).parent.parent / "data" / "evoca.db"
_db_path = os.environ.get("EVOCA_DB_PATH", str(_default_path))

# For in-memory databases (:memory:) skip directory creation.
_in_memory = _db_path == ":memory:"

# SQLite URL — three slashes for a relative path, four for absolute.
# We always convert to absolute for file-backed databases.
if _in_memory:
    DATABASE_URL = "sqlite:///:memory:"
    _abs_path = Path(":memory:")
else:
    _abs_path = Path(_db_path).resolve()
    DATABASE_URL = f"sqlite:///{_abs_path}"
    # Create the parent directory at import time so that drop_all() in seed.py
    # (which runs before init_db()) never hits "unable to open database file".
    _abs_path.parent.mkdir(parents=True, exist_ok=True)


def _set_sqlite_pragma(dbapi_conn, _connection_record):
    """Enable FK enforcement for every new SQLite connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Engine — check_same_thread=False is required for SQLite when the session
# may be used across request threads (e.g. FastAPI).
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)
event.listen(engine, "connect", _set_sqlite_pragma)

# Session factory ------------------------------------------------------------
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def init_db() -> None:
    """Create all tables declared in core.models if they do not yet exist."""
    if not _in_memory:
        _abs_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
