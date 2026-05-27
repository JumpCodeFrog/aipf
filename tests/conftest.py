from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from aipf.client import AsyncProxyClient
from aipf.models import ApiStyle

BASE_URL = "https://mock.example.com"
API_KEY = "test-key-do-not-use"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Strip AIPF_* / legacy env vars and run from a clean tmp CWD so no real .env is read."""
    for var in (
        "AIPF_BASE_URL",
        "AIPF_API_KEY",
        "AIPF_MODEL",
        "AIPF_API_STYLE",
        "AIPF_TIMEOUT",
        "AIPF_LATENCY_ROUNDS",
        "BASE_URL",
        "API_KEY",
        "MODEL",
        "TIMEOUT",
        "API_STYLE",
        "LATENCY_ROUNDS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def sample_openai_chat_response() -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "gpt-test",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Hello from OpenAI"},
                "finish_reason": "stop",
            }
        ],
    }


@pytest.fixture
def sample_anthropic_chat_response() -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-test",
        "content": [{"type": "text", "text": "Hello from Claude"}],
        "stop_reason": "end_turn",
    }


@pytest.fixture
def sample_models_list_openai() -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {"id": "gpt-4o", "object": "model"},
            {"id": "gpt-4o-mini", "object": "model"},
        ],
    }


@pytest.fixture
def sample_models_list_anthropic() -> dict[str, Any]:
    return {
        "data": [
            {"id": "claude-haiku-4-5-20251001", "type": "model"},
            {"id": "claude-opus-4-7", "type": "model"},
        ],
    }


@pytest.fixture
def openai_stream_body() -> str:
    chunks = [
        '{"choices":[{"delta":{"role":"assistant"},"index":0}]}',
        '{"choices":[{"delta":{"content":"Hello"},"index":0}]}',
        '{"choices":[{"delta":{"content":" world"},"index":0}]}',
        '{"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}',
    ]
    sse = "\n".join(f"data: {c}" for c in chunks)
    return sse + "\n\ndata: [DONE]\n\n"


@pytest.fixture
def anthropic_stream_body() -> str:
    delta_hello = '{"type":"content_block_delta","delta":{"text":"Hello"}}'
    delta_world = '{"type":"content_block_delta","delta":{"text":" world"}}'
    parts = [
        f"event: content_block_delta\ndata: {delta_hello}",
        f"event: content_block_delta\ndata: {delta_world}",
        'event: message_stop\ndata: {"type":"message_stop"}',
    ]
    return "\n\n".join(parts) + "\n\n"


@pytest.fixture
async def openai_client() -> AsyncIterator[AsyncProxyClient]:
    async with AsyncProxyClient(
        base_url=BASE_URL,
        api_key=API_KEY,
        api_style=ApiStyle.OPENAI,
    ) as c:
        yield c


@pytest.fixture
async def anthropic_client() -> AsyncIterator[AsyncProxyClient]:
    async with AsyncProxyClient(
        base_url=BASE_URL,
        api_key=API_KEY,
        api_style=ApiStyle.ANTHROPIC,
    ) as c:
        yield c
