"""Claim check judge settings: read and save (add-judge-model-setting, design D1 and D6).

``GET /v1/settings/judge`` reports the judge provider and model in force, the
registry provider an alias resolves to, the source, the lock and whether the
judge is ready. It sends no request to any provider and does not say whether
claim checks are on: a profile decides that per collection.
``PUT /v1/settings/judge`` writes or clears ``answer.verify_provider`` and
``answer.verify_model`` in ``omrs.jsonc`` as one unit, with
``answer.verify_reasoning`` in the same write (add-chat-reasoning-and-usage D4),
and the Engine takes the choice from the next answer.
Both routes carry the file ``revision`` (ADR-087).
A judge test reuses ``POST /v1/settings/chat/test`` (design D5).
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ....compose_answer import resolve_verify_provider
from ....compose_providers import locked_fields
from ....compose_providers import provider_settings as _provider_settings
from ....config.settings_file_write import SettingsFileError
from ....core.providers.llm import registry as llm_registry
from ..engine_access import ReadScope, RuntimeDep, admitted
from ..errors import error_response
from ..lifespan import WebRuntime
from ..provider_state import EngineRefused
from ..settings_store import refusal_response
from .chat_reasoning import JUDGE_LEVEL, level_changes, level_lock_response, level_view
from .chat_settings import (
    MAX_MODEL_CHARS,
    ReasoningLevel,
    _chat_source,
    _not_ready_reason,
    _valid_model,
    provider_values_of,
)
from .experiments import ManageScope
from .graphs import ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

_VARIABLES = {
    "answer.verify_provider": "ANSWER__VERIFY_PROVIDER",
    "answer.verify_model": "ANSWER__VERIFY_MODEL",
}


class JudgeSaveBody(BaseModel):
    """Body of ``PUT /v1/settings/judge``.

    A choice has both ``provider`` (a registry name, never an alias) and
    ``model``. A body with neither (only an optional ``revision``), or no
    body, clears the choice.
    """

    model_config = ConfigDict(extra="forbid")

    provider: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    model: Annotated[str, Field(min_length=1, max_length=MAX_MODEL_CHARS)] | None = None
    reasoning: ReasoningLevel = None
    revision: Annotated[str, Field(max_length=128)] | None = None


def _lock_reason(env_vars: list[str]) -> str | None:
    if not env_vars:
        return None
    return f"Set by {' and '.join(env_vars)} in the environment or .env. Remove it to edit here."


def _reason(settings: Any, resolved: str, model: str) -> str | None:
    """Return why the judge cannot run, or ``None``. Sends nothing."""
    if not settings.answer.enabled:
        return "disabled"
    reason = _not_ready_reason(settings, resolved, model)
    if reason == "not-configured" and not model.strip():
        return "no-model"
    return reason


def _status(runtime: WebRuntime) -> dict[str, Any]:
    """Return the body of ``GET /v1/settings/judge``."""
    settings = _provider_settings(provider_values_of(runtime))
    locked = locked_fields(settings, settings.provider_explicit)
    env_vars = [_VARIABLES[p] for p in _VARIABLES if p in locked]
    provider = str(settings.answer.verify_provider or "").strip() or "cloud"
    model = str(settings.answer.verify_model or "")
    resolved = resolve_verify_provider(settings, provider)
    reason = _reason(settings, resolved, model)
    state = runtime.providers
    return {
        "revision": state.revision if state is not None else "absent",
        "provider": provider,
        "resolved_provider": resolved,
        "model": model,
        "source": _chat_source(settings, bool(env_vars), _VARIABLES),
        "locked": bool(env_vars),
        "lock_reason": _lock_reason(env_vars),
        "enabled": settings.answer.enabled,
        "ready": reason is None,
        "reason": reason,
        **level_view(settings, JUDGE_LEVEL, resolved),
    }


def _choice(body: JudgeSaveBody) -> tuple[str, str] | Response | None:
    """Return the checked choice, ``None`` to clear, or a 400 response."""
    if body.provider is None and body.model is None:
        return None
    if body.provider is None or body.model is None:
        return error_response(400, "Send both provider and model, or neither to clear.")
    if body.provider not in llm_registry.available():
        return error_response(400, "Unknown judge provider. Choose a registered provider.")
    if not _valid_model(body.model):
        return error_response(
            400, "The model name must be 1 to 200 characters with no control characters."
        )
    return body.provider, body.model


@router.get("/settings/judge", operation_id="getJudgeSettings")
async def get_judge_settings(_: ReadScope, runtime: RuntimeDep) -> Response:
    """Return the judge provider, model, source, lock and whether the judge is ready.

    This route sends no request to any provider.
    """
    async with admitted(runtime):
        body = await run_in_threadpool(_status, runtime)
    return ok(body)


@router.put("/settings/judge", operation_id="setJudgeSettings")
async def set_judge_settings(
    _: ManageScope,
    runtime: RuntimeDep,
    body: Annotated[JudgeSaveBody | None, Body()] = None,
) -> Response:
    """Write the judge provider, model and reasoning level to `omrs.jsonc`, or clear them.

    `reasoning` left out keeps the saved level; `""` removes it. A body with
    only `reasoning` keeps the choice. A body without `provider`, `model` and
    `reasoning`, or no body, clears the choice and its level. A bad level is
    400; a level set by `ANSWER__VERIFY_REASONING` is 409. The Engine uses
    the choice from the next answer. 400 for an unknown
    provider, an alias, one field only or a bad model name; 409 when the
    environment sets the choice, the file changed since `revision`, or the
    Engine refuses it. The answer carries the new `revision`.
    """
    body = body or JudgeSaveBody()
    writes_choice = body.reasoning is None or body.provider is not None or body.model is not None
    choice = _choice(body) if writes_choice else None
    if isinstance(choice, Response):
        return choice
    state = runtime.providers
    if state is None:
        return error_response(404, "Provider settings are not available.")
    async with admitted(runtime), state.lock:
        settings = await run_in_threadpool(_provider_settings, provider_values_of(runtime))
        locked = locked_fields(settings, settings.provider_explicit)
        names = [_VARIABLES[p] for p in _VARIABLES if p in locked]
        if writes_choice and names:
            return error_response(409, _lock_reason(names) or "The judge choice is locked.")
        if (
            body.reasoning is not None
            and (refused := level_lock_response(settings, JUDGE_LEVEL)) is not None
        ):
            return refused
        changes: dict[str, str | None] = {}
        if writes_choice:
            provider, model = choice if choice is not None else (None, None)
            changes = dict(zip(_VARIABLES, (provider, model), strict=True))
        clearing = writes_choice and choice is None
        changes |= level_changes(settings, JUDGE_LEVEL, body.reasoning, clearing)
        try:
            await run_in_threadpool(state.save_fields, runtime.engine, changes, body.revision)
        except SettingsFileError as exc:
            return refusal_response(exc)
        except EngineRefused:
            return error_response(409, "The running server could not take this judge choice.")
        result = await run_in_threadpool(_status, runtime)
    logger.info("Judge choice %s", "cleared" if writes_choice and choice is None else "saved")
    return ok(result)
