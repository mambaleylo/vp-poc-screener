"""Версионированные миграции схемы SQLite.

Как это работает:
  * Текущая версия схемы хранится в самой базе: PRAGMA user_version.
  * MIGRATIONS — упорядоченный список шагов. При старте применяются все шаги
    с номером больше текущей версии, каждый в своей транзакции.
  * Перед изменением существующей базы делается копия <база>.<версия>.bak.

Как добавить изменение схемы:
  1. Измените модели в models.py.
  2. Добавьте в конец MIGRATIONS новый шаг с номером на 1 больше,
     содержащий SQL (ALTER TABLE ... / CREATE INDEX ...).
  3. Запустите pytest: test_migrations_match_models сверит результат с моделями.
Уже выпущенные шаги никогда не редактируются.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, text

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Migration:
    version: int
    description: str
    statements: tuple[str, ...]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        description="Начальная схема",
        statements=(
            """
            CREATE TABLE topics (
                id INTEGER NOT NULL PRIMARY KEY,
                key VARCHAR(64) NOT NULL UNIQUE,
                title VARCHAR(200) NOT NULL,
                enabled BOOLEAN NOT NULL
            )
            """,
            """
            CREATE TABLE seed_queries (
                id INTEGER NOT NULL PRIMARY KEY,
                topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
                phrase VARCHAR(300) NOT NULL,
                origin VARCHAR(20) NOT NULL,
                enabled BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL,
                last_scanned_at DATETIME,
                last_result_count INTEGER,
                CONSTRAINT uq_seed_topic_phrase UNIQUE (topic_id, phrase)
            )
            """,
            "CREATE INDEX ix_seed_last_scanned ON seed_queries (enabled, last_scanned_at)",
            """
            CREATE TABLE phrases (
                id INTEGER NOT NULL PRIMARY KEY,
                normalized VARCHAR(300) NOT NULL,
                original VARCHAR(300) NOT NULL,
                group_key VARCHAR(300) NOT NULL,
                is_demo BOOLEAN NOT NULL,
                topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
                first_seen_at DATETIME NOT NULL,
                last_seen_at DATETIME NOT NULL,
                CONSTRAINT uq_phrase_normalized_demo UNIQUE (normalized, is_demo)
            )
            """,
            "CREATE INDEX ix_phrases_group ON phrases (group_key)",
            """
            CREATE TABLE metric_snapshots (
                id INTEGER NOT NULL PRIMARY KEY,
                phrase_id INTEGER NOT NULL REFERENCES phrases(id) ON DELETE CASCADE,
                source VARCHAR(50) NOT NULL,
                region_key VARCHAR(200) NOT NULL,
                devices VARCHAR(50) NOT NULL,
                period_type VARCHAR(20) NOT NULL,
                period_start DATE NOT NULL,
                period_end DATE NOT NULL,
                count INTEGER,
                observed_at DATETIME NOT NULL,
                CONSTRAINT uq_snapshot_period
                    UNIQUE (phrase_id, source, region_key, devices, period_type, period_start)
            )
            """,
            "CREATE INDEX ix_snapshots_lookup "
            "ON metric_snapshots (phrase_id, region_key, period_type)",
            """
            CREATE TABLE scan_runs (
                id INTEGER NOT NULL PRIMARY KEY,
                trigger VARCHAR(20) NOT NULL,
                mode VARCHAR(10) NOT NULL,
                status VARCHAR(20) NOT NULL,
                started_at DATETIME NOT NULL,
                finished_at DATETIME,
                stats_json TEXT,
                error TEXT
            )
            """,
            "CREATE INDEX ix_scan_runs_started ON scan_runs (started_at)",
            "CREATE UNIQUE INDEX ux_scan_runs_one_running ON scan_runs (status) "
            "WHERE status = 'running'",
            """
            CREATE TABLE scores (
                id INTEGER NOT NULL PRIMARY KEY,
                phrase_id INTEGER NOT NULL REFERENCES phrases(id) ON DELETE CASCADE,
                scan_run_id INTEGER REFERENCES scan_runs(id) ON DELETE SET NULL,
                region_key VARCHAR(200) NOT NULL,
                total FLOAT NOT NULL,
                is_preliminary BOOLEAN NOT NULL,
                completeness FLOAT NOT NULL,
                confidence VARCHAR(10) NOT NULL,
                components_json TEXT NOT NULL,
                reasons_json TEXT NOT NULL,
                data_used_json TEXT NOT NULL,
                computed_at DATETIME NOT NULL
            )
            """,
            "CREATE INDEX ix_scores_phrase_time ON scores (phrase_id, computed_at)",
            """
            CREATE TABLE opportunities (
                id INTEGER NOT NULL PRIMARY KEY,
                phrase_id INTEGER NOT NULL REFERENCES phrases(id) ON DELETE CASCADE,
                region_key VARCHAR(200) NOT NULL,
                status VARCHAR(20) NOT NULL,
                status_reason TEXT NOT NULL,
                score_id INTEGER NOT NULL REFERENCES scores(id) ON DELETE CASCADE,
                total FLOAT NOT NULL,
                is_preliminary BOOLEAN NOT NULL,
                first_found_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                last_observed_on DATE,
                CONSTRAINT uq_opportunity_phrase_region UNIQUE (phrase_id, region_key)
            )
            """,
            "CREATE INDEX ix_opportunities_rank ON opportunities (region_key, status, total)",
            """
            CREATE TABLE telegram_users (
                id INTEGER NOT NULL PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                daily_enabled BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL,
                last_seen_at DATETIME
            )
            """,
            """
            CREATE TABLE notifications (
                id INTEGER NOT NULL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES telegram_users(id) ON DELETE CASCADE,
                kind VARCHAR(30) NOT NULL,
                dedupe_key VARCHAR(100) NOT NULL,
                sent_at DATETIME NOT NULL,
                details TEXT,
                CONSTRAINT uq_notification_once UNIQUE (user_id, kind, dedupe_key)
            )
            """,
        ),
    ),
)

LATEST_VERSION = MIGRATIONS[-1].version


def current_version(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("PRAGMA user_version")).scalar_one())


def migrate(engine: Engine, db_file: Path | None = None) -> int:
    """Применяет недостающие миграции. Возвращает итоговую версию схемы."""
    version = current_version(engine)
    if version > LATEST_VERSION:
        raise RuntimeError(
            f"База создана более новой версией программы (схема v{version}, "
            f"эта версия знает до v{LATEST_VERSION}). Обновите код."
        )
    pending = [m for m in MIGRATIONS if m.version > version]
    if not pending:
        return version

    if version > 0 and db_file is not None and db_file.exists():
        backup = db_file.with_name(f"{db_file.name}.v{version}.bak")
        shutil.copy2(db_file, backup)
        log.info("Резервная копия базы перед миграцией: %s", backup)

    for migration in pending:
        log.info("Миграция схемы до v%s: %s", migration.version, migration.description)
        with engine.begin() as conn:
            for statement in migration.statements:
                conn.execute(text(statement))
            # PRAGMA не поддерживает параметры; версия — наше целое число.
            conn.execute(text(f"PRAGMA user_version = {int(migration.version)}"))
    return LATEST_VERSION
