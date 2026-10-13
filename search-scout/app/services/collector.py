"""Сканирование: сбор → нормализация → отбор по тематикам → хранение →
динамика → оценка → отбор возможностей → расширение сидов.

Live-режим (Wordstat):
  1. Берём сиды, которые дольше всех не опрашивались (бюджет запросов на скан
     ограничен: WORDSTAT_MAX_REQUESTS_PER_SCAN, из них часть — на динамику).
  2. topRequests по каждому сиду: сам сид + похожие запросы, частотность за 30 дней.
  3. Фразы нормализуются; не подходящие ни под одну тематику или из стоп-списка
     отбрасываются; дубликаты объединяются.
  4. Предварительная оценка всех фраз. Лучшим кандидатам без свежей истории
     запрашивается помесячная динамика (dynamics).
  5. Итоговая оценка, статусы top/watch/rejected, история оценок.
  6. Лучшие короткие фразы из топа становятся новыми сидами (расширение).

Demo-режим: то же, но данные берутся из CSV (помечены как тестовые), а
сетевых запросов нет.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from app.config import Mode, Settings
from app.services.intent import analyze_intent
from app.services.normalizer import prepare
from app.services.scorer import SelectionParams, score_phrase, select_status
from app.services.trend import TrendParams, analyze
from app.sources.base import (
    BatchSource,
    Observation,
    QuerySource,
    SourceAuthError,
    SourceError,
)
from app.storage.repository import (
    PreparedObservation,
    Repository,
    ScanAlreadyRunningError,
    ScoredItem,
)
from app.topics import TopicsConfig

log = logging.getLogger(__name__)

SCORE_RETENTION_DAYS = 180


@dataclass
class ScanSummary:
    run_id: int
    mode: str  # demo | live | csv (импорт реального CSV)
    status: str  # success | partial | failed
    stats: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0


def prepare_observations(
    observations: list[Observation], topics: TopicsConfig
) -> tuple[list[PreparedObservation], Counter[str]]:
    """Нормализация + отбор по тематикам. Возвращает подходящие и счётчик отказов."""
    rejected: Counter[str] = Counter()
    prepared: list[PreparedObservation] = []
    for obs in observations:
        phrase = prepare(obs.phrase)
        if phrase is None:
            rejected["пустая фраза"] += 1
            continue
        if topics.is_excluded(phrase.normalized):
            rejected["стоп-слово"] += 1
            continue
        topic = topics.classify(phrase.normalized, obs.topic_key)
        if topic is None:
            rejected["вне тематик"] += 1
            continue
        prepared.append(PreparedObservation(phrase=phrase, topic_key=topic.key, observation=obs))
    return prepared, rejected


class ScanService:
    def __init__(
        self,
        settings: Settings,
        repo: Repository,
        topics: TopicsConfig,
        *,
        query_source_factory: Callable[[], QuerySource] | None = None,
        batch_source_factory: Callable[[Mode], BatchSource | None] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.settings = settings
        self.repo = repo
        self.topics = topics
        self._query_source_factory = query_source_factory
        self._batch_source_factory = batch_source_factory
        self._clock = clock
        self._lock = asyncio.Lock()
        self.trend_params = TrendParams(min_volume=settings.min_monthly_volume)
        self.selection_params = SelectionParams(top_min_score=settings.top_min_score)

    @property
    def is_running(self) -> bool:
        return self._lock.locked()

    async def wait_idle(self) -> None:
        async with self._lock:
            pass

    async def run(self, trigger: str) -> ScanSummary:
        """Один запуск сканирования. Параллельный второй запуск отклоняется."""
        if self._lock.locked():
            raise ScanAlreadyRunningError("Сканирование уже выполняется")
        async with self._lock:
            mode = self.settings.resolve_mode()  # ModeUnavailableError — до записи в журнал
            started = time.monotonic()
            now = self._clock()
            run_id = await asyncio.to_thread(
                self.repo.start_scan_run, trigger, mode, now, self.settings.scan_stale_minutes
            )
            summary = ScanSummary(run_id=run_id, mode=mode, status="success")
            try:
                if mode == "live":
                    await self._collect_live(summary)
                else:
                    await self._import_batch(summary, mode)
                await self._score_all(summary, is_demo=self.settings.dataset_is_demo(mode))
                if mode == "live":
                    await self._expand(summary)
                await asyncio.to_thread(
                    self.repo.prune_scores, self._clock() - timedelta(days=SCORE_RETENTION_DAYS)
                )
                if summary.errors and summary.status == "success":
                    summary.status = "partial"
            except Exception as exc:
                summary.status = "failed"
                summary.errors.append(str(exc))
                log.exception("Сканирование #%s завершилось ошибкой", run_id)
            summary.duration_s = round(time.monotonic() - started, 1)
            summary.stats["errors"] = summary.errors[:20]
            await asyncio.to_thread(
                self.repo.finish_scan_run,
                run_id,
                summary.status,
                summary.stats,
                "; ".join(summary.errors[:5]) or None,
                self._clock(),
            )
            log.info(
                "Сканирование #%s (%s, %s): %s за %.1f с",
                run_id,
                mode,
                trigger,
                summary.status,
                summary.duration_s,
            )
            return summary

    async def import_observations(
        self, observations: list[Observation], *, is_demo: bool, trigger: str = "import"
    ) -> ScanSummary:
        """Сохраняет наблюдения (например, из присланного CSV) и пересчитывает рейтинг
        этого набора данных без запросов к API."""
        if self._lock.locked():
            raise ScanAlreadyRunningError("Сканирование уже выполняется")
        async with self._lock:
            mode = "demo" if is_demo else "csv"
            started = time.monotonic()
            run_id = await asyncio.to_thread(
                self.repo.start_scan_run,
                trigger,
                mode,
                self._clock(),
                self.settings.scan_stale_minutes,
            )
            summary = ScanSummary(run_id=run_id, mode=mode, status="success")
            try:
                await self._store(observations, summary)
                await self._score_all(summary, is_demo=is_demo)
            except Exception as exc:
                summary.status = "failed"
                summary.errors.append(str(exc))
                log.exception("Импорт #%s завершился ошибкой", run_id)
            summary.duration_s = round(time.monotonic() - started, 1)
            await asyncio.to_thread(
                self.repo.finish_scan_run,
                run_id,
                summary.status,
                summary.stats,
                "; ".join(summary.errors[:5]) or None,
                self._clock(),
            )
            return summary

    # ---------------- сбор ----------------

    async def _store(self, observations: list[Observation], summary: ScanSummary) -> None:
        prepared, rejected = prepare_observations(observations, self.topics)
        stored = await asyncio.to_thread(self.repo.store_observations, prepared, self._clock())
        stats = summary.stats
        stats["observations"] = stats.get("observations", 0) + len(observations)
        stats["relevant"] = stats.get("relevant", 0) + len(prepared)
        stats["new_phrases"] = stats.get("new_phrases", 0) + stored["new_phrases"]
        filtered = stats.setdefault("filtered", {})
        for reason, count in rejected.items():
            filtered[reason] = filtered.get(reason, 0) + count

    async def _import_batch(self, summary: ScanSummary, mode: Mode) -> None:
        source = self._batch_source_factory(mode) if self._batch_source_factory else None
        if source is None:
            summary.stats["batch"] = "CSV-источник не настроен"
            return
        result = await asyncio.to_thread(source.load)
        summary.stats["csv_rows"] = result.rows_total
        if result.errors:
            summary.stats["csv_errors"] = result.errors[:20]
            summary.errors.extend(f"CSV: {e}" for e in result.errors[:5])
        await self._store(result.observations, summary)

    async def _collect_live(self, summary: ScanSummary) -> None:
        if self._query_source_factory is None:
            raise RuntimeError("Live-источник не подключён")
        source = self._query_source_factory()
        try:
            # Реальный CSV (ручные выгрузки) можно импортировать и в Live-режиме.
            if self._batch_source_factory:
                batch = self._batch_source_factory("live")
                if batch is not None:
                    result = await asyncio.to_thread(batch.load)
                    if result.errors:
                        summary.errors.extend(f"CSV: {e}" for e in result.errors[:5])
                    await self._store(result.observations, summary)

            budget = self.settings.wordstat_max_requests_per_scan
            dynamics_budget = min(self.settings.wordstat_dynamics_per_scan, budget - 1)
            seeds = await asyncio.to_thread(self.repo.pick_seeds, max(1, budget - dynamics_budget))
            summary.stats["seeds_requested"] = len(seeds)

            # Запросы идут параллельно (лимит частоты и параллельности — внутри
            # источника), а запись в базу — одной операцией после сбора.
            results = await asyncio.gather(
                *(source.related(s.phrase, s.topic_key) for s in seeds), return_exceptions=True
            )
            collected: list[Observation] = []
            scanned: list[tuple[int, int]] = []
            failed = 0
            for seed, result in zip(seeds, results, strict=True):
                if isinstance(result, SourceAuthError):
                    raise result  # ключ/права — дальше нет смысла
                if isinstance(result, BaseException):
                    # Сид не отмечаем опрошенным — в следующий раз он будет первым.
                    failed += 1
                    summary.errors.append(f"сид «{seed.phrase}»: {result}")
                    if not isinstance(result, SourceError):
                        log.error("Ошибка при запросе сида", exc_info=result)
                    continue
                collected.extend(result)
                scanned.append((seed.id, len(result)))
            await asyncio.to_thread(self.repo.mark_seeds_scanned, scanned, self._clock())
            summary.stats["seeds_failed"] = failed
            if seeds and failed == len(seeds):
                raise SourceError("все запросы к источнику завершились ошибкой")
            await self._store(collected, summary)

            if source.supports_dynamics and dynamics_budget > 0:
                await self._enrich_dynamics(source, summary, dynamics_budget)
            summary.stats["api_requests"] = getattr(source, "requests_made", None)
        finally:
            await source.aclose()

    async def _enrich_dynamics(self, source: QuerySource, summary: ScanSummary, limit: int) -> None:
        """Запрашивает помесячную динамику для лучших кандидатов без свежей истории."""
        preliminary = await asyncio.to_thread(self._compute_scores, False)
        # Динамику тратим только на фразы, которые могут попасть в топ или наблюдение.
        ranked = sorted(
            (item for item in preliminary if item.status in ("top", "watch")),
            key=lambda item: item.total,
            reverse=True,
        )
        fresh_since = self._clock() - timedelta(days=self.settings.dynamics_refresh_days)
        candidates = await asyncio.to_thread(
            self.repo.phrases_needing_dynamics,
            [item.phrase_id for item in ranked],
            self.settings.region_key,
            self.settings.devices_key,
            source.name,
            fresh_since,
        )
        phrases = {p.id: p for p in await asyncio.to_thread(self.repo.phrases, False)}
        chosen = [phrases[pid] for pid in candidates[:limit] if pid in phrases]

        async def fetch(normalized: str) -> list[Observation]:
            return await source.monthly_dynamics(normalized)

        results = await asyncio.gather(
            *(fetch(p.normalized) for p in chosen), return_exceptions=True
        )
        collected: list[Observation] = []
        for phrase, result in zip(chosen, results, strict=True):
            if isinstance(result, SourceAuthError):
                raise result
            if isinstance(result, BaseException):
                summary.errors.append(f"динамика «{phrase.normalized}»: {result}")
                continue
            collected.extend(
                Observation(**{**asdict(o), "topic_key": phrase.topic_key}) for o in result
            )
        summary.stats["dynamics_requested"] = len(chosen)
        await self._store(collected, summary)

    # ---------------- оценка ----------------

    def _compute_scores(self, is_demo: bool) -> list[ScoredItem]:
        now = self._clock()
        today = now.date()
        settings = self.settings
        phrases = self.repo.phrases(is_demo)
        series = self.repo.series(
            [p.id for p in phrases], settings.region_key, settings.devices_key, today
        )
        items = []
        for phrase in phrases:
            history = series.get(phrase.id)
            if history is None:
                continue  # нет наблюдений для текущего региона/устройств
            intent = analyze_intent(phrase.normalized)
            trend = analyze(history.monthly, history.rolling, self.trend_params)
            score = score_phrase(
                intent=intent,
                trend=trend,
                first_seen_at=phrase.first_seen_at,
                now=now,
                weights=settings.weights,
                novelty_decay_days=settings.novelty_decay_days,
            )
            status, reason = select_status(score, trend, self.selection_params)
            latest = _latest_count(history.monthly, history.rolling)
            data_used = {
                "sources": sorted(history.sources),
                "region_key": settings.region_key,
                "devices": settings.devices_key,
                "intent": intent.intent.value,
                "monthly_points": len(history.monthly),
                "rolling_points": len(history.rolling),
                "latest_count": latest[0] if latest else None,
                "latest_period": latest[1] if latest else None,
                "trend": {
                    "status": trend.status,
                    "basis": trend.basis,
                    "growth_ratio": trend.growth_ratio,
                    "recent_avg": trend.recent_avg,
                    "previous_avg": trend.previous_avg,
                    "window": trend.window_label,
                    "spike": trend.spike,
                    "seasonal": trend.seasonal,
                    "yoy_ratio": trend.yoy_ratio,
                    "months": trend.months_available,
                },
                "problem_score": intent.problem_score,
                "commercial_score": intent.commercial_score,
            }
            items.append(
                ScoredItem(
                    phrase_id=phrase.id,
                    total=score.total,
                    is_preliminary=score.is_preliminary,
                    completeness=score.completeness,
                    confidence=score.confidence,
                    components={k: asdict(c) for k, c in score.components.items()},
                    reasons=score.reasons,
                    data_used=data_used,
                    status=status,
                    status_reason=reason,
                    last_observed_on=history.last_observed_on,
                )
            )
        return items

    async def _score_all(self, summary: ScanSummary, is_demo: bool) -> None:
        items = await asyncio.to_thread(self._compute_scores, is_demo)
        await asyncio.to_thread(
            self.repo.save_scores, summary.run_id, self.settings.region_key, items, self._clock()
        )
        statuses = Counter(item.status for item in items)
        summary.stats["scored"] = len(items)
        summary.stats["top"] = statuses.get("top", 0)
        summary.stats["watch"] = statuses.get("watch", 0)
        summary.stats["rejected"] = statuses.get("rejected", 0)

    async def _expand(self, summary: ScanSummary) -> None:
        """Лучшие короткие фразы из топа становятся сидами следующих сканирований."""
        limit = self.settings.expansion_per_scan
        if limit <= 0:
            return
        top = await asyncio.to_thread(
            self.repo.list_opportunities, self.settings.region_key, False, ("top",), limit * 4
        )
        candidates = [
            (o.topic_key, o.normalized)
            for o in top
            if o.topic_key and 2 <= len(o.normalized.split()) <= 4
        ][:limit]
        added = await asyncio.to_thread(self.repo.add_expansion_seeds, candidates, self._clock())
        summary.stats["expansion_seeds_added"] = added


def _latest_count(
    monthly: list[tuple[date, int]], rolling: list[tuple[date, int]]
) -> tuple[int, str] | None:
    """Самое свежее значение частотности с подписью периода."""
    options = []
    if rolling:
        day, count = rolling[-1]
        options.append((day, count, f"30 дней на {day:%d.%m.%Y}"))
    if monthly:
        day, count = monthly[-1]
        options.append((day, count, f"за {day:%m.%Y}"))
    if not options:
        return None
    _, count, label = max(options, key=lambda o: o[0])
    return count, label
