from datetime import date

import pytest

from app.services.trend import (
    MAX_RATIO,
    TrendParams,
    analyze,
    analyze_monthly,
    analyze_rolling,
    ratio_to_score,
    safe_ratio,
)
from tests.conftest import monthly


def test_ratio_to_score_scale() -> None:
    assert ratio_to_score(1.0) == 50
    assert ratio_to_score(2.0) == 100
    assert ratio_to_score(0.5) == 0
    assert ratio_to_score(10.0) == 100
    assert ratio_to_score(0) == 0
    assert 50 < ratio_to_score(1.3) < 100


def test_safe_ratio_handles_zero() -> None:
    assert safe_ratio(0, 0) == 1.0
    assert safe_ratio(500, 0) == MAX_RATIO  # раньше спроса не было — рост ограничен


def test_insufficient_history_is_not_invented() -> None:
    result = analyze_monthly(monthly(date(2026, 7, 1), [100, 120, 140]))
    assert result.status == "insufficient_history"
    assert result.score is None
    assert result.growth_ratio is None


def test_growth_with_three_month_windows() -> None:
    result = analyze_monthly(monthly(date(2026, 3, 1), [100, 100, 100, 150, 150, 150]))
    assert result.status == "ok"
    assert result.recent_avg == 150 and result.previous_avg == 100
    assert result.growth_ratio == pytest.approx(151 / 101, rel=1e-3)
    assert result.score is not None and result.score > 70
    assert result.seasonal is None  # меньше 13 месяцев — сезонность не определить


def test_short_history_uses_two_month_windows() -> None:
    result = analyze_monthly(monthly(date(2026, 5, 1), [100, 100, 200, 200]))
    assert result.window_label.startswith("2 ")
    assert result.score == pytest.approx(100, abs=0.5)  # +1 в числителе и знаменателе


def test_low_volume_not_scored() -> None:
    result = analyze_monthly(
        monthly(date(2026, 1, 1), [5, 6, 7, 8, 9, 30]), TrendParams(min_volume=50)
    )
    assert result.status == "low_volume"
    assert result.score is None


def test_spike_is_capped() -> None:
    values = [100] * 8 + [600]
    result = analyze_monthly(monthly(date(2025, 12, 1), values))
    assert result.spike is True
    assert result.score == 50


def test_sustained_growth_is_not_spike() -> None:
    values = [100, 100, 100, 100, 200, 300, 400, 500, 600]
    result = analyze_monthly(monthly(date(2025, 12, 1), values))
    assert result.spike is False
    assert result.score == 100


def test_seasonal_growth_uses_year_over_year() -> None:
    # Синтетический сезон: всплеск каждый сентябрь–октябрь, год к году без изменений.
    year = [100, 100, 100, 100, 100, 100, 100, 100, 200, 220, 100, 100]
    values = year + year[:10]  # 22 месяца, январь 2025 — октябрь 2026
    result = analyze_monthly(monthly(date(2025, 1, 1), values))
    assert result.growth_ratio is not None and result.growth_ratio > 1.3
    assert result.seasonal is True
    assert result.score == pytest.approx(50, abs=5)


def test_non_seasonal_growth_detected_with_long_history() -> None:
    values = [100] * 12 + [100, 110, 150, 200, 250]
    result = analyze_monthly(monthly(date(2025, 1, 1), values))
    assert result.seasonal is False
    assert result.score is not None and result.score > 80


def test_rolling_needs_gap() -> None:
    near = analyze_rolling([(date(2026, 10, 1), 100), (date(2026, 10, 10), 200)])
    assert near.status == "insufficient_history"
    far = analyze_rolling([(date(2026, 9, 1), 100), (date(2026, 10, 10), 200)])
    assert far.status == "ok"
    assert far.basis == "rolling30"
    assert far.score is not None and far.score > 90


def test_analyze_prefers_monthly_and_falls_back() -> None:
    rolling = [(date(2026, 8, 1), 100), (date(2026, 10, 1), 100)]
    assert analyze([], rolling).basis == "rolling30"
    months = monthly(date(2026, 1, 1), [100] * 6)
    assert analyze(months, rolling).basis == "monthly"
    assert analyze([], [(date(2026, 10, 1), 5)]).status == "insufficient_history"
