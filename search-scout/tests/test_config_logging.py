import logging

import pytest
from pydantic import ValidationError

from app.config import ModeUnavailableError, region_label
from app.logging_setup import SecretRedactingFilter


def test_list_parsing_and_keys(make_settings) -> None:
    s = make_settings(
        allowed_user_ids="1, 2", wordstat_regions="225,149", wordstat_devices="phone,desktop"
    )
    assert s.allowed_user_ids == [1, 2]
    assert s.region_key == "149,225"
    assert s.devices_key == "desktop,phone"
    assert make_settings(wordstat_devices="all").devices_key == "all"
    assert make_settings(allowed_user_ids="").allowed_user_ids == []


def test_invalid_values_rejected(make_settings) -> None:
    for bad in (
        {"daily_time": "9am"},
        {"timezone": "Mars/Base"},
        {"allowed_user_ids": "abc"},
        {"wordstat_devices": "tv"},
    ):
        with pytest.raises(ValidationError):
            make_settings(**bad)


def test_mode_resolution(make_settings) -> None:
    assert make_settings().resolve_mode() == "demo"
    assert make_settings(wordstat_api_key="k", wordstat_folder_id="f").resolve_mode() == "live"
    assert (
        make_settings(
            scout_mode="demo", wordstat_api_key="k", wordstat_folder_id="f"
        ).resolve_mode()
        == "demo"
    )
    with pytest.raises(ModeUnavailableError):
        make_settings(scout_mode="live", wordstat_api_key="k").resolve_mode()
    # Пустые строки в .env означают «не задано»
    assert make_settings(wordstat_api_key="", wordstat_folder_id="").wordstat_configured is False


def test_secrets_hidden_in_repr(make_settings) -> None:
    s = make_settings(telegram_bot_token="123456:SECRET_TOKEN_VALUE_abcdefghijklmnopqrstu")
    assert "SECRET_TOKEN" not in repr(s)


def test_region_label() -> None:
    assert region_label("all") == "все регионы"
    assert region_label("149,225") == "Беларусь, Россия"
    assert region_label("99999") == "регион 99999"


def test_log_redaction() -> None:
    token = "123456789:AAH-very-secret-token-value-1234567890"
    flt = SecretRedactingFilter(["my-api-key-123"])
    record = logging.LogRecord(
        "x",
        logging.INFO,
        __file__,
        1,
        "url https://api.telegram.org/bot%s/getMe key=%s",
        (token, "my-api-key-123"),
        None,
    )
    flt.filter(record)
    message = record.getMessage()
    assert token not in message and "my-api-key-123" not in message
    assert message.count("***") == 2
