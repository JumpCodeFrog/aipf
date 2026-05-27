from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from aipf import client as client_module
from aipf.client import AsyncProxyClient
from aipf.models import ApiStyle
from tests.conftest import API_KEY, BASE_URL


async def test_list_models_openai(
    openai_client: AsyncProxyClient,
    sample_models_list_openai: dict[str, Any],
) -> None:
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/v1/models").mock(
            return_value=httpx.Response(200, json=sample_models_list_openai)
        )
        result = await openai_client.list_models()

    assert result.status_code == 200
    assert result.ids == ["gpt-4o", "gpt-4o-mini"]
    assert len(result.calls) == 1


async def test_chat_openai_extracts_content(
    openai_client: AsyncProxyClient,
    sample_openai_chat_response: dict[str, Any],
) -> None:
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=sample_openai_chat_response)
        )
        result = await openai_client.chat("gpt-test", "Hi")

    assert route.called
    assert result.text == "Hello from OpenAI"
    sent_request = route.calls.last.request
    assert sent_request.headers["authorization"].startswith("Bearer ")
    body = sent_request.read()
    assert b'"model":"gpt-test"' in body or b'"model": "gpt-test"' in body


async def test_chat_retries_on_429(
    monkeypatch: pytest.MonkeyPatch,
    openai_client: AsyncProxyClient,
    sample_openai_chat_response: dict[str, Any],
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(client_module.asyncio, "sleep", fake_sleep)

    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/v1/chat/completions")
        route.side_effect = [
            httpx.Response(429, headers={"Retry-After": "2"}),
            httpx.Response(200, json=sample_openai_chat_response),
        ]
        result = await openai_client.chat("gpt-test", "Hi")

    assert result.status_code == 200
    assert len(result.calls) == 2
    assert result.calls[0].status_code == 429
    assert result.calls[1].status_code == 200
    assert result.calls[1].attempt == 2
    assert sleeps == [2.0]


async def test_chat_retries_transient_status_with_capped_retry_after(
    monkeypatch: pytest.MonkeyPatch,
    openai_client: AsyncProxyClient,
    sample_openai_chat_response: dict[str, Any],
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(client_module.asyncio, "sleep", fake_sleep)

    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/v1/chat/completions")
        route.side_effect = [
            httpx.Response(500),
            httpx.Response(502, headers={"Retry-After": "120"}),
            httpx.Response(200, json=sample_openai_chat_response),
        ]
        result = await openai_client.chat("gpt-test", "Hi")

    assert result.status_code == 200
    assert [call.status_code for call in result.calls] == [500, 502, 200]
    assert [call.attempt for call in result.calls] == [1, 2, 3]
    assert sleeps == [0.25, client_module.MAX_RETRY_SLEEP_S]


async def test_chat_retries_retryable_network_errors(
    monkeypatch: pytest.MonkeyPatch,
    openai_client: AsyncProxyClient,
    sample_openai_chat_response: dict[str, Any],
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(client_module.asyncio, "sleep", fake_sleep)

    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/v1/chat/completions")
        route.side_effect = [
            httpx.ConnectTimeout("connect timed out"),
            httpx.Response(200, json=sample_openai_chat_response),
        ]
        result = await openai_client.chat("gpt-test", "Hi")

    assert result.status_code == 200
    assert len(result.calls) == 2
    assert result.calls[0].status_code is None
    assert result.calls[0].error is not None
    assert result.calls[1].status_code == 200
    assert sleeps == [0.25]


async def test_chat_does_not_retry_permanent_400(
    monkeypatch: pytest.MonkeyPatch,
    openai_client: AsyncProxyClient,
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(client_module.asyncio, "sleep", fake_sleep)

    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/v1/chat/completions").mock(return_value=httpx.Response(400))
        result = await openai_client.chat("gpt-test", "Hi")

    assert route.call_count == 1
    assert result.status_code == 400
    assert len(result.calls) == 1
    assert sleeps == []


async def test_detect_style_openai(
    sample_models_list_openai: dict[str, Any],
) -> None:
    async with AsyncProxyClient(BASE_URL, API_KEY, api_style="auto") as client:
        with respx.mock(base_url=BASE_URL) as router:
            router.get("/v1/models").mock(
                return_value=httpx.Response(200, json=sample_models_list_openai)
            )
            style = await client.ensure_style()
    assert style is ApiStyle.OPENAI


async def test_chat_stream_openai(
    openai_client: AsyncProxyClient,
    openai_stream_body: str,
) -> None:
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                content=openai_stream_body.encode("utf-8"),
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await openai_client.chat_stream("gpt-test", "Hi")

    assert result.sse_format_valid is True
    assert result.chunk_count >= 3
    assert "Hello" in result.accumulated_text
    assert "world" in result.accumulated_text


async def test_chat_stream_does_not_retry_rate_limit(
    monkeypatch: pytest.MonkeyPatch,
    openai_client: AsyncProxyClient,
) -> None:
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(client_module.asyncio, "sleep", fake_sleep)

    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/v1/chat/completions").mock(
            return_value=httpx.Response(
                429,
                content=b"rate limited",
                headers={"Retry-After": "1"},
            )
        )
        result = await openai_client.chat_stream("gpt-test", "Hi")

    assert route.call_count == 1
    assert result.calls[0].status_code == 429
    assert result.chunk_count == 0
    assert result.sse_format_valid is False
    assert sleeps == []


async def test_chat_stream_redacts_api_key_in_sample_chunks() -> None:
    secret = "sk-test-secret-value"
    body = (
        'data: {"choices":[{"delta":{"content":"'
        + secret
        + '"},"index":0}]}\n\n'
        "data: [DONE]\n\n"
    )
    async with AsyncProxyClient(BASE_URL, secret, api_style=ApiStyle.OPENAI) as client:
        with respx.mock(base_url=BASE_URL) as router:
            router.post("/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    content=body.encode("utf-8"),
                    headers={"content-type": "text/event-stream"},
                )
            )
            result = await client.chat_stream("gpt-test", "Hi")

    assert secret in result.accumulated_text
    assert secret not in "".join(result.sample_chunks)
    assert "***" in "".join(result.sample_chunks)
