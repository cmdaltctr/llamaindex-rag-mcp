"""One model-list request per provider URL, reduced to a fixed reason (design D13).

The result is ``{reachable, reason}`` and nothing else. ``reason`` is one
of ``refused``, ``timeout``, ``unauthorised``, ``http-<status>`` or
``not-configured``, and ``None`` when the provider answered. Response
bodies are never read, and exception text is never returned or logged, so
a key sent in a header cannot reach a client or the log through this code.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import httpx

#: Seconds one request may take (connect, answer and total).
TEST_TIMEOUT_SECONDS = 5.0
#: Most bytes of a model-list body the server reads.
MODELS_BODY_LIMIT = 8 * 1024 * 1024
#: Most model names returned, and the length bounds of one name.
MAX_MODELS = 1000
MAX_MODEL_NAME_CHARS = 200


def reachability(reachable: bool, reason: str | None) -> dict[str, Any]:
    """Return the test result body."""
    return {"reachable": reachable, "reason": reason}


async def _request(client: httpx.AsyncClient, url: str, headers: dict[str, str]) -> str | None:
    """Return ``None`` when *url* answered with 2xx, else the failure reason."""
    try:
        async with asyncio.timeout(TEST_TIMEOUT_SECONDS):
            async with client.stream("GET", url, headers=headers) as response:
                status = response.status_code
    except (TimeoutError, httpx.TimeoutException):
        return "timeout"
    except Exception:
        # Refused, unreachable, reset or malformed: the client learns only that
        # the provider could not be reached. The text may hold the URL or key.
        return "refused"
    if 200 <= status < 300:
        return None
    if status in (401, 403):
        return "unauthorised"
    return f"http-{status}"


async def probe(urls: tuple[str, ...], headers: dict[str, str]) -> dict[str, Any]:
    """Send one ``GET`` to each URL, one after another, and report the first failure.

    Args:
        urls: Model-list URLs. None means the provider is not configured and
            nothing is sent.
        headers: Request headers (the OpenRouter key, for that provider).

    Returns:
        ``{"reachable": bool, "reason": str | None}``.
    """
    if not urls:
        return reachability(False, "not-configured")
    timeout = httpx.Timeout(TEST_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for url in urls:
            reason = await _request(client, url, headers)
            if reason is not None:
                return reachability(False, reason)
    return reachability(True, None)


def _clean_names(names: list[str]) -> list[str]:
    """Return the distinct names of 1 to 200 printable characters, sorted."""
    keep = {
        name
        for name in names
        if isinstance(name, str) and 1 <= len(name) <= MAX_MODEL_NAME_CHARS and name.isprintable()
    }
    return sorted(keep)


async def _read_models(
    client: httpx.AsyncClient, url: str, headers: dict[str, str]
) -> tuple[int, bytes, bool]:
    """Return ``(status, body, over_limit)``; the body stops at the read limit."""
    async with client.stream("GET", url, headers=headers) as response:
        status = response.status_code
        if not 200 <= status < 300:
            return status, b"", False
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MODELS_BODY_LIMIT:
                return status, b"", True
            chunks.append(chunk)
    return status, b"".join(chunks), False


def _models_result(
    reachable: bool, reason: str | None, models: list[str] | None = None, truncated: bool = False
) -> dict[str, Any]:
    return {**reachability(reachable, reason), "models": models or [], "truncated": truncated}


async def list_models(
    urls: tuple[str, ...],
    headers: dict[str, str],
    parse: Callable[[object], list[str]],
) -> dict[str, Any]:
    """Send one request for the model list and return only the model names.

    Reads at most 8 MiB, keeps at most 1,000 valid names and sorts them.
    Nothing else of the body, and no exception text, is returned.

    Returns:
        ``{"reachable", "reason", "models", "truncated"}``.
    """
    if not urls:
        return _models_result(False, "not-configured")
    timeout = httpx.Timeout(TEST_TIMEOUT_SECONDS)
    try:
        async with asyncio.timeout(TEST_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                status, body, over = await _read_models(client, urls[0], headers)
    except (TimeoutError, httpx.TimeoutException):
        return _models_result(False, "timeout")
    except Exception:
        return _models_result(False, "refused")
    if status in (401, 403):
        return _models_result(False, "unauthorised")
    if not 200 <= status < 300:
        return _models_result(False, f"http-{status}")
    if over:
        return _models_result(True, None, [], True)
    try:
        names = _clean_names(parse(json.loads(body)))
    except Exception:
        names = []
    return _models_result(True, None, names[:MAX_MODELS], len(names) > MAX_MODELS)
