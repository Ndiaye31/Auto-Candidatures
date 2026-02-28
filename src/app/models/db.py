from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.tables import SchemaVersion

DB_PATH = Path("data/app.db")
DB_URL = f"sqlite:///{DB_PATH.as_posix()}"
SCHEMA_COMPONENT = "core"
SCHEMA_VERSION = 5


def create_db_engine(url: str = DB_URL) -> Engine:
    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {}

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    if url == "sqlite://":
        engine_kwargs["poolclass"] = StaticPool

    return create_engine(url, connect_args=connect_args, **engine_kwargs)


engine = create_db_engine()


def _add_column_if_missing(active_engine: Engine, table_name: str, column_sql: str) -> None:
    inspector = inspect(active_engine)
    column_name = column_sql.split()[0]
    existing = {column["name"] for column in inspector.get_columns(table_name)}
    if column_name in existing:
        return
    with active_engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}"))


def _run_basic_migrations(active_engine: Engine) -> None:
    inspector = inspect(active_engine)
    tables = set(inspector.get_table_names())
    if "applications" in tables:
        _add_column_if_missing(active_engine, "applications", "application_channel TEXT")
        _add_column_if_missing(active_engine, "applications", "stage TEXT")
        _add_column_if_missing(active_engine, "applications", "last_event_at TIMESTAMP")
        _add_column_if_missing(active_engine, "applications", "next_step TEXT")
        _add_column_if_missing(active_engine, "applications", "next_step_due_at TIMESTAMP")
        _add_column_if_missing(active_engine, "applications", "outcome_reason TEXT")
    if "events" in tables:
        _add_column_if_missing(active_engine, "events", "note TEXT")
        _add_column_if_missing(active_engine, "events", "event_at TIMESTAMP")


def init_db(db_engine: Engine | None = None) -> SchemaVersion:
    active_engine = db_engine or engine

    if active_engine.url.drivername == "sqlite" and active_engine.url.database:
        Path(active_engine.url.database).parent.mkdir(parents=True, exist_ok=True)

    SQLModel.metadata.create_all(active_engine)
    _run_basic_migrations(active_engine)

    with Session(active_engine) as session:
        version = session.exec(
            select(SchemaVersion).where(SchemaVersion.component == SCHEMA_COMPONENT)
        ).first()
        if version is None:
            version = SchemaVersion(component=SCHEMA_COMPONENT, version=SCHEMA_VERSION)
        else:
            version.version = SCHEMA_VERSION
        session.add(version)
        session.commit()
        session.refresh(version)
        return version


def get_session(db_engine: Engine | None = None) -> Session:
    return Session(db_engine or engine)
