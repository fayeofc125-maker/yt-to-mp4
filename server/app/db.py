"""Database setup for durable job state.

SQLite is deliberately configured here rather than in the models so tests can
use an in-memory engine while production uses a WAL-enabled file database.
"""

from collections.abc import Generator

from sqlalchemy import event, inspect, text
from sqlmodel import Session, SQLModel, create_engine


def make_engine(url: str = "sqlite:///clipper.db"):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def create_db_and_tables(engine) -> None:
    SQLModel.metadata.create_all(engine)
    if inspect(engine).has_table("jobrecord"):
        required = {
            "progress_phase": "TEXT NOT NULL DEFAULT 'queued'",
            "progress_percent": "INTEGER NOT NULL DEFAULT 0",
            "created_at": "DATETIME",
            "updated_at": "DATETIME",
            "expires_at": "DATETIME",
            "result_url": "TEXT",
            "object_key": "TEXT",
            "result_size": "INTEGER",
            "spec_metadata": "TEXT NOT NULL DEFAULT '{}'",
            "cancellation_requested": "BOOLEAN NOT NULL DEFAULT 0",
        }
        existing = {column["name"] for column in inspect(engine).get_columns("jobrecord")}
        with engine.begin() as connection:
            for name, definition in required.items():
                if name not in existing:
                    connection.execute(
                        text(f"ALTER TABLE jobrecord ADD COLUMN {name} {definition}")
                    )
            connection.execute(
                text(
                    "UPDATE jobrecord SET created_at = COALESCE(created_at, CURRENT_TIMESTAMP), "
                    "updated_at = COALESCE(updated_at, CURRENT_TIMESTAMP)"
                )
            )


def sessions(engine) -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
