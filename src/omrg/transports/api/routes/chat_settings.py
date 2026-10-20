"""Chat model settings: read, save and test (design D6, D7).

``GET /v1/settings/chat`` reports the provider and model that answer Chat
and whether Chat is ready. It sends no request to any provider.
``PUT /v1/settings/chat`` writes or clears ``answer.provider`` and
``answer.model`` in ``omrg.jsonc``, and the Engine takes the choice at once.
Both routes carry the file ``revision`` (ADR-087).
``POST /v1/settings/chat/test`` builds the model, sends one short prompt and
reports a reason from a fixed set. A test never saves, and no reply text or
exception text leaves the server.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import time
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Body
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ....compose_providers import ProviderValues, locked_fields
from ....compose_providers import provider_settings as _provider_settings
from ....config.settings_file_write import SettingsFileError
from ....core.providers.llm import registry as llm_registry
from ..engine_access import ReadScope, RuntimeDep, admitted
from ..errors import error_response
from ..lifespan import WebRuntime
from ..provider_state import EngineRefused
from ..settings_store import refusal_response
from .experiments import ManageScope
from .graphs import ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

#: Seconds a Chat model test waits for the reply.
TEST_TIMEOUT_SECONDS = 30.0
TEST_PROMPT = "Reply with the word OK."
MAX_MODEL_CHARS = 200
_PROVIDER_PATH = "answer.provider"
_MODEL_PATH = "answer.model"
_VARIABLES = {_PROVIDER_PATH: "ANSWER__PROVIDER", _MODEL_PATH: "ANSWER__MODEL"}


class ChatChoice(BaseModel):
    """A Chat provider and model name (the body of a test)."""

    model_config = ConfigDict(extra="forbid")

    provider: Annotated[str, Field(min_length=1, max_length=64)]
    model: Annotated[str, Field(min_length=1, max_length=MAX_MODEL_CHARS)]


class ChatSaveBody(BaseModel):
    """Body of ``PUT /v1/settings/chat``.

    A choice has both ``provider`` and ``model``. A body with neither (only an
    optional ``revision``), or no body, clears the choice.
    """

    model_config = ConfigDict(extra="forbid")

    provider: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    model: Annotated[str, Field(min_length=1, max_length=MAX_MODEL_CHARS)] | None = None
    revision: Annotated[str, Field(max_length=128)] | None = None


@dataclass
class RuntimeProviderValues:
    """Holder of provider values for a runtime built without a ``ProviderState``.

    Calling the holder returns the current values, so it works as the
    ``provider_source`` of ``compose.build_engine``.
    """

    current: ProviderValues

    def __call__(self) -> ProviderValues:
        return self.current


def provider_values_of(runtime: WebRuntime) -> Any:
    """Return a callable that gives the provider values in use.

    The launch's :class:`~omrg.transports.api.provider_state.ProviderState`
    holds the values read from ``omrg.jsonc`` and the keychain, so Chat
    readiness and a Chat save see the same keys and addresses as the other
    routes. Without one (a runtime built by hand), an empty holder is used.
    """
    if runtime.providers is not None:
        return runtime.providers.source
    holder = getattr(runtime, "provider_values", None)
    if holder is None:
        holder = RuntimeProviderValues(ProviderValues())
        runtime.provider_values = holder  # type: ignore[attr-defined]
    return holder


def module_installed(name: str) -> bool:
    """Return whether the module *name* can be imported."""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _not_ready_reason(settings: Any, provider: str, model: str) -> str | None:
    """Return why a Chat model for *provider* cannot run, or ``None``. Sends nothing."""
    descriptors = llm_registry.describe_all()
    descriptor = descriptors.get(provider)
    if provider not in llm_registry.available() or descriptor is None:
        return "unknown-provider"
    if not module_installed(descriptor.requires_module):
        return "not-installed"
    keys_missing = any(
        field.kind == "secret"
        and field.required
        and not str(getattr(settings, field.settings_field, "")).strip()
        for field in descriptor.fields
    )
    if keys_missing or not model.strip() or not descriptor.test_targets(settings).urls:
        return "not-configured"
    return None


def _chat_source(settings: Any, locked: bool, paths: Iterable[str] = _VARIABLES) -> str:
    """Return the source of the choice at *paths* (default: Chat).

    ``env``/``dotenv`` (locks), ``config-file`` or ``default``.
    """
    words = [settings.setting_sources.get(p, "default") for p in paths]
    if locked:
        return "dotenv" if "dotenv" in words and "env" not in words else "env"
    return "config-file" if "config-file" in words else "default"


def _status(runtime: WebRuntime) -> dict[str, Any]:
    """Return the body of ``GET /v1/settings/chat``."""
    settings = _provider_settings(provider_values_of(runtime))
    env_vars = [_VARIABLES[p] for p in _VARIABLES if p in settings.provider_explicit]
    provider, model = settings.answer.provider.strip(), settings.answer.model
    reason = "disabled" if not settings.answer.enabled else None
    if reason is None:
        reason = _not_ready_reason(settings, provider, model)
    state = runtime.providers
    return {
        "revision": state.revision if state is not None else "absent",
        "provider": provider,
        "model": model,
        "source": _chat_source(settings, bool(env_vars)),
        "locked": bool(env_vars),
        "lock_reason": _lock_reason(env_vars),
        "enabled": settings.answer.enabled,
        "ready": reason is None,
        "reason": reason,
    }


def _lock_reason(env_vars: list[str]) -> str | None:
    if not env_vars:
        return None
    return f"Set by {' and '.join(env_vars)} in the environment or .env. Remove it to edit here."


def _valid_model(model: str) -> bool:
    return (
        0 < len(model) <= MAX_MODEL_CHARS
        and model == model.strip()
        and not any(unicodedata.category(c).startswith("C") for c in model)
    )


def _locked_response(settings: Any) -> Response | None:
    """Return a 409 naming the variable that locks the Chat choice, or ``None``."""
    locked = locked_fields(settings, settings.provider_explicit)
    names = [_VARIABLES[p] for p in _VARIABLES if p in locked]
    if not names:
        return None
    return error_response(409, _lock_reason(names) or "The Chat choice is locked.")


@router.get("/settings/chat", operation_id="getChatSettings")
async def get_chat_settings(_: ReadScope, runtime: RuntimeDep) -> Response:
    """Return the Chat provider, model, source, lock and whether Chat is ready.

    This route sends no request to any provider.
    """
    async with admitted(runtime):
        body = await run_in_threadpool(_status, runtime)
    return ok(body)


@router.put("/settings/chat", operation_id="setChatSettings")
async def set_chat_settings(
    _: ManageScope,
    runtime: RuntimeDep,
    body: Annotated[ChatSaveBody | None, Body()] = None,
) -> Response:
    """Write the Chat provider and model to `omrg.jsonc`, or clear both.

    A body without `provider` and `model`, or no body, clears the choice.
    The Engine uses the choice from the next answer. 400 for an unknown
    provider or bad model name, 409 when the environment sets the choice,
    the file changed since `revision`, or the Engine refuses it. The answer
    carries the new `revision`.
    """
    body = body or ChatSaveBody()
    choice = None
    if body.provider is not None or body.model is not None:
        if body.provider is None or body.model is None:
            return error_response(400, "Send both provider and model, or neither to clear.")
        if body.provider not in llm_registry.available():
            return error_response(400, "Unknown Chat provider.")
        if not _valid_model(body.model):
            return error_response(
                400, "The model name must be 1 to 200 characters with no control characters."
            )
        choice = (body.provider, body.model)
    state = runtime.providers
    if state is None:
        return error_response(404, "Provider settings are not available.")
    async with admitted(runtime), state.lock:
        settings = await run_in_threadpool(_provider_settings, provider_values_of(runtime))
        if (locked := _locked_response(settings)) is not None:
            return locked
        try:
            await run_in_threadpool(state.save_chat, runtime.engine, choice, body.revision)
        except SettingsFileError as exc:
            return refusal_response(exc)
        except EngineRefused:
            return error_response(409, "The running server could not take this Chat choice.")
        result = await run_in_threadpool(_status, runtime)
    logger.info("Chat choice %s", "cleared" if choice is None else "saved")
    return ok(result)


def _chain(exc: BaseException) -> list[BaseException]:
    """Return *exc* and its causes, at most five deep."""
    found: list[BaseException] = []
    node: BaseException | None = exc
    while node is not None and len(found) < 5:
        found.append(node)
        node = node.__cause__ or node.__context__
    return found


def _mro_names(exc: BaseException) -> set[str]:
    return {cls.__name__ for cls in type(exc).__mro__}


def reason_for(exc: BaseException) -> str:
    """Map an exception to a fixed reason by type and ``status_code``, never by text."""
    chain = _chain(exc)
    for node in chain:
        if isinstance(node, TimeoutError) or any("Timeout" in n for n in _mro_names(node)):
            return "timeout"
    for node in chain:
        status = getattr(node, "status_code", None)
        if isinstance(status, int) and not isinstance(status, bool):
            return "unauthorised" if status in (401, 403) else f"http-{status}"
    if any(isinstance(node, ModuleNotFoundError) for node in chain):
        return "not-installed"
    for node in chain:
        names = _mro_names(node)
        if isinstance(node, ConnectionError) or names & {"ConnectError", "APIConnectionError"}:
            return "refused"
    return "failed"


async def _run_test(settings: Any, provider: str, model: str) -> dict[str, Any]:
    started = time.monotonic()

    def elapsed() -> int:
        return int((time.monotonic() - started) * 1000)

    def result(ok_: bool, reason: str | None) -> dict[str, Any]:
        return {"ok": ok_, "reason": reason, "elapsed_ms": elapsed()}

    candidate = settings.model_copy(
        update={
            "answer": settings.answer.model_copy(
                update={"enabled": True, "provider": provider, "model": model}
            )
        }
    )
    if (reason := _not_ready_reason(candidate, provider, model)) is not None:
        return result(False, "not-configured" if reason == "unknown-provider" else reason)
    try:
        async with asyncio.timeout(TEST_TIMEOUT_SECONDS):
            build = await run_in_threadpool(llm_registry.get, provider)
            llm = await run_in_threadpool(
                lambda: build(candidate, timeout=TEST_TIMEOUT_SECONDS, answer_model=model)
            )
            reply = await llm.acomplete(TEST_PROMPT)
    except Exception as exc:  # noqa: BLE001 - mapped to a fixed reason below
        return result(False, reason_for(exc))
    text = str(getattr(reply, "text", reply) or "").strip()
    return result(bool(text), None if text else "empty-reply")


@router.post("/settings/chat/test", operation_id="testChatModel")
async def test_chat_model(
    _: ManageScope,
    runtime: RuntimeDep,
    body: Annotated[ChatChoice | None, Body()] = None,
) -> Response:
    """Send one short prompt to the given or saved Chat model and report `{ok, reason, elapsed_ms}`.

    The reply and any exception text stay on the server. Nothing is saved.
    """
    if body is not None and body.provider not in llm_registry.available():
        return error_response(400, "Unknown Chat provider.")
    if body is not None and not _valid_model(body.model):
        return error_response(
            400, "The model name must be 1 to 200 characters with no control characters."
        )
    async with admitted(runtime):
        settings = await run_in_threadpool(_provider_settings, provider_values_of(runtime))
        provider = settings.answer.provider.strip() if body is None else body.provider
        model = settings.answer.model if body is None else body.model
        outcome = await _run_test(settings, provider, model)
    logger.info("Chat model test: %s", outcome["reason"] or "ok")
    return ok(outcome)
