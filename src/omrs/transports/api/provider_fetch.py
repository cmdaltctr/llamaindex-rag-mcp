"""One provider read on request, decoded and parsed (add-chat-reasoning-and-usage D5).

The reasoning-level and credit routes use this. It sends one ``GET`` built
from a descriptor's :class:`~omrs.core.providers.llm.connection.ProviderLookup`
and returns the parsed value, or ``None`` on any failure. No exception text,
header or response body is logged or returned, so a key in a header cannot
reach a client or the log through this code.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from ...core.providers.llm.connection import ProviderLookup

#: Seconds one read may take in total.
FETCH_TIMEOUT_SECONDS = 10.0
#: Most bytes of a body the server reads (the catalogue is about 0.8 MB).
BODY_LIMIT = 8 * 1024 * 1024


async def _read(url: str, headers: dict[str, str]) -> bytes | None:
    """Return the 2xx body of *url*, or ``None`` for another status or an oversize body."""
    timeout = httpx.Timeout(FETCH_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        async with client.stream("GET", url, headers=headers) as response:
            if not 200 <= response.status_code < 300:
                return None
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > BODY_LIMIT:
                    return None
                chunks.append(chunk)
    return b"".join(chunks)


async def fetch_parsed(lookup: ProviderLookup, settings: Any) -> Any:
    """Send the read of *lookup* and return its parsed value, or ``None``.

    Args:
        lookup: The descriptor hook (request and parser).
        settings: Settings the request is built from.

    Returns:
        The parser's result, or ``None`` when nothing is configured, the
        request fails, or the body cannot be decoded.
    """
    target = lookup.target(settings)
    if not target.urls:
        return None
    try:
        async with asyncio.timeout(FETCH_TIMEOUT_SECONDS):
            body = await _read(target.urls[0], target.headers)
    except Exception:  # noqa: BLE001 - the text may hold the URL or key; report nothing
        return None
    if body is None:
        return None
    try:
        return lookup.parse(json.loads(body))
    except Exception:  # noqa: BLE001 - a malformed body reads as "no data"
        return None
