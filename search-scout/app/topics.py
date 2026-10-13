"""Загрузка тематик и правил расширения из config/topics.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from app.services.normalizer import contains_marker, normalize_phrase


class TopicsConfigError(ValueError):
    pass


@dataclass(frozen=True)
class TopicConfig:
    key: str
    title: str
    stems: tuple[str, ...]
    seeds: tuple[str, ...]
    core: tuple[str, ...]
    modifiers: tuple[str, ...]
    product_hint: str

    def matches(self, normalized: str) -> bool:
        return any(contains_marker(normalized, stem) for stem in self.stems)

    def all_seeds(self, max_modifiers: int) -> list[str]:
        """Стартовые фразы + фразы, полученные по правилам расширения."""
        result: list[str] = []
        for seed in self.seeds:
            result.append(normalize_phrase(seed))
        for core in self.core:
            for modifier in self.modifiers[:max_modifiers]:
                result.append(normalize_phrase(f"{core} {modifier}"))
        # Без повторов, порядок сохраняем
        return list(dict.fromkeys(s for s in result if s))


@dataclass(frozen=True)
class TopicsConfig:
    topics: tuple[TopicConfig, ...]
    exclude: tuple[str, ...] = ()
    max_modifiers_per_core: int = 8
    commercial_modifiers: tuple[str, ...] = field(default_factory=tuple)

    def by_key(self, key: str) -> TopicConfig | None:
        return next((t for t in self.topics if t.key == key), None)

    def is_excluded(self, normalized: str) -> bool:
        return any(contains_marker(normalized, word) for word in self.exclude)

    def classify(self, normalized: str, preferred_key: str | None = None) -> TopicConfig | None:
        """К какой тематике относится фраза (None — ни к какой или в стоп-списке).

        Если фраза подходит под тематику сида, из которого она получена,
        выбираем её; иначе — первую подходящую по порядку в конфиге.
        """
        if self.is_excluded(normalized):
            return None
        if preferred_key:
            preferred = self.by_key(preferred_key)
            if preferred and preferred.matches(normalized):
                return preferred
        return next((t for t in self.topics if t.matches(normalized)), None)


def _str_list(raw: dict, name: str, where: str) -> tuple[str, ...]:
    value = raw.get(name, [])
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise TopicsConfigError(f"{where}: поле '{name}' должно быть списком строк")
    return tuple(value)


def load_topics(path: Path) -> TopicsConfig:
    if not path.exists():
        raise TopicsConfigError(f"Файл тематик не найден: {path}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise TopicsConfigError(f"Ошибка в {path}: {exc}") from exc

    expansion = data.get("expansion", {})
    commercial = _str_list(expansion, "commercial_modifiers", "[expansion]")
    max_mods = int(expansion.get("max_modifiers_per_core", 8))
    exclude = _str_list(data.get("filters", {}), "exclude", "[filters]")

    topics = []
    seen_keys: set[str] = set()
    for index, raw in enumerate(data.get("topic", []), start=1):
        where = f"[[topic]] №{index}"
        key = raw.get("key")
        title = raw.get("title")
        if not key or not title:
            raise TopicsConfigError(f"{where}: обязательны поля key и title")
        if key in seen_keys:
            raise TopicsConfigError(f"{where}: повторяется key '{key}'")
        seen_keys.add(key)
        stems = _str_list(raw, "stems", where)
        if not stems:
            raise TopicsConfigError(f"{where}: нужен хотя бы один stem")
        topics.append(
            TopicConfig(
                key=key,
                title=title,
                stems=stems,
                seeds=_str_list(raw, "seeds", where),
                core=_str_list(raw, "core", where),
                modifiers=_str_list(raw, "modifiers", where) or commercial,
                product_hint=str(raw.get("product_hint", "")),
            )
        )
    if not topics:
        raise TopicsConfigError(f"В {path} нет ни одной тематики [[topic]]")
    return TopicsConfig(
        topics=tuple(topics),
        exclude=exclude,
        max_modifiers_per_core=max_mods,
        commercial_modifiers=commercial,
    )
