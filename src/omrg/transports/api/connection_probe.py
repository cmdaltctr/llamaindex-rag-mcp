"""One model-list request per provider URL, reduced to a fixed reason (design D13).

The result is ``{reachable, reason}`` and nothing else. ``reason`` is one
of ``refused``, ``timeout``, ``unauthorised``, ``http-<status>`` or
``not-configured``, and ``None`` when the provider answered. Response
bodies are never read, and exception text is never returned or logged, so
a key sent in a header cannot reach a client or the log through this code.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

#: Seconds one request may take (connect, answer and total).
TEST_TIMEOUT_SECONDS = 5.0


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
