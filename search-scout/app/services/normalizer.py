"""Нормализация и группировка поисковых фраз.

normalize_phrase  — каноническая форма для сравнения и дедупликации:
                    нижний регистр, ё→е, без операторов Wordstat и лишних пробелов.
group_key         — ключ группы близких формулировок: слова приводятся к основе
                    (стеммер Snowball), ПОРЯДОК СЛОВ СОХРАНЯЕТСЯ.

Почему порядок сохраняется: «из pdf в word» и «из word в pdf» — разные
намерения, хотя слова одинаковые. А вот «конвертер pdf» и «конвертеры pdf»
— одно и то же, их группируем.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

import snowballstemmer

# Всё, что не буква/цифра/пробел/дефис/точка/плюс/решётка, превращается в пробел.
# Операторы Wordstat (! " [ ] ( ) |) и пунктуация отбрасываются.
_DISALLOWED = re.compile(r"[^\w\s\-.+#]", flags=re.UNICODE)
_SPACES = re.compile(r"\s+")
# Минус-слова Wordstat: «-слово» в начале токена
_MINUS_WORD = re.compile(r"(?:^|\s)-\S+")

_stemmer = snowballstemmer.stemmer("russian")
_en_stemmer = snowballstemmer.stemmer("english")


def normalize_phrase(text: str) -> str:
    """Возвращает нормализованную фразу ('' — если после очистки ничего не осталось)."""
    value = text.lower().replace("ё", "е")
    value = _MINUS_WORD.sub(" ", value)
    value = _DISALLOWED.sub(" ", value)
    value = value.replace("_", " ")
    tokens = []
    for raw in _SPACES.split(value):
        # «+» перед словом — оператор Wordstat; «c++» оставляем как есть.
        token = raw.lstrip("+").strip("-.")
        if token:
            tokens.append(token)
    return " ".join(tokens)


@lru_cache(maxsize=50_000)
def _stem(token: str) -> str:
    if re.fullmatch(r"[a-z]+", token):
        return _en_stemmer.stemWord(token)
    if re.fullmatch(r"[а-я]+", token):
        return _stemmer.stemWord(token)
    return token


def group_key(normalized: str) -> str:
    return " ".join(_stem(token) for token in normalized.split())


def contains_marker(normalized: str, marker: str) -> bool:
    """Есть ли в фразе маркер, совпадающий с НАЧАЛОМ слова.

    marker «счет» найдёт «счета» и «счетов», но не «пересчет».
    Пробел в конце маркера («ип ») требует целого слова.
    Маркер из нескольких слов ищется как последовательность.
    """
    haystack = f" {normalized} "
    needle = " " + normalize_phrase(marker)
    if marker.endswith(" "):
        needle += " "
    return needle in haystack


@dataclass(frozen=True)
class NormalizedPhrase:
    original: str
    normalized: str
    group_key: str


def prepare(original: str) -> NormalizedPhrase | None:
    original = _SPACES.sub(" ", original).strip()
    normalized = normalize_phrase(original)
    if not normalized:
        return None
    return NormalizedPhrase(
        original=original, normalized=normalized, group_key=group_key(normalized)
    )


def dedupe(phrases: list[str]) -> list[NormalizedPhrase]:
    """Убирает точные дубликаты после нормализации, сохраняя первую исходную формулировку."""
    seen: set[str] = set()
    result = []
    for phrase in phrases:
        item = prepare(phrase)
        if item is None or item.normalized in seen:
            continue
        seen.add(item.normalized)
        result.append(item)
    return result
