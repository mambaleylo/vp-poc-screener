"""Итоговый рейтинг возможности (0..100) из объяснимых компонентов.

Компоненты (каждый уже нормализован в 0..100 ДО применения весов):
  trend       — динамика спроса (trend.py); может отсутствовать
  commercial  — коммерческое намерение (intent.py)
  problem     — выраженность проблемы (intent.py)
  novelty     — новизна для нашей базы: 100 в день первого появления,
                линейно до 0 за novelty_decay_days

Если компонента нет (например, нет истории для динамики), фиктивное
значение НЕ подставляется: итог считается как средневзвешенное по
доступным компонентам, а рейтинг помечается как предварительный.
completeness — доля суммарного веса, для которой были реальные данные.

Это эвристика для сортировки гипотез, а не вероятность успеха продукта.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.services.intent import IntentResult
from app.services.trend import TrendResult

Status = Literal["top", "watch", "rejected"]
Confidence = Literal["low", "medium", "high"]

CONFIDENCE_LABELS = {"low": "низкая", "medium": "средняя", "high": "высокая"}


@dataclass
class Component:
    value: float | None
    weight: float
    status: str  # ok | missing | ...
    note: str


@dataclass
class ScoreResult:
    total: float
    is_preliminary: bool
    completeness: float
    confidence: Confidence
    components: dict[str, Component]
    reasons: list[str] = field(default_factory=list)


def novelty_score(first_seen_at: datetime, now: datetime, decay_days: int) -> float:
    age_days = max(0.0, (now - first_seen_at).total_seconds() / 86400)
    return round(max(0.0, 100.0 * (1 - age_days / decay_days)), 1)


def combine(components: dict[str, Component]) -> tuple[float, float]:
    """Средневзвешенное по доступным компонентам и доля веса с данными."""
    total_weight = sum(c.weight for c in components.values())
    available = {k: c for k, c in components.items() if c.value is not None and c.weight > 0}
    available_weight = sum(c.weight for c in available.values())
    if available_weight == 0:
        return 0.0, 0.0
    total = sum(c.value * c.weight for c in available.values()) / available_weight  # type: ignore[operator]
    return round(total, 1), round(available_weight / total_weight, 3)


def score_phrase(
    *,
    intent: IntentResult,
    trend: TrendResult,
    first_seen_at: datetime,
    now: datetime,
    weights: dict[str, float],
    novelty_decay_days: int,
) -> ScoreResult:
    age_days = int((now - first_seen_at).total_seconds() // 86400)
    components = {
        "trend": Component(
            value=trend.score if trend.status == "ok" else None,
            weight=weights["trend"],
            status=trend.status,
            note="; ".join(trend.reasons),
        ),
        "commercial": Component(
            value=intent.commercial_score,
            weight=weights["commercial"],
            status="ok",
            note="; ".join(intent.commercial_reasons),
        ),
        "problem": Component(
            value=intent.problem_score,
            weight=weights["problem"],
            status="ok",
            note="; ".join(intent.problem_reasons),
        ),
        "novelty": Component(
            value=novelty_score(first_seen_at, now, novelty_decay_days),
            weight=weights["novelty"],
            status="ok",
            note=f"впервые замечена {age_days} дн. назад",
        ),
    }
    total, completeness = combine(components)
    is_preliminary = completeness < 0.999

    if trend.status != "ok":
        confidence: Confidence = "low"
    elif trend.basis == "monthly" and trend.months_available >= 12 and not trend.spike:
        confidence = "high"
    else:
        confidence = "medium"

    reasons: list[str] = []
    trend_value = components["trend"].value
    if trend_value is None:
        reasons.append("динамика: нет данных — рейтинг предварительный")
    elif trend_value >= 65:
        reasons.append(f"↑ спрос растёт (динамика {trend_value:.0f}/100)")
    elif trend_value <= 35:
        reasons.append(f"↓ спрос снижается (динамика {trend_value:.0f}/100)")
    else:
        reasons.append(f"• спрос стабилен (динамика {trend_value:.0f}/100)")
    if trend.spike:
        reasons.append("↓ всплеск похож на разовый — балл динамики ограничен 50")
    if trend.seasonal:
        reasons.append("• изменение сезонное — оценено год к году")
    if intent.commercial_score >= 70:
        reasons.append("↑ выраженное коммерческое намерение (по формулировке)")
    elif intent.commercial_score <= 30:
        reasons.append("↓ слабое коммерческое намерение")
    reasons.extend(r for r in intent.commercial_reasons if r.startswith("−"))
    if intent.problem_score >= 40:
        reasons.append("↑ в запросе явно видна проблема/рутина")
    if components["novelty"].value and components["novelty"].value >= 80:
        reasons.append("↑ фраза новая для базы")

    return ScoreResult(
        total=total,
        is_preliminary=is_preliminary,
        completeness=completeness,
        confidence=confidence,
        components=components,
        reasons=reasons,
    )


@dataclass(frozen=True)
class SelectionParams:
    top_min_score: float = 55.0
    decline_below: float = 25.0
    watch_min_commercial: float = 40.0
    watch_min_problem: float = 30.0


def select_status(
    score: ScoreResult, trend: TrendResult, params: SelectionParams | None = None
) -> tuple[Status, str]:
    """Решает, куда попадает фраза: в топ, в список наблюдения или в отбор."""
    params = params or SelectionParams()
    commercial = score.components["commercial"].value or 0
    problem = score.components["problem"].value or 0

    if trend.status == "low_volume":
        return "rejected", "объём запросов ниже порога"
    if trend.status == "insufficient_history":
        if commercial >= params.watch_min_commercial or problem >= params.watch_min_problem:
            return "watch", "новая фраза без истории — наблюдаем, пока не накопятся данные"
        return "rejected", "нет истории и слабое намерение"
    if trend.spike:
        return "watch", "разовый всплеск — наблюдаем, подтвердится ли спрос"
    trend_value = score.components["trend"].value or 0
    if trend_value < params.decline_below:
        return "rejected", "спрос заметно снижается"
    if score.total >= params.top_min_score:
        return "top", "проходит порог рейтинга"
    return "rejected", f"рейтинг ниже порога {params.top_min_score:.0f}"
