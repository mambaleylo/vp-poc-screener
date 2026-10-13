"""Гипотеза продукта и следующий шаг проверки для найденной фразы.

Правила простые и прозрачные. Мы НЕ оцениваем выручку, число покупателей,
стоимость привлечения или готовность платить — таких данных у бота нет.
Конкуренция без данных о конкурентах всегда помечается как «не исследована».
"""

from __future__ import annotations

from urllib.parse import quote

from app.services.intent import Intent

INTENT_IDEA = {
    Intent.TRANSACTIONAL: "готовое решение с понятной ценой — сначала выяснить, кто уже "
    "продаёт это и почём",
    Intent.COMPARISON: "простая альтернатива существующим решениям — сначала выяснить, чем "
    "недовольны их пользователи",
    Intent.TOOL: "узкий онлайн-инструмент или бот, который делает ровно эту операцию",
    Intent.PROBLEM: "автоматизация описанной рутины: бот или скрипт, снимающий ручную работу",
    Intent.INFORMATIONAL: "прямой монетизации не видно; возможен бесплатный инструмент или "
    "контент как вход к платному продукту",
}

COMPETITION_UNKNOWN = "не исследована (данных о конкурентах в боте нет)"


def wordstat_url(phrase: str, region_key: str) -> str:
    region = "all" if region_key == "all" else region_key
    return f"https://wordstat.yandex.ru/?region={quote(region)}&view=table&words={quote(phrase)}"


def search_url(phrase: str) -> str:
    return f"https://yandex.ru/search/?text={quote(phrase)}"


def product_idea(intent: str, product_hint: str | None) -> str:
    try:
        idea = INTENT_IDEA[Intent(intent)]
    except ValueError:
        idea = INTENT_IDEA[Intent.INFORMATIONAL]
    if product_hint:
        return f"{product_hint}; {idea} (гипотеза)"
    return f"{idea[0].upper()}{idea[1:]} (гипотеза)"


def next_steps(data_used: dict, is_preliminary: bool) -> list[str]:
    """Конкретные действия для проверки гипотезы, от самого важного."""
    steps = []
    trend = data_used.get("trend") or {}
    if is_preliminary or trend.get("status") != "ok":
        steps.append(
            "Проверить динамику вручную в Wordstat (ссылка ниже) — бот ещё не накопил историю"
        )
    steps.append(
        "Открыть выдачу Яндекса и выписать 5–10 существующих решений: цена, модель оплаты, "
        "слабые места"
    )
    if (data_used.get("commercial_score") or 0) >= 60:
        steps.append(
            "Посмотреть, есть ли реклама в выдаче — косвенный признак, что на запросе зарабатывают"
        )
    if (data_used.get("problem_score") or 0) >= 40:
        steps.append(
            "Найти 3–5 обсуждений проблемы (форумы, чаты) и записать, как люди её описывают"
        )
    if trend.get("seasonal"):
        steps.append("Посмотреть график за 2+ года — рост может быть сезонным")
    if trend.get("spike"):
        steps.append("Выяснить причину всплеска (новость, изменение правил, сбой сервиса)")
    return steps


def missing_data(data_used: dict) -> list[str]:
    missing = []
    trend = data_used.get("trend") or {}
    if trend.get("status") == "insufficient_history":
        missing.append("история спроса")
    elif trend.get("seasonal") is None and trend.get("status") == "ok":
        missing.append("история ≥ 13 мес. для проверки сезонности")
    if data_used.get("latest_count") is None:
        missing.append("частотность")
    missing.append("конкуренты и их цены")
    missing.append("подтверждение, что за решение платят")
    return missing
