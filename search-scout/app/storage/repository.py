"""Все операции с базой в одном месте.

Методы синхронные и короткие: каждый открывает свою транзакцию. Из
асинхронного кода тяжёлые вызовы выполняются через asyncio.to_thread.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.services.normalizer import NormalizedPhrase
from app.sources.base import Observation
from app.storage.models import (
    MetricSnapshot,
    Notification,
    Opportunity,
    Phrase,
    ScanRun,
    Score,
    SeedQuery,
    TelegramUser,
    Topic,
)
from app.topics import TopicsConfig

CHUNK = 400


class ScanAlreadyRunningError(RuntimeError):
    pass


@dataclass(frozen=True)
class SeedRow:
    id: int
    phrase: str
    topic_key: str


@dataclass(frozen=True)
class PreparedObservation:
    phrase: NormalizedPhrase
    topic_key: str | None
    observation: Observation


@dataclass(frozen=True)
class PhraseRow:
    id: int
    normalized: str
    original: str
    group_key: str
    topic_key: str | None
    first_seen_at: datetime
    last_seen_at: datetime


@dataclass
class PhraseSeries:
    monthly: list[tuple[date, int]] = field(default_factory=list)
    rolling: list[tuple[date, int]] = field(default_factory=list)
    sources: set[str] = field(default_factory=set)
    last_observed_on: date | None = None
    rolling_without_count: int = 0


@dataclass(frozen=True)
class ScoredItem:
    phrase_id: int
    total: float
    is_preliminary: bool
    completeness: float
    confidence: str
    components: dict[str, Any]
    reasons: list[str]
    data_used: dict[str, Any]
    status: str
    status_reason: str
    last_observed_on: date | None


@dataclass(frozen=True)
class OpportunityView:
    phrase_id: int
    original: str
    normalized: str
    group_key: str
    is_demo: bool
    topic_key: str | None
    topic_title: str | None
    region_key: str
    status: str
    status_reason: str
    total: float
    is_preliminary: bool
    completeness: float
    confidence: str
    components: dict[str, Any]
    reasons: list[str]
    data_used: dict[str, Any]
    first_found_at: datetime
    updated_at: datetime
    last_observed_on: date | None


@dataclass(frozen=True)
class ScanRunView:
    id: int
    trigger: str
    mode: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    stats: dict[str, Any]
    error: str | None


@dataclass(frozen=True)
class UserView:
    id: int
    chat_id: int
    daily_enabled: bool


def _chunks(items: list[Any], size: int = CHUNK) -> Iterable[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _run_view(run: ScanRun) -> ScanRunView:
    return ScanRunView(
        id=run.id,
        trigger=run.trigger,
        mode=run.mode,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        stats=json.loads(run.stats_json) if run.stats_json else {},
        error=run.error,
    )


class Repository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    # ================= тематики и сиды =================

    def sync_topics(self, config: TopicsConfig, now: datetime) -> None:
        """Приводит тематики и config-сиды в базе к содержимому topics.toml."""
        with self._sf.begin() as s:
            existing = {t.key: t for t in s.scalars(select(Topic))}
            keys = set()
            for topic_cfg in config.topics:
                keys.add(topic_cfg.key)
                topic = existing.get(topic_cfg.key)
                if topic is None:
                    topic = Topic(key=topic_cfg.key, title=topic_cfg.title, enabled=True)
                    s.add(topic)
                    s.flush()
                else:
                    topic.title = topic_cfg.title
                    topic.enabled = True
                seeds = topic_cfg.all_seeds(config.max_modifiers_per_core)
                current = {
                    q.phrase: q
                    for q in s.scalars(select(SeedQuery).where(SeedQuery.topic_id == topic.id))
                }
                for phrase in seeds:
                    if phrase in current:
                        current[phrase].enabled = True
                    else:
                        s.add(
                            SeedQuery(
                                topic_id=topic.id,
                                phrase=phrase,
                                origin="config",
                                enabled=True,
                                created_at=now,
                            )
                        )
                for phrase, seed in current.items():
                    if seed.origin == "config" and phrase not in seeds:
                        seed.enabled = False
            for key, topic in existing.items():
                if key not in keys:
                    topic.enabled = False

    def pick_seeds(self, limit: int) -> list[SeedRow]:
        """Сиды, которые дольше всех не опрашивались (никогда — в первую очередь)."""
        with self._sf() as s:
            rows = s.execute(
                select(SeedQuery.id, SeedQuery.phrase, Topic.key)
                .join(Topic, Topic.id == SeedQuery.topic_id)
                .where(SeedQuery.enabled.is_(True), Topic.enabled.is_(True))
                .order_by(
                    SeedQuery.last_scanned_at.is_not(None), SeedQuery.last_scanned_at, SeedQuery.id
                )
                .limit(limit)
            ).all()
        return [SeedRow(id=r[0], phrase=r[1], topic_key=r[2]) for r in rows]

    def mark_seed_scanned(self, seed_id: int, when: datetime, result_count: int | None) -> None:
        self.mark_seeds_scanned([(seed_id, result_count)], when)

    def mark_seeds_scanned(self, items: list[tuple[int, int | None]], when: datetime) -> None:
        with self._sf.begin() as s:
            for seed_id, result_count in items:
                s.execute(
                    update(SeedQuery)
                    .where(SeedQuery.id == seed_id)
                    .values(last_scanned_at=when, last_result_count=result_count)
                )

    def add_expansion_seeds(self, items: list[tuple[str, str]], now: datetime) -> int:
        """Добавляет найденные фразы как новые сиды (topic_key, phrase). Возвращает число новых."""
        added = 0
        with self._sf.begin() as s:
            topic_ids = dict(s.execute(select(Topic.key, Topic.id)).all())
            for topic_key, phrase in items:
                topic_id = topic_ids.get(topic_key)
                if topic_id is None:
                    continue
                stmt = (
                    sqlite_insert(SeedQuery)
                    .values(
                        topic_id=topic_id,
                        phrase=phrase,
                        origin="expansion",
                        enabled=True,
                        created_at=now,
                    )
                    .on_conflict_do_nothing()
                )
                added += s.execute(stmt).rowcount or 0
        return added

    def seed_stats(self) -> dict[str, int]:
        with self._sf() as s:
            total = s.scalar(select(func.count()).select_from(SeedQuery).where(SeedQuery.enabled))
            never = s.scalar(
                select(func.count())
                .select_from(SeedQuery)
                .where(SeedQuery.enabled, SeedQuery.last_scanned_at.is_(None))
            )
            expansion = s.scalar(
                select(func.count())
                .select_from(SeedQuery)
                .where(SeedQuery.enabled, SeedQuery.origin == "expansion")
            )
        return {"total": total or 0, "never_scanned": never or 0, "expansion": expansion or 0}

    # ================= фразы и метрики =================

    def store_observations(self, items: list[PreparedObservation], now: datetime) -> dict[str, int]:
        """Сохраняет фразы (без дублей) и снимки метрик (повтор обновляет значение)."""
        stats = {"new_phrases": 0, "snapshots": 0}
        if not items:
            return stats
        with self._sf.begin() as s:
            topic_ids = dict(s.execute(select(Topic.key, Topic.id)).all())
            phrase_ids: dict[tuple[str, bool], int] = {}
            keys = list({(i.phrase.normalized, i.observation.is_demo) for i in items})
            for chunk in _chunks(keys):
                demo_values = {k[1] for k in chunk}
                rows = s.execute(
                    select(Phrase.id, Phrase.normalized, Phrase.is_demo).where(
                        Phrase.normalized.in_([k[0] for k in chunk]),
                        Phrase.is_demo.in_(demo_values),
                    )
                ).all()
                for pid, normalized, is_demo in rows:
                    phrase_ids[(normalized, bool(is_demo))] = pid

            touched: set[int] = set()
            for item in items:
                key = (item.phrase.normalized, item.observation.is_demo)
                topic_id = topic_ids.get(item.topic_key) if item.topic_key else None
                if key not in phrase_ids:
                    phrase = Phrase(
                        normalized=item.phrase.normalized,
                        original=item.phrase.original,
                        group_key=item.phrase.group_key,
                        is_demo=item.observation.is_demo,
                        topic_id=topic_id,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                    s.add(phrase)
                    s.flush()
                    phrase_ids[key] = phrase.id
                    stats["new_phrases"] += 1
                elif phrase_ids[key] not in touched:
                    values: dict[str, Any] = {"last_seen_at": now}
                    s.execute(update(Phrase).where(Phrase.id == phrase_ids[key]).values(**values))
                    if topic_id is not None:
                        s.execute(
                            update(Phrase)
                            .where(Phrase.id == phrase_ids[key], Phrase.topic_id.is_(None))
                            .values(topic_id=topic_id)
                        )
                touched.add(phrase_ids[key])

                obs = item.observation
                stmt = sqlite_insert(MetricSnapshot).values(
                    phrase_id=phrase_ids[key],
                    source=obs.source,
                    region_key=obs.region_key,
                    devices=obs.devices,
                    period_type=obs.period_type,
                    period_start=obs.period_start,
                    period_end=obs.period_end,
                    count=obs.count,
                    observed_at=now,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=[
                        "phrase_id",
                        "source",
                        "region_key",
                        "devices",
                        "period_type",
                        "period_start",
                    ],
                    set_={
                        "count": stmt.excluded.count,
                        "period_end": stmt.excluded.period_end,
                        "observed_at": stmt.excluded.observed_at,
                    },
                )
                s.execute(stmt)
                stats["snapshots"] += 1
        return stats

    def phrases(self, is_demo: bool) -> list[PhraseRow]:
        with self._sf() as s:
            rows = s.execute(
                select(
                    Phrase.id,
                    Phrase.normalized,
                    Phrase.original,
                    Phrase.group_key,
                    Topic.key,
                    Phrase.first_seen_at,
                    Phrase.last_seen_at,
                )
                .outerjoin(Topic, Topic.id == Phrase.topic_id)
                .where(Phrase.is_demo.is_(is_demo))
            ).all()
        return [PhraseRow(*r) for r in rows]

    def series(
        self, phrase_ids: list[int], region_key: str, devices: str, today: date
    ) -> dict[int, PhraseSeries]:
        """История метрик фраз. Для месяцев берутся только полностью прошедшие."""
        result: dict[int, PhraseSeries] = defaultdict(PhraseSeries)
        latest: dict[tuple[int, str, date], tuple[datetime, int]] = {}
        with self._sf() as s:
            for chunk in _chunks(phrase_ids):
                rows = s.execute(
                    select(
                        MetricSnapshot.phrase_id,
                        MetricSnapshot.source,
                        MetricSnapshot.period_type,
                        MetricSnapshot.period_start,
                        MetricSnapshot.period_end,
                        MetricSnapshot.count,
                        MetricSnapshot.observed_at,
                    ).where(
                        MetricSnapshot.phrase_id.in_(chunk),
                        MetricSnapshot.region_key == region_key,
                        MetricSnapshot.devices == devices,
                    )
                ).all()
                for pid, source, ptype, start, end, count, observed_at in rows:
                    item = result[pid]
                    item.sources.add(source)
                    if item.last_observed_on is None or end > item.last_observed_on:
                        item.last_observed_on = min(end, today)
                    if count is None:
                        if ptype == "rolling30":
                            item.rolling_without_count += 1
                        continue
                    if ptype == "month" and end >= today:
                        continue
                    # Если один период есть у нескольких источников — берём свежее наблюдение.
                    key = (pid, ptype, end if ptype == "rolling30" else start)
                    if key not in latest or observed_at > latest[key][0]:
                        latest[key] = (observed_at, count)
        for (pid, ptype, day), (_, count) in latest.items():
            target = result[pid].monthly if ptype == "month" else result[pid].rolling
            target.append((day, count))
        for item in result.values():
            item.monthly.sort()
            item.rolling.sort()
        return dict(result)

    def phrases_needing_dynamics(
        self,
        candidate_ids: list[int],
        region_key: str,
        devices: str,
        source: str,
        fresh_since: datetime,
    ) -> list[int]:
        """Из кандидатов (в порядке приоритета) — те, у кого нет свежей помесячной динамики."""
        fresh: set[int] = set()
        with self._sf() as s:
            for chunk in _chunks(candidate_ids):
                fresh.update(
                    s.scalars(
                        select(MetricSnapshot.phrase_id)
                        .where(
                            MetricSnapshot.phrase_id.in_(chunk),
                            MetricSnapshot.region_key == region_key,
                            MetricSnapshot.devices == devices,
                            MetricSnapshot.source == source,
                            MetricSnapshot.period_type == "month",
                            MetricSnapshot.observed_at >= fresh_since,
                        )
                        .distinct()
                    )
                )
        return [pid for pid in candidate_ids if pid not in fresh]

    # ================= оценки и возможности =================

    def save_scores(
        self, run_id: int | None, region_key: str, items: list[ScoredItem], now: datetime
    ) -> None:
        with self._sf.begin() as s:
            for item in items:
                score = Score(
                    phrase_id=item.phrase_id,
                    scan_run_id=run_id,
                    region_key=region_key,
                    total=item.total,
                    is_preliminary=item.is_preliminary,
                    completeness=item.completeness,
                    confidence=item.confidence,
                    components_json=json.dumps(item.components, ensure_ascii=False),
                    reasons_json=json.dumps(item.reasons, ensure_ascii=False),
                    data_used_json=json.dumps(item.data_used, ensure_ascii=False, default=str),
                    computed_at=now,
                )
                s.add(score)
                s.flush()
                stmt = sqlite_insert(Opportunity).values(
                    phrase_id=item.phrase_id,
                    region_key=region_key,
                    status=item.status,
                    status_reason=item.status_reason,
                    score_id=score.id,
                    total=item.total,
                    is_preliminary=item.is_preliminary,
                    first_found_at=now,
                    updated_at=now,
                    last_observed_on=item.last_observed_on,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["phrase_id", "region_key"],
                    set_={
                        "status": stmt.excluded.status,
                        "status_reason": stmt.excluded.status_reason,
                        "score_id": stmt.excluded.score_id,
                        "total": stmt.excluded.total,
                        "is_preliminary": stmt.excluded.is_preliminary,
                        "updated_at": stmt.excluded.updated_at,
                        "last_observed_on": stmt.excluded.last_observed_on,
                    },
                )
                s.execute(stmt)

    def prune_scores(self, older_than: datetime) -> int:
        """Удаляет старые оценки, кроме тех, на которые ссылаются текущие возможности."""
        with self._sf.begin() as s:
            used = select(Opportunity.score_id)
            result = s.execute(
                delete(Score).where(Score.computed_at < older_than, Score.id.not_in(used))
            )
            return result.rowcount or 0

    def list_opportunities(
        self,
        region_key: str,
        is_demo: bool,
        statuses: tuple[str, ...],
        limit: int | None = None,
    ) -> list[OpportunityView]:
        with self._sf() as s:
            query = (
                select(Opportunity, Phrase, Score, Topic)
                .join(Phrase, Phrase.id == Opportunity.phrase_id)
                .join(Score, Score.id == Opportunity.score_id)
                .outerjoin(Topic, Topic.id == Phrase.topic_id)
                .where(
                    Opportunity.region_key == region_key,
                    Phrase.is_demo.is_(is_demo),
                    Opportunity.status.in_(statuses),
                )
                .order_by(Opportunity.total.desc(), Phrase.id)
            )
            if limit:
                query = query.limit(limit)
            rows = s.execute(query).all()
        return [
            OpportunityView(
                phrase_id=phrase.id,
                original=phrase.original,
                normalized=phrase.normalized,
                group_key=phrase.group_key,
                is_demo=phrase.is_demo,
                topic_key=topic.key if topic else None,
                topic_title=topic.title if topic else None,
                region_key=opp.region_key,
                status=opp.status,
                status_reason=opp.status_reason,
                total=opp.total,
                is_preliminary=opp.is_preliminary,
                completeness=score.completeness,
                confidence=score.confidence,
                components=json.loads(score.components_json),
                reasons=json.loads(score.reasons_json),
                data_used=json.loads(score.data_used_json),
                first_found_at=opp.first_found_at,
                updated_at=opp.updated_at,
                last_observed_on=opp.last_observed_on,
            )
            for opp, phrase, score, topic in rows
        ]

    def opportunity_counts(self, region_key: str, is_demo: bool) -> dict[str, int]:
        with self._sf() as s:
            rows = s.execute(
                select(Opportunity.status, func.count())
                .join(Phrase, Phrase.id == Opportunity.phrase_id)
                .where(Opportunity.region_key == region_key, Phrase.is_demo.is_(is_demo))
                .group_by(Opportunity.status)
            ).all()
        return {status: count for status, count in rows}

    def phrase_count(self, is_demo: bool) -> int:
        with self._sf() as s:
            return (
                s.scalar(
                    select(func.count()).select_from(Phrase).where(Phrase.is_demo.is_(is_demo))
                )
                or 0
            )

    # ================= запуски сканирования =================

    def start_scan_run(self, trigger: str, mode: str, now: datetime, stale_minutes: int) -> int:
        stale_before = now - timedelta(minutes=stale_minutes)
        try:
            with self._sf.begin() as s:
                s.execute(
                    update(ScanRun)
                    .where(ScanRun.status == "running", ScanRun.started_at < stale_before)
                    .values(
                        status="interrupted",
                        finished_at=now,
                        error="не завершено (сбой или перезапуск)",
                    )
                )
                run = ScanRun(trigger=trigger, mode=mode, status="running", started_at=now)
                s.add(run)
                s.flush()
                return run.id
        except IntegrityError as exc:
            raise ScanAlreadyRunningError("Сканирование уже выполняется") from exc

    def finish_scan_run(
        self, run_id: int, status: str, stats: dict[str, Any], error: str | None, now: datetime
    ) -> None:
        with self._sf.begin() as s:
            s.execute(
                update(ScanRun)
                .where(ScanRun.id == run_id)
                .values(
                    status=status,
                    finished_at=now,
                    stats_json=json.dumps(stats, ensure_ascii=False, default=str),
                    error=error[:2000] if error else None,
                )
            )

    def interrupt_running_runs(self, now: datetime) -> int:
        """При старте бота: незавершённые запуски этого процесса считаем прерванными."""
        with self._sf.begin() as s:
            result = s.execute(
                update(ScanRun)
                .where(ScanRun.status == "running")
                .values(status="interrupted", finished_at=now, error="прервано перезапуском")
            )
            return result.rowcount or 0

    def last_scan_run(self, finished: bool = False) -> ScanRunView | None:
        with self._sf() as s:
            query = select(ScanRun).order_by(ScanRun.started_at.desc(), ScanRun.id.desc()).limit(1)
            if finished:
                query = query.where(ScanRun.status.in_(("success", "partial")))
            run = s.scalar(query)
            return _run_view(run) if run else None

    def scheduled_scan_done_on(self, local_day: date, tz: ZoneInfo) -> bool:
        start = datetime.combine(local_day, datetime.min.time(), tz).astimezone(UTC)
        end = start + timedelta(days=1)
        with self._sf() as s:
            return bool(
                s.scalar(
                    select(func.count())
                    .select_from(ScanRun)
                    .where(
                        ScanRun.trigger == "scheduled",
                        ScanRun.status.in_(("success", "partial")),
                        and_(ScanRun.started_at >= start, ScanRun.started_at < end),
                    )
                )
            )

    # ================= пользователи и уведомления =================

    def ensure_user(
        self, user_id: int, chat_id: int, daily_default: bool, now: datetime
    ) -> UserView:
        with self._sf.begin() as s:
            user = s.get(TelegramUser, user_id)
            if user is None:
                user = TelegramUser(
                    id=user_id, chat_id=chat_id, daily_enabled=daily_default, created_at=now
                )
                s.add(user)
            else:
                user.chat_id = chat_id
            user.last_seen_at = now
            s.flush()
            return UserView(id=user.id, chat_id=user.chat_id, daily_enabled=user.daily_enabled)

    def register_allowed_users(
        self, user_ids: list[int], daily_default: bool, now: datetime
    ) -> None:
        """Создаёт записи для разрешённых пользователей, чтобы ежедневный отчёт
        приходил даже до первого /start (в личном чате chat_id = user_id)."""
        with self._sf.begin() as s:
            for uid in user_ids:
                s.execute(
                    sqlite_insert(TelegramUser)
                    .values(id=uid, chat_id=uid, daily_enabled=daily_default, created_at=now)
                    .on_conflict_do_nothing()
                )

    def get_user(self, user_id: int) -> UserView | None:
        with self._sf() as s:
            user = s.get(TelegramUser, user_id)
            return UserView(user.id, user.chat_id, user.daily_enabled) if user else None

    def set_daily(self, user_id: int, enabled: bool) -> None:
        with self._sf.begin() as s:
            s.execute(
                update(TelegramUser).where(TelegramUser.id == user_id).values(daily_enabled=enabled)
            )

    def daily_users(self, allowed_ids: list[int]) -> list[UserView]:
        """Пользователи с включённым ежедневным отчётом — только из списка разрешённых."""
        if not allowed_ids:
            return []
        with self._sf() as s:
            users = s.scalars(
                select(TelegramUser).where(
                    TelegramUser.daily_enabled.is_(True), TelegramUser.id.in_(allowed_ids)
                )
            ).all()
            return [UserView(u.id, u.chat_id, u.daily_enabled) for u in users]

    def reserve_notification(self, user_id: int, kind: str, key: str, now: datetime) -> bool:
        """Атомарно «занимает» уведомление. False — оно уже отправлялось."""
        with self._sf.begin() as s:
            result = s.execute(
                sqlite_insert(Notification)
                .values(user_id=user_id, kind=kind, dedupe_key=key, sent_at=now)
                .on_conflict_do_nothing()
            )
            return (result.rowcount or 0) == 1

    def release_notification(self, user_id: int, kind: str, key: str) -> None:
        """Отменяет резерв, если отправка не удалась — тогда уведомление уйдёт позже."""
        with self._sf.begin() as s:
            s.execute(
                delete(Notification).where(
                    Notification.user_id == user_id,
                    Notification.kind == kind,
                    Notification.dedupe_key == key,
                )
            )

    def notification_sent(self, user_id: int, kind: str, key: str) -> bool:
        with self._sf() as s:
            return bool(
                s.scalar(
                    select(func.count())
                    .select_from(Notification)
                    .where(
                        Notification.user_id == user_id,
                        Notification.kind == kind,
                        Notification.dedupe_key == key,
                    )
                )
            )

    def last_notification(self, kind: str) -> datetime | None:
        with self._sf() as s:
            return s.scalar(select(func.max(Notification.sent_at)).where(Notification.kind == kind))

    def has_any(self, is_demo: bool | None = None) -> bool:
        with self._sf() as s:
            query = select(Phrase.id).limit(1)
            if is_demo is not None:
                query = query.where(or_(Phrase.is_demo.is_(is_demo)))
            return s.scalar(query) is not None
