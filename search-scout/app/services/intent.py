"""Правила определения намерения пользователя по тексту запроса.

Это прозрачные правила, а не модель: каждое срабатывание даёт текстовую
причину, которая попадает в отчёт. Позже сюда можно подключить ML/LLM,
сохранив интерфейс analyze_intent() → IntentResult.

Важно: коммерческое слово в запросе — признак намерения, но НЕ доказательство
того, что люди готовы платить. Поэтому балл — эвристика, а не вероятность.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.services.normalizer import contains_marker


class Intent(StrEnum):
    TRANSACTIONAL = "transactional"
    COMPARISON = "comparison"
    TOOL = "tool"
    PROBLEM = "problem"
    INFORMATIONAL = "informational"


INTENT_LABELS = {
    Intent.TRANSACTIONAL: "транзакционный / ценовой",
    Intent.COMPARISON: "сравнение / поиск альтернативы",
    Intent.TOOL: "поиск конкретного инструмента",
    Intent.PROBLEM: "описание проблемы",
    Intent.INFORMATIONAL: "информационный",
}

# Базовый балл коммерческого намерения по типу запроса (0..100)
INTENT_BASE_SCORE = {
    Intent.TRANSACTIONAL: 85,
    Intent.COMPARISON: 70,
    Intent.TOOL: 65,
    Intent.PROBLEM: 45,
    Intent.INFORMATIONAL: 15,
}

# Явно информационные вопросы перекрывают остальные правила:
# «что такое crm» — интерес к понятию, а не поиск инструмента.
INFORMATIONAL_OVERRIDES = (
    "что такое",
    "что это",
    "что значит",
    "определение",
    "википеди",
    "кто придумал",
    "история создания",
    "расшифровка",
)

# Маркеры — начала слов (см. contains_marker). Порядок проверки = приоритет.
INTENT_MARKERS: tuple[tuple[Intent, tuple[str, ...]], ...] = (
    (Intent.INFORMATIONAL, INFORMATIONAL_OVERRIDES),
    (
        Intent.TRANSACTIONAL,
        (
            "купить",
            "куплю",
            "покупк",
            "цена",
            "цены",
            "стоимость",
            "сколько стоит",
            "заказать",
            "закажу",
            "тариф",
            "подписк",
            "прайс",
            "недорог",
            "дешев",
            "руб ",
            "рублей",
            "оплат",
        ),
    ),
    (
        Intent.COMPARISON,
        (
            "аналог",
            "альтернатив",
            "вместо",
            "замена",
            "заменить",
            "сравнени",
            "vs ",
            "или ",
            "лучше ",
            "лучший",
            "лучшие",
            "топ ",
            "рейтинг",
            "отзыв",
        ),
    ),
    (
        Intent.TOOL,
        (
            "программ",
            "сервис",
            "онлайн",
            "бот ",
            "бота",
            "боты",
            "приложени",
            "генератор",
            "калькулятор",
            "конвертер",
            "конструктор",
            "шаблон",
            "плагин",
            "расширени",
            "скрипт",
            "api",
            "парсер",
            "crm",
            "срм",
            "инструмент",
            "платформ",
            "софт",
            "утилит",
            "система",
        ),
    ),
    (
        Intent.PROBLEM,
        (
            "как ",
            "почему",
            "не работает",
            "ошибка",
            "не открывается",
            "не получается",
            "что делать",
            "без ручной",
            "вручную",
            "долго",
            "сократить",
            "ускорить",
            "упростить",
            "автоматизировать",
            "избавиться",
        ),
    ),
)

# Сочетания, где «цена/стоимость» означает не покупку, а данные о ценах
# («мониторинг цен конкурентов»). Перед поиском ценовых маркеров они вырезаются.
PRICE_DATA_CONTEXTS = (
    "цены конкурентов",
    "цен конкурентов",
    "мониторинг цен",
    "отслеживание цен",
    "отслеживать цены",
    "парсинг цен",
    "парсер цен",
    "сравнение цен",
    "динамика цен",
    "история цен",
    "изменение цен",
)

# Сигналы B2B-аудитории: бизнес чаще платит за инструменты, чем частные лица.
B2B_MARKERS = (
    "для бизнеса",
    "бизнес",
    "для магазина",
    "магазин",
    "для маркетплейса",
    "маркетплейс",
    "wildberries",
    "вайлдберриз",
    "ozon",
    "озон",
    "селлер",
    "для ип",
    "ип ",
    "ооо",
    "для компании",
    "компани",
    "для салона",
    "салон",
    "клиник",
    "для юрист",
    "бухгалтер",
    "1с",
    "crm",
    "склад",
    "оптов",
    "b2b",
    "самозанят",
    "фриланс",
)

# Выраженность проблемы: (маркеры, вклад, причина)
PROBLEM_RULES: tuple[tuple[tuple[str, ...], int, str], ...] = (
    (
        (
            "не работает",
            "ошибка",
            "не открывается",
            "не получается",
            "проблем",
            "глючит",
            "тормозит",
            "слетает",
            "не сохраняется",
            "что делать",
        ),
        50,
        "описан сбой или проблема",
    ),
    (
        (
            "как автоматизировать",
            "как ускорить",
            "как сократить",
            "как упростить",
            "как быстро",
            "как избавиться",
            "без ручной",
            "вручную",
            "рутин",
            "долго",
            "автоматизировать",
        ),
        45,
        "ищут способ убрать ручную работу",
    ),
    (
        (
            "массов",
            "пакетн",
            "много файлов",
            "сразу несколько",
            "несколько файлов",
            "автоматически",
            "все файлы",
            "по расписанию",
        ),
        30,
        "задача повторяется в объёме",
    ),
    (
        (
            "без потери",
            "сохранить форматирование",
            "с сохранением",
            "без искажений",
            "без водяного знака",
            "без ограничений",
        ),
        30,
        "существующие решения не устраивают качеством или ограничениями",
    ),
    (
        ("чем заменить", "аналог", "альтернатив", "вместо", "замена"),
        30,
        "недовольство текущим решением / поиск замены",
    ),
    (("как ", "почему"), 15, "вопрос «как/почему» — есть задача, которую пытаются решить"),
)

FREE_MARKERS = ("бесплатн", "free", "даром", "без регистрации")
DOWNLOAD_MARKERS = ("скачать", "скачивани", "download")


@dataclass
class IntentResult:
    intent: Intent
    commercial_score: float
    problem_score: float
    commercial_reasons: list[str] = field(default_factory=list)
    problem_reasons: list[str] = field(default_factory=list)
    matched_markers: list[str] = field(default_factory=list)


def _first_match(normalized: str, markers: tuple[str, ...]) -> str | None:
    return next((m for m in markers if contains_marker(normalized, m)), None)


def analyze_intent(normalized: str) -> IntentResult:
    intent = Intent.INFORMATIONAL
    matched: list[str] = []
    without_price_data = normalized
    for context in PRICE_DATA_CONTEXTS:
        without_price_data = without_price_data.replace(context, " ")
    for candidate, markers in INTENT_MARKERS:
        text = without_price_data if candidate is Intent.TRANSACTIONAL else normalized
        marker = _first_match(" ".join(text.split()), markers)
        if marker:
            intent = candidate
            matched.append(marker.strip())
            break

    commercial = float(INTENT_BASE_SCORE[intent])
    reasons = [f"тип запроса: {INTENT_LABELS[intent]}" + (f" («{matched[0]}»)" if matched else "")]

    b2b = _first_match(normalized, B2B_MARKERS)
    if b2b:
        commercial += 10
        reasons.append(f"+ бизнес-аудитория («{b2b.strip()}»)")
    free = _first_match(normalized, FREE_MARKERS)
    if free:
        commercial -= 25
        reasons.append(f"− ищут бесплатное («{free.strip()}»): готовность платить под вопросом")
    download = _first_match(normalized, DOWNLOAD_MARKERS)
    if download:
        commercial -= 10
        reasons.append("− ищут скачиваемую программу, а не сервис")
    commercial = max(0.0, min(100.0, commercial))

    problem = 0
    problem_reasons = []
    for markers, weight, reason in PROBLEM_RULES:
        marker = _first_match(normalized, markers)
        if marker:
            problem += weight
            problem_reasons.append(f"{reason} («{marker.strip()}»)")
    if not problem_reasons:
        problem_reasons.append("в формулировке нет явных признаков проблемы")

    return IntentResult(
        intent=intent,
        commercial_score=commercial,
        problem_score=float(min(100, problem)),
        commercial_reasons=reasons,
        problem_reasons=problem_reasons,
        matched_markers=matched,
    )
