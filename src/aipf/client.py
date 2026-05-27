from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Literal

import httpx

from aipf.debug_trace import DebugTracer, NullDebugTracer
from aipf.models import ApiStyle, HttpCallLog
from aipf.redaction import redact_text

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 512
ANTHROPIC_VERSION = "2023-06-01"
RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
MAX_RETRIES = 2
BACKOFF_BASE_MS = 250
MAX_RETRY_SLEEP_S = 30.0
RETRY_AFTER_HEADER = "retry-after"


@dataclass
class ListModelsResult:
    ids: list[str]
    raw_json: dict[str, Any] | None
    raw_text: str
    status_code: int
    calls: list[HttpCallLog] = field(default_factory=list)


@dataclass
class ChatResult:
    text: str
    raw_json: dict[str, Any] | None
    raw_text: str
    status_code: int
    calls: list[HttpCallLog] = field(default_factory=list)


@dataclass
class StreamResult:
    chunk_count: int
    first_chunk_ms: float
    total_ms: float
    sample_chunks: list[str]
    sse_format_valid: bool
    accumulated_text: str
    calls: list[HttpCallLog] = field(default_factory=list)


class ProxyClientError(RuntimeError):
    pass


@dataclass
class _StreamTraceState:
    trace_id: str
    style: ApiStyle
    start: float
    chunk_count: int = 0
    first_chunk_ms: float = 0.0
    accumulated: list[str] = field(default_factory=list)
    sample_chunks: list[str] = field(default_factory=list)
    sse_format_valid: bool = False
    any_data_line: bool = False


class AsyncProxyClient:
    """HTTP client with adapters for OpenAI Chat Completions and Anthropic Messages."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_style: ApiStyle | Literal["auto"] = "auto",
        timeout_s: int = 90,
        debug_tracer: DebugTracer | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._declared_style: ApiStyle | Literal["auto"] = api_style
        self._detected_style: ApiStyle | None = (
            api_style if isinstance(api_style, ApiStyle) else None
        )
        self._debug = debug_tracer or NullDebugTracer()
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=float(timeout_s), write=10.0, pool=10.0),
        )
        declared = api_style.value if isinstance(api_style, ApiStyle) else api_style
        self._trace(
            "client.init",
            base_url=self._redact(self.base_url),
            declared_style=declared,
            timeout_s=timeout_s,
        )

    async def __aenter__(self) -> AsyncProxyClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    def trace(self, event: str, **fields: object) -> None:
        self._debug.emit(event, **fields)

    def _trace(self, event: str, **fields: object) -> None:
        self.trace(event, **fields)

    @property
    def style(self) -> ApiStyle:
        if self._detected_style is None:
            raise ProxyClientError("API style not detected yet; call ensure_style() first")
        return self._detected_style

    async def ensure_style(self) -> ApiStyle:
        if self._detected_style is not None:
            self._trace(
                "provider.selection.cached",
                style=self._detected_style.value,
            )
            return self._detected_style
        self._trace("provider.selection.start", declared_style=self._declared_style)
        detected, _calls = await self._detect_style()
        self._detected_style = detected
        self._trace("provider.selection.done", style=detected.value)
        return detected

    async def _detect_style(self) -> tuple[ApiStyle, list[HttpCallLog]]:
        """Probe /v1/models with both authentication schemes and pick a style."""
        headers = self._auth_headers_both()
        result = await self._request_with_retry("GET", "/v1/models", headers=headers)
        calls = result.calls
        if result.status_code and 200 <= result.status_code < 300:
            payload = _safe_json(result.text)
            style = _infer_style_from_models_payload(payload)
            ids = _extract_model_ids(payload)
            self._trace(
                "provider.selection.infer",
                status=result.status_code,
                model_count=len(ids),
                style=style.value,
                reason="all_models_anthropic" if style is ApiStyle.ANTHROPIC else "fallback_openai",
            )
            logger.info(
                "style.detected",
                extra={"event": "style.detected", "style": style.value, "via": "models"},
            )
            return style, calls
        self._trace(
            "provider.selection.fallback",
            status=result.status_code,
            style=ApiStyle.OPENAI.value,
            reason="models_probe_failed",
        )
        logger.warning(
            "style.detect.failed",
            extra={
                "event": "style.detect.failed",
                "status": result.status_code,
                "fallback": ApiStyle.OPENAI.value,
            },
        )
        return ApiStyle.OPENAI, calls

    async def list_models(self) -> ListModelsResult:
        style = await self.ensure_style()
        headers = self._auth_headers(style)
        self._trace("models.list.start", style=style.value)
        result = await self._request_with_retry("GET", "/v1/models", headers=headers)
        payload = _safe_json(result.text)
        ids = _extract_model_ids(payload)
        self._trace(
            "models.list.done",
            style=style.value,
            status=result.status_code,
            model_count=len(ids),
        )
        return ListModelsResult(
            ids=ids,
            raw_json=payload,
            raw_text=result.text,
            status_code=result.status_code or 0,
            calls=result.calls,
        )

    async def chat(
        self,
        model: str,
        prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> ChatResult:
        style = await self.ensure_style()
        endpoint, payload, headers = self._build_chat_request(style, model, prompt, max_tokens)
        self._trace(
            "chat.request.build",
            style=style.value,
            endpoint=endpoint,
            model=self._redact(model),
            max_tokens=max_tokens,
            stream=False,
        )
        result = await self._request_with_retry(
            "POST", endpoint, headers=headers, json_body=payload
        )
        body = _safe_json(result.text)
        text = _extract_chat_text(style, body)
        self._trace(
            "chat.response.extract",
            style=style.value,
            status=result.status_code,
            text_chars=len(text),
        )
        return ChatResult(
            text=text,
            raw_json=body,
            raw_text=result.text,
            status_code=result.status_code or 0,
            calls=result.calls,
        )

    async def chat_stream(
        self,
        model: str,
        prompt: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_sample_chunks: int = 10,
    ) -> StreamResult:
        style = await self.ensure_style()
        endpoint, payload, headers = self._build_chat_request(
            style, model, prompt, max_tokens, stream=True
        )
        headers = {**headers, "Accept": "text/event-stream"}
        url = f"{self.base_url}{endpoint}"
        trace_id = f"stream-{id(payload):x}"
        state = _StreamTraceState(trace_id=trace_id, style=style, start=time.perf_counter())
        self._trace(
            "stream.request.build",
            trace_id=trace_id,
            style=style.value,
            endpoint=endpoint,
            model=self._redact(model),
            max_tokens=max_tokens,
        )

        status_code = 0
        error: str | None = None
        attempt_calls: list[HttpCallLog] = []

        logger.info(
            "request.start",
            extra={
                "event": "request.start",
                "method": "POST",
                "url": self._redact(url),
                "stream": True,
            },
        )
        self._trace(
            "http.request.start",
            trace_id=trace_id,
            method="POST",
            url=self._redact(url),
            attempt=1,
            stream=True,
        )

        try:
            async with self._client.stream(
                "POST", url, headers=headers, json=payload
            ) as response:
                status_code = response.status_code
                self._trace(
                    "http.response.headers",
                    trace_id=trace_id,
                    status=status_code,
                    request_id=_extract_request_id(response.headers),
                    stream=True,
                )
                async for raw_line in response.aiter_lines():
                    if not raw_line:
                        continue
                    if self._handle_stream_line(raw_line, state, max_sample_chunks):
                        break
        except httpx.HTTPError as exc:
            error = self._redact(f"{type(exc).__name__}: {exc}")
            self._trace(
                "http.request.error",
                trace_id=trace_id,
                method="POST",
                url=self._redact(url),
                error=error,
                stream=True,
            )
            logger.warning(
                "request.error",
                extra={"event": "request.error", "url": self._redact(url), "error": error},
            )

        total_ms = (time.perf_counter() - state.start) * 1000
        attempt_calls.append(
            HttpCallLog(
                method="POST",
                url=self._redact(url),
                status_code=status_code or None,
                latency_ms=total_ms,
                attempt=1,
                error=error,
            )
        )
        logger.info(
            "request.end",
            extra={
                "event": "request.end",
                "url": self._redact(url),
                "status": status_code,
                "latency_ms": round(total_ms, 2),
                "chunks": state.chunk_count,
                "stream": True,
            },
        )
        self._trace(
            "http.request.end",
            trace_id=trace_id,
            method="POST",
            url=self._redact(url),
            status=status_code or None,
            latency_ms=round(total_ms, 2),
            chunks=state.chunk_count,
            stream=True,
            error=error,
        )

        if not state.any_data_line:
            state.sse_format_valid = False

        return StreamResult(
            chunk_count=state.chunk_count,
            first_chunk_ms=state.first_chunk_ms,
            total_ms=total_ms,
            sample_chunks=state.sample_chunks,
            sse_format_valid=state.sse_format_valid,
            accumulated_text="".join(state.accumulated),
            calls=attempt_calls,
        )

    def _handle_stream_line(
        self,
        raw_line: str,
        state: _StreamTraceState,
        max_sample_chunks: int,
    ) -> bool:
        if raw_line.startswith("data:"):
            return self._handle_stream_data_line(raw_line, state, max_sample_chunks)
        if raw_line.startswith("event:"):
            state.sse_format_valid = True
            if len(state.sample_chunks) < max_sample_chunks:
                state.sample_chunks.append(self._redact(raw_line[:200]))
            self._trace(
                "stream.event",
                trace_id=state.trace_id,
                event_line=self._redact(raw_line[:80]),
            )
        return False

    def _handle_stream_data_line(
        self,
        raw_line: str,
        state: _StreamTraceState,
        max_sample_chunks: int,
    ) -> bool:
        state.any_data_line = True
        state.sse_format_valid = True
        data_part = raw_line[5:].strip()
        if data_part == "[DONE]":
            self._trace(
                "stream.chunk.done",
                trace_id=state.trace_id,
                chunk_index=state.chunk_count,
            )
            return True
        if state.chunk_count == 0:
            state.first_chunk_ms = (time.perf_counter() - state.start) * 1000
        state.chunk_count += 1
        chunk_text = _extract_stream_chunk_text(state.style, data_part)
        if chunk_text:
            state.accumulated.append(chunk_text)
        if len(state.sample_chunks) < max_sample_chunks:
            state.sample_chunks.append(self._redact(raw_line[:200]))
        self._trace(
            "stream.chunk",
            trace_id=state.trace_id,
            chunk_index=state.chunk_count,
            text_chars=len(chunk_text),
            first_chunk_ms=round(state.first_chunk_ms, 2)
            if state.chunk_count == 1
            else None,
        )
        return False

    def _auth_headers(self, style: ApiStyle) -> dict[str, str]:
        if style is ApiStyle.OPENAI:
            return {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        return {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _auth_headers_both(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Accept": "application/json",
        }

    def _redact(self, text: str) -> str:
        return redact_text(text, (self._api_key,))

    def _build_chat_request(
        self,
        style: ApiStyle,
        model: str,
        prompt: str,
        max_tokens: int,
        stream: bool = False,
    ) -> tuple[str, dict[str, Any], dict[str, str]]:
        if style is ApiStyle.OPENAI:
            return (
                "/v1/chat/completions",
                _build_openai_payload(model, prompt, max_tokens, stream),
                self._auth_headers(ApiStyle.OPENAI),
            )
        return (
            "/v1/messages",
            _build_anthropic_payload(model, prompt, max_tokens, stream),
            self._auth_headers(ApiStyle.ANTHROPIC),
        )

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
    ) -> _AttemptResult:
        url = f"{self.base_url}{path}"
        calls: list[HttpCallLog] = []
        last_text = ""
        last_status: int | None = None
        trace_id = f"req-{time.perf_counter_ns():x}"

        for attempt in range(1, MAX_RETRIES + 2):
            start = time.perf_counter()
            logger.info(
                "request.start",
                extra={
                    "event": "request.start",
                    "method": method,
                    "url": self._redact(url),
                    "attempt": attempt,
                },
            )
            error: str | None = None
            exc: httpx.HTTPError | None = None
            status_code: int | None = None
            text = ""
            request_id: str | None = None
            response_headers: httpx.Headers | None = None
            self._trace(
                "http.request.start",
                trace_id=trace_id,
                method=method,
                url=self._redact(url),
                path=path,
                attempt=attempt,
                stream=False,
            )
            try:
                response = await self._client.request(
                    method, url, headers=headers, json=json_body
                )
                status_code = response.status_code
                text = response.text
                response_headers = response.headers
                request_id = _extract_request_id(response.headers)
            except httpx.HTTPError as caught:
                exc = caught
                error = self._redact(f"{type(exc).__name__}: {exc}")
                self._trace(
                    "http.request.error",
                    trace_id=trace_id,
                    method=method,
                    url=self._redact(url),
                    attempt=attempt,
                    error=error,
                )

            latency_ms = (time.perf_counter() - start) * 1000
            calls.append(
                HttpCallLog(
                    method=method,
                    url=self._redact(url),
                    status_code=status_code,
                    latency_ms=latency_ms,
                    attempt=attempt,
                    request_id=self._redact(request_id) if request_id else None,
                    error=error,
                )
            )
            logger.info(
                "request.end",
                extra={
                    "event": "request.end",
                    "method": method,
                    "url": self._redact(url),
                    "status": status_code,
                    "latency_ms": round(latency_ms, 2),
                    "attempt": attempt,
                    "error": error,
                },
            )
            self._trace(
                "http.request.end",
                trace_id=trace_id,
                method=method,
                url=self._redact(url),
                path=path,
                status=status_code,
                latency_ms=round(latency_ms, 2),
                attempt=attempt,
                request_id=self._redact(request_id) if request_id else None,
                stream=False,
                error=error,
            )
            last_text = text
            last_status = status_code

            retry = _retry_decision(
                attempt=attempt,
                status_code=status_code,
                response_headers=response_headers,
                error=exc,
            )
            if retry is None:
                return _AttemptResult(text=text, status_code=status_code, calls=calls)

            self._trace(
                "http.retry",
                trace_id=trace_id,
                method=method,
                url=self._redact(url),
                next_attempt=attempt + 1,
                sleep_s=retry.delay_s,
                reason=retry.reason,
                status=status_code,
                error=error,
            )
            logger.info(
                "request.retry",
                extra={
                    "event": "request.retry",
                    "url": self._redact(url),
                    "next_attempt": attempt + 1,
                    "sleep_s": retry.delay_s,
                    "reason": retry.reason,
                    "status": status_code,
                    "error": error,
                },
            )
            await asyncio.sleep(retry.delay_s)

        return _AttemptResult(text=last_text, status_code=last_status, calls=calls)


@dataclass
class _AttemptResult:
    text: str
    status_code: int | None
    calls: list[HttpCallLog]


@dataclass(frozen=True)
class _RetryDecision:
    delay_s: float
    reason: str


def _retry_decision(
    attempt: int,
    status_code: int | None,
    response_headers: httpx.Headers | None,
    error: httpx.HTTPError | None,
) -> _RetryDecision | None:
    if attempt > MAX_RETRIES:
        return None
    if error is not None:
        if not _is_retryable_http_error(error):
            return None
        return _RetryDecision(delay_s=_backoff_delay_s(attempt), reason=type(error).__name__)
    if status_code not in RETRY_STATUSES:
        return None
    retry_after_value = (
        response_headers.get(RETRY_AFTER_HEADER) if response_headers is not None else None
    )
    retry_after = _parse_retry_after(retry_after_value)
    if retry_after is not None:
        return _RetryDecision(delay_s=retry_after, reason=RETRY_AFTER_HEADER)
    return _RetryDecision(delay_s=_backoff_delay_s(attempt), reason=f"http_{status_code}")


def _extract_request_id(headers: httpx.Headers) -> str | None:
    request_id = (
        headers.get("x-request-id")
        or headers.get("request-id")
        or headers.get("x-amzn-requestid")
        or headers.get("cf-ray")
    )
    return request_id if isinstance(request_id, str) else None


def _is_retryable_http_error(error: httpx.HTTPError) -> bool:
    return isinstance(
        error,
        httpx.TimeoutException | httpx.NetworkError | httpx.RemoteProtocolError,
    )


def _backoff_delay_s(attempt: int) -> float:
    delay = (BACKOFF_BASE_MS * (2 ** (attempt - 1))) / 1000
    return _cap_retry_delay_s(delay)


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        delay = float(stripped)
    except ValueError:
        date_delay = _retry_after_http_date_delay_s(stripped)
        if date_delay is None:
            return None
        delay = date_delay
    return _cap_retry_delay_s(delay)


def _cap_retry_delay_s(delay: float) -> float:
    if delay < 0:
        return 0.0
    if delay > MAX_RETRY_SLEEP_S:
        return MAX_RETRY_SLEEP_S
    return delay


def _retry_after_http_date_delay_s(value: str) -> float | None:
    try:
        retry_at = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    return (retry_at - datetime.now(UTC)).total_seconds()


def _build_openai_payload(
    model: str, prompt: str, max_tokens: int, stream: bool
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": stream,
    }


def _build_anthropic_payload(
    model: str, prompt: str, max_tokens: int, stream: bool
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "stream": stream,
    }


def _safe_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except (ValueError, TypeError):
        return None


def _extract_model_ids(payload: dict[str, Any] | None) -> list[str]:
    if not payload:
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    ids: list[str] = []
    for item in data:
        if isinstance(item, dict):
            candidate = item.get("id") or item.get("name")
            if isinstance(candidate, str):
                ids.append(candidate)
    return ids


def _infer_style_from_models_payload(payload: dict[str, Any] | None) -> ApiStyle:
    if not payload:
        return ApiStyle.OPENAI
    ids = _extract_model_ids(payload)
    if ids and all("claude" in mid.lower() or "anthropic" in mid.lower() for mid in ids):
        return ApiStyle.ANTHROPIC
    return ApiStyle.OPENAI


def _extract_chat_text(style: ApiStyle, body: dict[str, Any] | None) -> str:
    if not body:
        return ""
    if style is ApiStyle.OPENAI:
        choices = body.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content
        return ""
    # Anthropic
    content = body.get("content")
    if isinstance(content, list):
        chunks: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        return "".join(chunks)
    return ""


def _extract_stream_chunk_text(style: ApiStyle, data_part: str) -> str:
    try:
        data = json.loads(data_part)
    except (ValueError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    if style is ApiStyle.OPENAI:
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str):
                    return content
        return ""
    # Anthropic
    if data.get("type") == "content_block_delta":
        delta = data.get("delta")
        if isinstance(delta, dict):
            text = delta.get("text")
            if isinstance(text, str):
                return text
    return ""

# expose internal helpers for tests
__all__ = [
    "AsyncProxyClient",
    "ChatResult",
    "ListModelsResult",
    "ProxyClientError",
    "StreamResult",
    "_extract_chat_text",
    "_extract_stream_chunk_text",
    "_infer_style_from_models_payload",
    "_parse_retry_after",
]
