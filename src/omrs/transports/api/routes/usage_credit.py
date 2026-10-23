"""Remaining credit of the Chat provider key (add-chat-reasoning-and-usage D5).

``GET /v1/usage/credit`` reads the key's spending limit when the Chat
provider publishes one (OpenRouter ``GET /api/v1/key``). Nothing is cached,
because the web calls it once per finished answer. A provider without credit
data, a missing key, a key with no limit and any failure all give
``{"available": false}``. The key never appears in the answer or the log.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from ....compose_providers import provider_settings as _provider_settings
from ....core.providers.llm import registry as llm_registry
from ..engine_access import ReadScope, RuntimeDep, admitted
from ..provider_fetch import fetch_parsed
from .chat_settings import provider_values_of
from .graphs import ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")


@router.get("/usage/credit", operation_id="getUsageCredit")
async def get_usage_credit(_: ReadScope, runtime: RuntimeDep) -> Response:
    """Return the credit left on the Chat provider key.

    The body is `{available: true, limit_usd, remaining_usd}` or
    `{available: false}`. Sends one request to the provider only when it publishes credit data and
    a key is set. The key never leaves the server.
    """
    async with admitted(runtime):
        settings = await run_in_threadpool(_provider_settings, provider_values_of(runtime))
        provider = settings.answer.provider.strip()
        descriptor = llm_registry.describe_all().get(provider)
        lookup = descriptor.credit if descriptor is not None else None
        credit = await fetch_parsed(lookup, settings) if lookup is not None else None
    if lookup is not None:
        logger.info("Credit read for %s: %s", provider, "available" if credit else "not available")
    if not isinstance(credit, dict):
        return ok({"available": False})
    return ok({"available": True, **credit})
