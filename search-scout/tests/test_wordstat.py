"""Адаптер Wordstat против поддельного HTTP-сервера (httpx.MockTransport).
Ответы сервера — синтетические, реальный API не вызывается."""

import json
from datetime import date

import httpx
import pytest

from app.sources.base import SourceAuthError, SourceRequestError, SourceTemporaryError
from app.sources.wordstat import WordstatSource, month_range, to_int

SECRET = "AQVN-test-secret-key"


class FakeSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def make_source(make_settings, handler, **overrides):
    settings = make_settings(
        wordstat_api_key=SECRET,
        wordstat_folder_id="b1gtestfolder",
        wordstat_rps=10,
        wordstat_max_retries=3,
        **overrides,
    )
    sleep = FakeSleep()
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source = WordstatSource(settings, client, sleep=sleep, today=lambda: date(2026, 10, 13))
    return source, sleep


def test_helpers() -> None:
    assert to_int("123") == 123 and to_int(5) == 5 and to_int(None) is None and to_int("x") is None
    assert month_range(date(2026, 9, 30), 12) == (date(2025, 10, 1), date(2026, 9, 30))
    assert month_range(date(2026, 9, 30), 25) == (date(2024, 9, 1), date(2026, 9, 30))


async def test_top_requests_request_and_parsing(make_settings) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "totalCount": "1500",
                "results": [{"phrase": "конвертер pdf онлайн", "count": "900"}],
                "associations": [{"phrase": "объединить pdf", "count": 300}],
            },
        )

    source, _ = make_source(
        make_settings, handler, wordstat_regions="225,149", wordstat_devices="phone"
    )
    observations = await source.related("конвертер pdf", "documents_files")
    assert seen["url"].endswith("/v2/wordstat/topRequests")
    assert seen["auth"] == f"Api-Key {SECRET}"
    assert seen["body"] == {
        "folderId": "b1gtestfolder",
        "regions": ["149", "225"],
        "devices": ["DEVICE_PHONE"],
        "phrase": "конвертер pdf",
        "numPhrases": 100,
    }
    assert [(o.phrase, o.count) for o in observations] == [
        ("конвертер pdf", 1500),
        ("конвертер pdf онлайн", 900),
        ("объединить pdf", 300),
    ]
    assert all(o.region_key == "149,225" and o.period_type == "rolling30" for o in observations)
    assert all(not o.is_demo and o.source == "wordstat" for o in observations)


async def test_dynamics_request_and_incomplete_month_dropped(make_settings) -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"date": "2026-08-01T00:00:00Z", "count": "100", "share": 0.001},
                    {"date": "2026-09-01T00:00:00Z", "count": "120"},
                    {"date": "2026-10-01T00:00:00Z", "count": "50"},
                ]
            },
        )

    source, _ = make_source(make_settings, handler, wordstat_dynamics_months=12)
    observations = await source.monthly_dynamics("генератор счетов")
    assert seen["body"]["period"] == "PERIOD_MONTHLY"
    assert seen["body"]["fromDate"] == "2025-10-01T00:00:00Z"
    assert seen["body"]["toDate"] == "2026-09-30T00:00:00Z"
    assert [(o.period_start, o.count) for o in observations] == [
        (date(2026, 8, 1), 100),
        (date(2026, 9, 1), 120),
    ]


async def test_retries_on_429_and_5xx(make_settings) -> None:
    responses = [
        httpx.Response(429, headers={"Retry-After": "3"}, text="quota"),
        httpx.Response(503, text="unavailable"),
        httpx.Response(200, json={"totalCount": "10", "results": []}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    source, sleep = make_source(make_settings, handler)
    observations = await source.related("счет", None)
    assert observations[0].count == 10
    assert sleep.calls[0] == 3.0  # учли Retry-After
    assert len([c for c in sleep.calls if c >= 1]) == 2
    assert source.requests_made == 3


async def test_gives_up_after_max_retries(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    source, _sleep = make_source(make_settings, handler)
    with pytest.raises(SourceTemporaryError):
        await source.related("счет", None)
    assert source.requests_made == 4  # 1 + 3 повтора


async def test_auth_error_not_retried_and_secret_not_leaked(make_settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text='{"message": "permission denied"}')

    source, _sleep = make_source(make_settings, handler)
    with pytest.raises(SourceAuthError) as exc:
        await source.related("счет", None)
    assert source.requests_made == 1
    assert SECRET not in str(exc.value)


async def test_bad_request_dynamics_falls_back_to_12_months(make_settings) -> None:
    bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        if body["fromDate"].startswith("2024"):
            return httpx.Response(400, text="invalid fromDate")
        return httpx.Response(200, json={"results": []})

    source, _ = make_source(make_settings, handler, wordstat_dynamics_months=25)
    assert await source.monthly_dynamics("счет") == []
    assert await source.monthly_dynamics("акт") == []
    assert [b["fromDate"][:7] for b in bodies] == ["2024-09", "2025-10", "2025-10"]


async def test_non_json_response(make_settings) -> None:
    source, _ = make_source(make_settings, lambda r: httpx.Response(200, text="<html>"))
    with pytest.raises(SourceRequestError):
        await source.related("счет", None)


def test_requires_configuration(make_settings) -> None:
    with pytest.raises(ValueError):
        WordstatSource(make_settings())
