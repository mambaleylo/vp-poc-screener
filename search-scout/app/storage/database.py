"""Подключение к SQLite."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.storage.migrations import migrate


def create_db_engine(db_file: Path | str) -> Engine:
    """Создаёт engine для SQLite-файла (или ':memory:' в тестах)."""
    extra: dict[str, object] = {}
    if str(db_file) == ":memory:":
        url = "sqlite://"
        # Одна общая in-memory база для всех потоков (используется в тестах).
        extra["poolclass"] = StaticPool
    else:
        path = Path(db_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{path}"

    engine = create_engine(
        url,
        # Бот вызывает базу из разных потоков (asyncio.to_thread); каждая
        # операция берёт своё соединение из пула, поэтому это безопасно.
        connect_args={"check_same_thread": False, "timeout": 30},
        **extra,
    )

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
        # Отключаем «умное» управление транзакциями модуля sqlite3, чтобы
        # BEGIN выдавал SQLAlchemy (рецепт из документации SQLAlchemy).
        # Иначе DDL в миграциях выполнялся бы вне транзакции.
        dbapi_conn.isolation_level = None
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA busy_timeout = 30000")
        if url != "sqlite://":
            # WAL позволяет читать базу, пока идёт запись (бот + CLI).
            cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn) -> None:  # type: ignore[no-untyped-def]
        conn.exec_driver_sql("BEGIN")

    return engine


def init_database(db_file: Path | str) -> tuple[Engine, sessionmaker[Session]]:
    """Создаёт engine, применяет миграции и возвращает фабрику сессий."""
    engine = create_db_engine(db_file)
    migrate(engine, Path(db_file) if str(db_file) != ":memory:" else None)
    return engine, sessionmaker(engine, expire_on_commit=False)
