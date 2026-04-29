from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _ensure_sqlite_columns()


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def _ensure_sqlite_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    additions = {
        "activity": [
            ("sport_variant", "VARCHAR DEFAULT 'other' NOT NULL"),
            ("gear_id", "VARCHAR"),
        ],
        "plannedworkout": [
            ("sport_variant", "VARCHAR DEFAULT 'other' NOT NULL"),
            ("surface", "VARCHAR"),
            ("location_suggestion", "VARCHAR"),
            ("gear_suggestion", "VARCHAR"),
        ],
    }
    with engine.begin() as connection:
        for table, columns in additions.items():
            existing = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")}
            for name, ddl in columns:
                if name not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
