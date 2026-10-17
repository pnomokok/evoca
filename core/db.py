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

    init_db()               # creates tables if they don't exist, adds new columns
    with SessionLocal() as db:
        ...
"""

import os
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
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


# Columns added after the first release. create_all() never alters an existing
# table, so add_missing_columns() adds these to an older database file in place.
# (table, column, SQL type and default)
_ADDED_COLUMNS: list[tuple[str, str, str]] = [
    ("sensitive_topic", "source", "VARCHAR NOT NULL DEFAULT 'family'"),
]


def add_missing_columns(bind: Engine) -> list[str]:
    """Add every column of _ADDED_COLUMNS that an existing table lacks.

    Idempotent: a column that is already there is left alone, and no row is
    dropped or rewritten (existing rows get the column's default). Returns
    "table.column" for each column added.
    """
    added: list[str] = []
    insp = inspect(bind)
    tables = set(insp.get_table_names())
    with bind.begin() as conn:
        for table, column, ddl in _ADDED_COLUMNS:
            if table not in tables:
                continue    # create_all() makes it with every column
            if column in {c["name"] for c in insp.get_columns(table)}:
                continue
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            added.append(f"{table}.{column}")
    return added


def init_db() -> None:
    """Create all tables declared in core.models if they do not yet exist, and
    add columns that an older database file lacks."""
    if not _in_memory:
        _abs_path.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    add_missing_columns(engine)
