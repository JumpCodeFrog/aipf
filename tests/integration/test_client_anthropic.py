from __future__ import annotations

from typing import Any

import httpx
import respx

from aipf.client import AsyncProxyClient
from aipf.models import ApiStyle
from tests.conftest import API_KEY, BASE_URL


async def test_chat_anthropic_extracts_content(
    anthropic_client: AsyncProxyClient,
    sample_anthropic_chat_response: dict[str, Any],
) -> None:
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/v1/messages").mock(
            return_value=httpx.Response(200, json=sample_anthropic_chat_response)
        )
        result = await anthropic_client.chat("claude-test", "Hi")

    assert route.called
    assert result.text == "Hello from Claude"
    sent_request = route.calls.last.request
    assert sent_request.headers["x-api-key"] == API_KEY
    assert sent_request.headers["anthropic-version"]


async def test_detect_style_anthropic(
    sample_models_list_anthropic: dict[str, Any],
) -> None:
    async with AsyncProxyClient(BASE_URL, API_KEY, api_style="auto") as client:
        with respx.mock(base_url=BASE_URL) as router:
            router.get("/v1/models").mock(
                return_value=httpx.Response(200, json=sample_models_list_anthropic)
            )
            style = await client.ensure_style()
    assert style is ApiStyle.ANTHROPIC


async def test_chat_stream_anthropic(
    anthropic_client: AsyncProxyClient,
    anthropic_stream_body: str,
) -> None:
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/v1/messages").mock(
            return_value=httpx.Response(
                200,
                content=anthropic_stream_body.encode("utf-8"),
                headers={"content-type": "text/event-stream"},
            )
        )
        result = await anthropic_client.chat_stream("claude-test", "Hi")

    assert result.sse_format_valid is True
    assert result.chunk_count >= 2
    assert result.accumulated_text == "Hello world"
