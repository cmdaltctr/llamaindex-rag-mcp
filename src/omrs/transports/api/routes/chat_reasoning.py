"""Reasoning levels: the shared save rules and the level list (add-chat-reasoning-and-usage D4, D5).

The Chat and judge settings routes use the helpers here to report and save
``answer.reasoning`` and ``answer.verify_reasoning``. Each level locks on its
own variable (``ANSWER__REASONING``, ``ANSWER__VERIFY_REASONING``), apart from
the provider and model.

``GET /v1/settings/chat/reasoning-levels`` returns the levels a model accepts
when its provider publishes a catalogue. The parsed catalogue stays in process
memory for 10 minutes. A provider without a catalogue sends no request. A
failed read gives ``{"known": false}`` and is not cached.
"""

from __future__ import annotations

import logging
import time
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from ....compose_providers import locked_fields
from ....compose_providers import provider_settings as _provider_settings
from ....core.providers.llm import registry as llm_registry
from ..engine_access import ReadScope, RuntimeDep, admitted
from ..errors import error_response
from ..provider_fetch import fetch_parsed
from .graphs import ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

#: Seconds a parsed catalogue stays in memory.
CATALOGUE_TTL_SECONDS = 600.0
CHAT_LEVEL = ("answer.reasoning", "ANSWER__REASONING")
JUDGE_LEVEL = ("answer.verify_reasoning", "ANSWER__VERIFY_REASONING")

#: Provider name -> (time read, model id -> level entry).
_catalogues: dict[str, tuple[float, dict[str, dict[str, Any]]]] = {}
_clock = time.monotonic


def clear_catalogue_cache() -> None:
    """Forget every cached catalogue (tests, and nothing else, call this)."""
    _catalogues.clear()


def _lock_reason(variable: str) -> str:
    return f"Set by {variable} in the environment or .env. Remove it to edit here."


def level_locked(settings: Any, level: tuple[str, str]) -> bool:
    """Return whether the environment or ``.env`` sets the level at *level*."""
    return level[0] in locked_fields(settings, settings.provider_explicit)


def level_view(settings: Any, level: tuple[str, str], provider: str) -> dict[str, Any]:
    """Return the four reasoning fields of a settings ``GET`` body.

    Args:
        settings: Settings in use.
        level: ``(path, variable)``: :data:`CHAT_LEVEL` or :data:`JUDGE_LEVEL`.
        provider: The registry provider the level goes to.
    """
    path, variable = level
    locked = level_locked(settings, level)
    return {
        "reasoning": getattr(settings.answer, path.removeprefix("answer.")),
        "reasoning_locked": locked,
        "reasoning_lock_reason": _lock_reason(variable) if locked else None,
        "reasoning_ignored": llm_registry.ignores_reasoning(provider),
    }


def level_lock_response(settings: Any, level: tuple[str, str]) -> Response | None:
    """Return a 409 naming the variable when the level is locked, else ``None``."""
    return error_response(409, _lock_reason(level[1])) if level_locked(settings, level) else None


def level_changes(
    settings: Any, level: tuple[str, str], sent: str | None, clearing: bool
) -> dict[str, str | None]:
    """Return the file change for the level.

    A sent level is written, and ``""`` removes the key. A clear of the
    whole choice also removes an unlocked level. Otherwise the saved level
    stays.
    """
    if sent is not None:
        return {level[0]: sent or None}
    if clearing and not level_locked(settings, level):
        return {level[0]: None}
    return {}


async def _catalogue(provider: str, lookup: Any, settings: Any) -> dict[str, dict[str, Any]] | None:
    """Return the cached or freshly read catalogue of *provider*, or ``None`` on failure."""
    cached = _catalogues.get(provider)
    if cached is not None and _clock() - cached[0] < CATALOGUE_TTL_SECONDS:
        return cached[1]
    parsed = await fetch_parsed(lookup, settings)
    if not isinstance(parsed, dict) or not parsed:
        return None
    _catalogues[provider] = (_clock(), parsed)
    return parsed


@router.get("/settings/chat/reasoning-levels", operation_id="getReasoningLevels")
async def get_reasoning_levels(
    _: ReadScope,
    runtime: RuntimeDep,
    provider: Annotated[str, Query(min_length=1, max_length=64)],
    model: Annotated[str, Query(min_length=1, max_length=200)],
) -> Response:
    """Return the reasoning levels *model* accepts, from the provider catalogue.

    `{known: true, levels, default, mandatory, ignored}` when the catalogue
    lists the model, else `{known: false, ignored}`. `ignored` says whether
    the provider sends no level at all. A provider without a catalogue sends
    no request; the catalogue read sends no API key.
    """
    ignored = llm_registry.ignores_reasoning(provider)
    descriptor = llm_registry.describe_all().get(provider)
    lookup = descriptor.reasoning_levels if descriptor is not None else None
    entry = None
    if lookup is not None:
        async with admitted(runtime):
            # chat_settings imports this module, so import it here, not at the top.
            from .chat_settings import provider_values_of

            settings = await run_in_threadpool(_provider_settings, provider_values_of(runtime))
            catalogue = await _catalogue(provider, lookup, settings)
        entry = (catalogue or {}).get(model)
        logger.info("Reasoning levels for %s: %s", provider, "known" if entry else "not known")
    if entry is None:
        return ok({"known": False, "ignored": ignored})
    return ok({"known": True, **entry, "ignored": ignored})
