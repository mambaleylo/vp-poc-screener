"""Таблицы базы данных (SQLAlchemy 2.x).

Схема создаётся не из этих классов, а миграциями в migrations.py — так
изменения структуры базы версионируются. Тест tests/test_storage.py
проверяет, что модели и миграции описывают одни и те же таблицы и колонки.

Назначение таблиц:
  topics            — тематики из config/topics.toml
  seed_queries      — стартовые фразы для источников (+ найденные при расширении)
  phrases           — уникальные поисковые фразы; демо и реальные хранятся раздельно
  metric_snapshots  — частотность фразы за период (месяц или «последние 30 дней»)
  scan_runs         — журнал запусков сканирования
  scores            — история оценок с компонентами и причинами
  opportunities     — текущее состояние фразы: top / watch (наблюдение) / rejected
  telegram_users    — пользователи бота и их настройки
  notifications     — отправленные уведомления (защита от повторной отправки)
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class UTCDateTime(TypeDecorator[datetime]):
    """Дата-время, которое всегда хранится в UTC и читается как aware-datetime.

    SQLite не хранит часовой пояс, поэтому приводим всё к UTC при записи и
    добавляем tzinfo=UTC при чтении. Наивные datetime запрещены, чтобы
    случайно не записать локальное время.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Ожидается datetime с часовым поясом (используйте UTC)")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class SeedQuery(Base):
    __tablename__ = "seed_queries"
    __table_args__ = (
        UniqueConstraint("topic_id", "phrase", name="uq_seed_topic_phrase"),
        Index("ix_seed_last_scanned", "enabled", "last_scanned_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    phrase: Mapped[str] = mapped_column(String(300))
    origin: Mapped[str] = mapped_column(String(20))  # config | expansion
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_scanned_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    last_result_count: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Phrase(Base):
    __tablename__ = "phrases"
    __table_args__ = (
        UniqueConstraint("normalized", "is_demo", name="uq_phrase_normalized_demo"),
        Index("ix_phrases_group", "group_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    normalized: Mapped[str] = mapped_column(String(300))
    original: Mapped[str] = mapped_column(String(300))
    group_key: Mapped[str] = mapped_column(String(300))
    # Демо-данные никогда не смешиваются с реальными: это разные строки.
    is_demo: Mapped[bool] = mapped_column(Boolean)
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime)


class MetricSnapshot(Base):
    __tablename__ = "metric_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "phrase_id",
            "source",
            "region_key",
            "devices",
            "period_type",
            "period_start",
            name="uq_snapshot_period",
        ),
        Index("ix_snapshots_lookup", "phrase_id", "region_key", "period_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phrase_id: Mapped[int] = mapped_column(ForeignKey("phrases.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(50))
    region_key: Mapped[str] = mapped_column(String(200))
    devices: Mapped[str] = mapped_column(String(50))
    # month — календарный месяц; rolling30 — «последние 30 дней» на дату наблюдения
    period_type: Mapped[str] = mapped_column(String(20))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    count: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = нет данных
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime)


class ScanRun(Base):
    __tablename__ = "scan_runs"
    __table_args__ = (
        Index("ix_scan_runs_started", "started_at"),
        # Не более одного выполняющегося сканирования — гарантирует сама база,
        # даже если сканирование запущено из второго процесса (CLI).
        Index(
            "ux_scan_runs_one_running",
            "status",
            unique=True,
            sqlite_where=text("status = 'running'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(20))  # manual | scheduled | cli
    mode: Mapped[str] = mapped_column(String(10))  # demo | live
    status: Mapped[str] = mapped_column(String(20))  # running|success|partial|failed|interrupted
    started_at: Mapped[datetime] = mapped_column(UTCDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    stats_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Score(Base):
    __tablename__ = "scores"
    __table_args__ = (Index("ix_scores_phrase_time", "phrase_id", "computed_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phrase_id: Mapped[int] = mapped_column(ForeignKey("phrases.id", ondelete="CASCADE"))
    scan_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("scan_runs.id", ondelete="SET NULL"), nullable=True
    )
    region_key: Mapped[str] = mapped_column(String(200))
    total: Mapped[float] = mapped_column(Float)
    is_preliminary: Mapped[bool] = mapped_column(Boolean)
    completeness: Mapped[float] = mapped_column(Float)  # доля весов с реальными данными, 0..1
    confidence: Mapped[str] = mapped_column(String(10))  # low | medium | high
    components_json: Mapped[str] = mapped_column(Text)
    reasons_json: Mapped[str] = mapped_column(Text)
    data_used_json: Mapped[str] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime)


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint("phrase_id", "region_key", name="uq_opportunity_phrase_region"),
        Index("ix_opportunities_rank", "region_key", "status", "total"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phrase_id: Mapped[int] = mapped_column(ForeignKey("phrases.id", ondelete="CASCADE"))
    region_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20))  # top | watch | rejected
    status_reason: Mapped[str] = mapped_column(Text)
    score_id: Mapped[int] = mapped_column(ForeignKey("scores.id", ondelete="CASCADE"))
    total: Mapped[float] = mapped_column(Float)
    is_preliminary: Mapped[bool] = mapped_column(Boolean)
    first_found_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_observed_on: Mapped[date | None] = mapped_column(Date, nullable=True)


class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    chat_id: Mapped[int] = mapped_column(Integer)
    daily_enabled: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "dedupe_key", name="uq_notification_once"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("telegram_users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30))
    dedupe_key: Mapped[str] = mapped_column(String(100))
    sent_at: Mapped[datetime] = mapped_column(UTCDateTime)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
