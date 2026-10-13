"""Анализ динамики спроса по накопленной истории.

Правила (все пороги — параметры, их проверяют тесты):

1. Основа — помесячный ряд (полные календарные месяцы).
   * ≥ 6 месяцев: среднее последних 3 мес. против предыдущих 3 мес.
   * 4–5 месяцев: последние 2 против предыдущих 2.
   * < 4 месяцев — помесячной динамики нет.
2. Если помесячного ряда нет, но есть два снимка «за последние 30 дней»
   с разницей ≥ 28 дней — сравниваем их (низкая уверенность).
3. Иначе — статус insufficient_history: рост НЕ придумывается.
4. Защита от деления на ноль: к обоим средним добавляется 1; если раньше
   спроса не было совсем, рост ограничивается MAX_RATIO.
5. Минимальный объём: если оба средних ниже min_volume, динамика считается
   ненадёжной (low_volume) и в рейтинг не идёт.
6. Всплеск: последний месяц > spike_factor × медианы предыдущих, а предпоследний
   ещё на обычном уровне → вероятно новостной/случайный всплеск, балл ≤ 50.
7. Сезонность (нужно ≥ 13 месяцев): если рост к прошлым месяцам заметен,
   а к тому же периоду прошлого года — нет, изменение сезонное, и для балла
   используется сравнение год к году. То же для сезонного спада.

Балл динамики: 50 = спрос стабилен, 100 = рост в full_ratio раз и более,
0 = падение в full_ratio раз и более (логарифмическая шкала).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from statistics import mean, median
from typing import Literal

TrendStatus = Literal["ok", "insufficient_history", "low_volume"]

MAX_RATIO = 10.0


@dataclass(frozen=True)
class TrendParams:
    min_volume: int = 50
    full_ratio: float = 2.0
    spike_factor: float = 3.0
    seasonal_growth: float = 1.3  # рост, при котором проверяем сезонность
    seasonal_band: tuple[float, float] = (0.8, 1.25)  # «год к году примерно без изменений»
    rolling_min_gap_days: int = 28


@dataclass
class TrendResult:
    status: TrendStatus
    score: float | None
    basis: str | None = None  # monthly | rolling30
    growth_ratio: float | None = None
    recent_avg: float | None = None
    previous_avg: float | None = None
    window_label: str | None = None
    months_available: int = 0
    spike: bool = False
    seasonal: bool | None = None  # None — определить нельзя
    yoy_ratio: float | None = None
    reasons: list[str] = field(default_factory=list)


def ratio_to_score(ratio: float, full_ratio: float = 2.0) -> float:
    """log-шкала: ratio=1 → 50, ratio=full_ratio → 100, ratio=1/full_ratio → 0."""
    if ratio <= 0:
        return 0.0
    value = 50 + 50 * math.log(ratio) / math.log(full_ratio)
    return round(max(0.0, min(100.0, value)), 1)


def safe_ratio(recent: float, previous: float) -> float:
    return min(MAX_RATIO, (recent + 1.0) / (previous + 1.0))


def _fmt_pct(ratio: float) -> str:
    return f"{(ratio - 1) * 100:+.0f}%"


def analyze_monthly(
    series: list[tuple[date, int]], params: TrendParams | None = None
) -> TrendResult:
    """series — пары (первое число месяца, частотность), только полные месяцы."""
    params = params or TrendParams()
    points = sorted(series)
    counts = [c for _, c in points]
    n = len(counts)
    if n < 4:
        return TrendResult(
            status="insufficient_history",
            score=None,
            months_available=n,
            reasons=[f"недостаточно истории: {n} мес. (нужно ≥ 4)"],
        )

    window = 3 if n >= 6 else 2
    recent = mean(counts[-window:])
    previous = mean(counts[-2 * window : -window])
    label = f"{window} посл. мес. против {window} предыдущих"
    result = TrendResult(
        status="ok",
        score=None,
        basis="monthly",
        recent_avg=round(recent, 1),
        previous_avg=round(previous, 1),
        window_label=label,
        months_available=n,
    )

    if max(recent, previous) < params.min_volume:
        result.status = "low_volume"
        result.reasons.append(f"объём ниже порога {params.min_volume}/мес. — динамика ненадёжна")
        return result

    ratio = safe_ratio(recent, previous)
    result.growth_ratio = round(ratio, 3)
    score_ratio = ratio
    result.reasons.append(f"динамика {_fmt_pct(ratio)} ({label})")

    # Всплеск только в последнем месяце
    prior = counts[:-1]
    base = median(prior)
    if counts[-1] > params.spike_factor * max(base, 1) and counts[-2] <= 1.5 * max(base, 1):
        result.spike = True
        result.reasons.append(
            "резкий всплеск только в последнем месяце — похоже на новостной или случайный"
        )

    # Сезонность
    if n >= 13:
        last_year = counts[-13]
        yoy = safe_ratio(counts[-1], last_year)
        if n >= 15:
            yoy = safe_ratio(mean(counts[-3:]), mean(counts[-15:-12]))
        result.yoy_ratio = round(yoy, 3)
        low, high = params.seasonal_band
        big_move = ratio >= params.seasonal_growth or ratio <= 1 / params.seasonal_growth
        if big_move and low <= yoy <= high:
            result.seasonal = True
            score_ratio = yoy
            word = "рост" if ratio > 1 else "спад"
            result.reasons.append(
                f"{word} повторяет прошлогодний сезон (год к году {_fmt_pct(yoy)}) — "
                "в балл идёт сравнение год к году"
            )
        else:
            result.seasonal = False
    else:
        result.reasons.append("сезонность не определить: история < 13 мес.")

    score = ratio_to_score(score_ratio, params.full_ratio)
    if result.spike:
        score = min(score, 50.0)
    result.score = score
    return result


def analyze_rolling(
    snapshots: list[tuple[date, int]], params: TrendParams | None = None
) -> TrendResult:
    """snapshots — (дата наблюдения, частотность за последние 30 дней)."""
    params = params or TrendParams()
    points = sorted(snapshots)
    if len(points) < 2:
        return TrendResult(
            status="insufficient_history",
            score=None,
            reasons=["есть только одно наблюдение — динамику оценить нельзя"],
        )
    last_day, last = points[-1]
    earlier = [p for p in points if (last_day - p[0]).days >= params.rolling_min_gap_days]
    if not earlier:
        return TrendResult(
            status="insufficient_history",
            score=None,
            reasons=[
                f"наблюдения охватывают < {params.rolling_min_gap_days} дней — "
                "динамику оценить нельзя"
            ],
        )
    prev_day, prev = earlier[-1]
    result = TrendResult(
        status="ok",
        score=None,
        basis="rolling30",
        recent_avg=float(last),
        previous_avg=float(prev),
        window_label=f"30 дней на {last_day:%d.%m} против 30 дней на {prev_day:%d.%m}",
    )
    if max(last, prev) < params.min_volume:
        result.status = "low_volume"
        result.reasons.append(f"объём ниже порога {params.min_volume} — динамика ненадёжна")
        return result
    ratio = safe_ratio(last, prev)
    result.growth_ratio = round(ratio, 3)
    result.score = ratio_to_score(ratio, params.full_ratio)
    result.reasons.append(
        f"динамика {_fmt_pct(ratio)} ({result.window_label}); всплески и сезонность "
        "по двум точкам не определить"
    )
    return result


def analyze(
    monthly: list[tuple[date, int]],
    rolling: list[tuple[date, int]],
    params: TrendParams | None = None,
) -> TrendResult:
    monthly_result = analyze_monthly(monthly, params)
    if monthly_result.status != "insufficient_history":
        return monthly_result
    rolling_result = analyze_rolling(rolling, params)
    if rolling_result.status != "insufficient_history":
        rolling_result.months_available = monthly_result.months_available
        return rolling_result
    return TrendResult(
        status="insufficient_history",
        score=None,
        months_available=monthly_result.months_available,
        reasons=["недостаточно истории для оценки динамики"],
    )
