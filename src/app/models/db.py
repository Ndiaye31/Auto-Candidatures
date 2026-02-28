from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.models.tables import SchemaVersion

DB_PATH = Path("data/app.db")
DB_URL = f"sqlite:///{DB_PATH.as_posix()}"
SCHEMA_COMPONENT = "core"
SCHEMA_VERSION = 1


def create_db_engine(url: str = DB_URL) -> Engine:
    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {}

    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    if url == "sqlite://":
        engine_kwargs["poolclass"] = StaticPool

    return create_engine(url, connect_args=connect_args, **engine_kwargs)


engine = create_db_engine()


def init_db(db_engine: Engine | None = None) -> SchemaVersion:
    active_engine = db_engine or engine

    if active_engine.url.drivername == "sqlite" and active_engine.url.database:
        Path(active_engine.url.database).parent.mkdir(parents=True, exist_ok=True)

    SQLModel.metadata.create_all(active_engine)

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
