"""Настройки приложения: читаются из переменных окружения и файла .env.

Секреты (токены, ключи) хранятся как SecretStr: при печати объекта настроек
или в логах они отображаются как '**********'.
"""

from __future__ import annotations

import re
from datetime import time
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Корень проекта (папка search-scout/). Относительные пути считаются от неё,
# чтобы запуск из другой папки не создавал вторую базу.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Подписи для часто используемых регионов Wordstat. Для остальных выводится ID.
REGION_LABELS = {
    225: "Россия",
    149: "Беларусь",
    159: "Казахстан",
    187: "Украина",
    213: "Москва",
    2: "Санкт-Петербург",
    171: "Узбекистан",
    207: "Кыргызстан",
}

DEVICE_VALUES = {"desktop", "phone", "tablet"}

Mode = Literal["demo", "live"]


class ModeUnavailableError(RuntimeError):
    """Запрошен Live-режим, но источник не настроен."""


def _split_csv(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Telegram ---
    telegram_bot_token: SecretStr | None = None
    allowed_user_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    # Адрес собственного Bot API сервера (обычно не нужен; пусто = api.telegram.org)
    telegram_api_base: str | None = None

    # --- Режим ---
    scout_mode: Literal["auto", "demo", "live"] = "auto"

    # --- Пути ---
    database_path: Path = Path("data/search_scout.sqlite3")
    topics_path: Path = Path("config/topics.toml")
    csv_import_path: Path | None = Path("data/demo_keywords.csv")
    csv_is_demo: bool = True

    # --- Расписание ---
    timezone: str = "Europe/Moscow"
    daily_time: str = "09:00"
    daily_default_enabled: bool = True

    # --- Wordstat (Yandex Cloud Search API v2) ---
    wordstat_api_key: SecretStr | None = None
    wordstat_folder_id: str | None = None
    wordstat_base_url: str = "https://searchapi.api.cloud.yandex.net"
    wordstat_regions: Annotated[list[int], NoDecode] = Field(default_factory=list)
    wordstat_devices: Annotated[list[str], NoDecode] = Field(default_factory=list)
    wordstat_num_phrases: int = Field(default=100, ge=1, le=2000)
    wordstat_max_requests_per_scan: int = Field(default=60, ge=1)
    wordstat_dynamics_per_scan: int = Field(default=15, ge=0)
    wordstat_dynamics_months: int = Field(default=25, ge=4, le=60)
    wordstat_rps: float = Field(default=2.0, gt=0, le=10)
    wordstat_concurrency: int = Field(default=2, ge=1, le=10)
    wordstat_timeout_s: float = Field(default=30.0, gt=0)
    wordstat_max_retries: int = Field(default=4, ge=0, le=10)

    # --- Логика сканирования ---
    dynamics_refresh_days: int = Field(default=25, ge=1)
    expansion_per_scan: int = Field(default=5, ge=0)
    scan_stale_minutes: int = Field(default=120, ge=10)

    # --- Оценка ---
    weight_trend: float = Field(default=0.35, ge=0)
    weight_commercial: float = Field(default=0.30, ge=0)
    weight_problem: float = Field(default=0.20, ge=0)
    weight_novelty: float = Field(default=0.15, ge=0)
    top_min_score: float = Field(default=55.0, ge=0, le=100)
    min_monthly_volume: int = Field(default=50, ge=0)
    novelty_decay_days: int = Field(default=60, ge=1)

    # --- Отчёты ---
    report_max_items: int = Field(default=10, ge=1, le=30)
    report_watch_items: int = Field(default=5, ge=0, le=30)

    log_level: str = "INFO"

    # ---------------- валидация ----------------

    @field_validator("allowed_user_ids", "wordstat_regions", mode="before")
    @classmethod
    def _parse_int_list(cls, value: object) -> list[int]:
        try:
            return [int(v) for v in _split_csv(value)]
        except ValueError as exc:
            raise ValueError("ожидается список целых чисел через запятую") from exc

    @field_validator("wordstat_devices", mode="before")
    @classmethod
    def _parse_devices(cls, value: object) -> list[str]:
        devices = [d.lower() for d in _split_csv(value)]
        if "all" in devices:
            return []
        unknown = set(devices) - DEVICE_VALUES
        if unknown:
            raise ValueError(f"неизвестные устройства: {', '.join(sorted(unknown))}")
        return sorted(set(devices))

    @field_validator("telegram_bot_token", "wordstat_api_key", mode="before")
    @classmethod
    def _empty_secret_is_none(cls, value: object) -> object:
        return None if value is None or str(value).strip() == "" else value

    @field_validator("wordstat_folder_id", "csv_import_path", "telegram_api_base", mode="before")
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        return None if value is None or str(value).strip() == "" else value

    @field_validator("daily_time")
    @classmethod
    def _check_time(cls, value: str) -> str:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value.strip()):
            raise ValueError("DAILY_TIME должен быть в формате ЧЧ:ММ, например 09:00")
        return value.strip()

    @field_validator("timezone")
    @classmethod
    def _check_tz(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"неизвестный часовой пояс: {value}") from exc
        return value

    @model_validator(mode="after")
    def _check_weights(self) -> Settings:
        if (
            self.weight_trend + self.weight_commercial + self.weight_problem + self.weight_novelty
            <= 0
        ):
            raise ValueError("сумма весов рейтинга должна быть больше нуля")
        return self

    # ---------------- производные значения ----------------

    def resolve_path(self, path: Path) -> Path:
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def db_file(self) -> Path:
        return self.resolve_path(self.database_path)

    @property
    def topics_file(self) -> Path:
        return self.resolve_path(self.topics_path)

    @property
    def csv_file(self) -> Path | None:
        return self.resolve_path(self.csv_import_path) if self.csv_import_path else None

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def daily_time_value(self) -> time:
        hours, minutes = self.daily_time.split(":")
        return time(int(hours), int(minutes))

    @property
    def wordstat_configured(self) -> bool:
        return bool(self.wordstat_api_key and self.wordstat_folder_id)

    @property
    def region_key(self) -> str:
        """Ключ региона, под которым хранятся метрики: 'all' или '149,159,225'."""
        if not self.wordstat_regions:
            return "all"
        return ",".join(str(r) for r in sorted(set(self.wordstat_regions)))

    @property
    def devices_key(self) -> str:
        return ",".join(self.wordstat_devices) if self.wordstat_devices else "all"

    @property
    def weights(self) -> dict[str, float]:
        return {
            "trend": self.weight_trend,
            "commercial": self.weight_commercial,
            "problem": self.weight_problem,
            "novelty": self.weight_novelty,
        }

    def resolve_mode(self) -> Mode:
        """Какой режим реально используется.

        auto → live, если Wordstat настроен, иначе demo.
        live без ключей → ошибка: мы не подменяем реальные данные тестовыми.
        """
        if self.scout_mode == "demo":
            return "demo"
        if self.wordstat_configured:
            return "live"
        if self.scout_mode == "live":
            raise ModeUnavailableError(
                "Live-режим недоступен: не заданы WORDSTAT_API_KEY и/или WORDSTAT_FOLDER_ID. "
                "Заполните их в .env или переключите SCOUT_MODE=demo."
            )
        return "demo"

    def dataset_is_demo(self, mode: Mode) -> bool:
        """С какими данными работает режим: Live — только реальные; Demo/CSV —
        с теми, что в CSV (тестовые, если CSV_IS_DEMO=true)."""
        return False if mode == "live" else self.csv_is_demo

    def secret_values(self) -> list[str]:
        """Значения, которые нельзя выводить в логи."""
        values = []
        for secret in (self.telegram_bot_token, self.wordstat_api_key):
            if secret is not None and secret.get_secret_value():
                values.append(secret.get_secret_value())
        return values


def region_label(region_key: str) -> str:
    if region_key == "all":
        return "все регионы"
    names = []
    for part in region_key.split(","):
        try:
            rid = int(part)
        except ValueError:
            names.append(part)
            continue
        names.append(REGION_LABELS.get(rid, f"регион {rid}"))
    return ", ".join(names)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
