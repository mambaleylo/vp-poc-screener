from app.services.intent import Intent, analyze_intent


def test_transactional() -> None:
    result = analyze_intent("crm для салона цена")
    assert result.intent is Intent.TRANSACTIONAL
    assert result.commercial_score == 95  # 85 + бизнес-аудитория
    assert any("бизнес" in r for r in result.commercial_reasons)


def test_comparison_and_tool() -> None:
    assert analyze_intent("аналог amocrm").intent is Intent.COMPARISON
    assert analyze_intent("конвертер pdf онлайн").intent is Intent.TOOL


def test_problem_and_informational() -> None:
    problem = analyze_intent("как автоматизировать выставление счетов")
    assert problem.intent is Intent.PROBLEM
    assert problem.problem_score >= 45
    info = analyze_intent("что такое crm")
    assert info.intent is Intent.INFORMATIONAL
    assert info.commercial_score <= 30


def test_free_lowers_commercial_score_with_reason() -> None:
    paid = analyze_intent("конвертер pdf онлайн")
    free = analyze_intent("конвертер pdf онлайн бесплатно")
    assert free.commercial_score == paid.commercial_score - 25
    assert any("бесплат" in r for r in free.commercial_reasons)


def test_price_monitoring_is_not_purchase() -> None:
    result = analyze_intent("как отслеживать цены конкурентов на wildberries")
    assert result.intent is not Intent.TRANSACTIONAL


def test_scores_are_bounded() -> None:
    for phrase in ["", "купить купить цена для бизнеса", "скачать бесплатно что такое"]:
        result = analyze_intent(phrase)
        assert 0 <= result.commercial_score <= 100
        assert 0 <= result.problem_score <= 100


def test_no_problem_markers_reported_explicitly() -> None:
    result = analyze_intent("генератор счетов")
    assert result.problem_score == 0
    assert "нет явных признаков" in result.problem_reasons[0]
