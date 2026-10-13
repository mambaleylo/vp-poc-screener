from datetime import timedelta

import pytest

from app.services.intent import analyze_intent
from app.services.scorer import Component, combine, novelty_score, score_phrase, select_status
from app.services.trend import TrendResult
from tests.conftest import FIXED_NOW

WEIGHTS = {"trend": 0.35, "commercial": 0.30, "problem": 0.20, "novelty": 0.15}


def trend_ok(score: float, **kw: object) -> TrendResult:
    defaults = {"basis": "monthly", "months_available": 14, "growth_ratio": 1.2}
    defaults.update(kw)
    return TrendResult(status="ok", score=score, **defaults)  # type: ignore[arg-type]


def test_combine_full_weighted_average() -> None:
    comps = {
        "trend": Component(100, 0.35, "ok", ""),
        "commercial": Component(0, 0.30, "ok", ""),
        "problem": Component(50, 0.20, "ok", ""),
        "novelty": Component(100, 0.15, "ok", ""),
    }
    total, completeness = combine(comps)
    assert total == pytest.approx(35 + 0 + 10 + 15)
    assert completeness == 1.0


def test_combine_missing_component_renormalizes() -> None:
    comps = {
        "trend": Component(None, 0.35, "insufficient_history", ""),
        "commercial": Component(80, 0.30, "ok", ""),
        "problem": Component(40, 0.20, "ok", ""),
        "novelty": Component(100, 0.15, "ok", ""),
    }
    total, completeness = combine(comps)
    assert total == pytest.approx((80 * 0.30 + 40 * 0.20 + 100 * 0.15) / 0.65, abs=0.1)
    assert completeness == pytest.approx(0.65)


def test_novelty_decay() -> None:
    assert novelty_score(FIXED_NOW, FIXED_NOW, 60) == 100
    assert novelty_score(FIXED_NOW - timedelta(days=30), FIXED_NOW, 60) == 50
    assert novelty_score(FIXED_NOW - timedelta(days=90), FIXED_NOW, 60) == 0


def test_score_is_reproducible_and_bounded() -> None:
    intent = analyze_intent("генератор счетов для ип онлайн")
    args = dict(
        intent=intent,
        trend=trend_ok(80),
        first_seen_at=FIXED_NOW - timedelta(days=10),
        now=FIXED_NOW,
        weights=WEIGHTS,
        novelty_decay_days=60,
    )
    first, second = score_phrase(**args), score_phrase(**args)
    assert first.total == second.total
    assert 0 <= first.total <= 100
    assert first.is_preliminary is False
    assert first.confidence == "high"
    assert set(first.components) == {"trend", "commercial", "problem", "novelty"}


def test_missing_trend_marks_preliminary_without_fake_value() -> None:
    intent = analyze_intent("генератор счетов")
    result = score_phrase(
        intent=intent,
        trend=TrendResult(status="insufficient_history", score=None, reasons=["нет истории"]),
        first_seen_at=FIXED_NOW,
        now=FIXED_NOW,
        weights=WEIGHTS,
        novelty_decay_days=60,
    )
    assert result.components["trend"].value is None
    assert result.is_preliminary is True
    assert result.confidence == "low"
    assert result.completeness == pytest.approx(0.65)
    assert any("предварительный" in r for r in result.reasons)


def _scored(trend: TrendResult, phrase: str = "генератор счетов для ип онлайн"):
    return score_phrase(
        intent=analyze_intent(phrase),
        trend=trend,
        first_seen_at=FIXED_NOW,
        now=FIXED_NOW,
        weights=WEIGHTS,
        novelty_decay_days=60,
    )


def test_select_status() -> None:
    assert select_status(_scored(trend_ok(90)), trend_ok(90))[0] == "top"
    assert select_status(_scored(trend_ok(10)), trend_ok(10))[0] == "rejected"
    spike = trend_ok(50, spike=True)
    assert select_status(_scored(spike), spike)[0] == "watch"
    no_history = TrendResult(status="insufficient_history", score=None)
    assert select_status(_scored(no_history), no_history)[0] == "watch"
    weak = _scored(no_history, "что такое отчет")
    assert select_status(weak, no_history)[0] == "rejected"
    low = TrendResult(status="low_volume", score=None)
    assert select_status(_scored(low), low) == ("rejected", "объём запросов ниже порога")
