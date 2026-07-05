"""SQLAlchemy engine/session management. DOCUMENT.md §5, §6.

Single-host SQLite. `Database` owns one engine and a session factory;
`session()` is a context manager committing on success and rolling back on
exception, so repositories never leak a half-written transaction.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from cocoon.persistence.models import Base


class Database:
    def __init__(self, url: str) -> None:
        self._url = url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self._engine = create_engine(url, future=True, connect_args=connect_args)
        self._session_factory = sessionmaker(
            bind=self._engine, expire_on_commit=False, class_=Session
        )

    @property
    def url(self) -> str:
        return self._url

    @property
    def engine(self):
        return self._engine

    def create_all(self) -> None:
        Base.metadata.create_all(self._engine)

    def drop_all(self) -> None:
        Base.metadata.drop_all(self._engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def get_database(db_path: str | Path) -> Database:
    path = Path(db_path)
    if path.suffix != "" or not str(db_path).startswith("sqlite"):
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{path}"
    else:
        url = str(db_path)
    db = Database(url)
    db.create_all()
    return db
