"""Provider connections: summary, saved addresses and keys, tests, model lists (design D6, D7).

``GET /v1/connections`` shows the registered LLM providers and sends no
request. ``PUT /v1/connections/{provider}`` saves addresses, the key routes
use the system keychain, and ``test`` and ``models`` contact a provider only
when called. Every write, test and list route needs the browser session. No
route returns a key, a response body or exception text.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .... import compose
from ....compose_providers import provider_settings
from ....core.providers.llm.connection import ConnectionDescriptor
from ....integrations.keychain import KeychainUnavailableError
from ..connection_probe import list_models, probe
from ..engine_access import ReadScope, RuntimeDep, admitted
from ..errors import error_response
from ..provider_state import (
    KEY_RULE,
    MAX_KEY_CHARS,
    MIN_KEY_CHARS,
    EngineRefused,
    ProviderState,
    descriptor_of,
    field_of,
    overlay,
    typed_settings,
    valid_key,
    validate_address,
)
from .experiments import ManageScope
from .graphs import ok
from .mcp import CredentialsScope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

_REFUSED = "The running engine cannot take this change. Restart the server to apply it."


class FieldValuesBody(BaseModel):
    """Typed values for a test or a model list. Nothing is saved."""

    model_config = ConfigDict(extra="forbid")

    fields: dict[str, str] = Field(default_factory=dict, max_length=16)


class SaveFieldsBody(BaseModel):
    """Body of ``PUT /v1/connections/{provider}``; ``null`` clears a saved address."""

    model_config = ConfigDict(extra="forbid")

    fields: dict[str, str | None] = Field(min_length=1, max_length=16)


class KeyBody(BaseModel):
    """Body of ``PUT /v1/connections/{provider}/key``."""

    model_config = ConfigDict(extra="forbid")

    api_key: str = Field(min_length=MIN_KEY_CHARS, max_length=MAX_KEY_CHARS)

    @field_validator("api_key")
    @classmethod
    def _rule(cls, value: str) -> str:
        if not valid_key(value):
            raise ValueError(KEY_RULE)  # names the rule, never the value
        return value


def _state(runtime: Any) -> ProviderState | None:
    return runtime.providers


def _unknown() -> Response:
    return error_response(404, "Unknown provider.")


async def _entry(state: ProviderState, runtime: Any, provider: str) -> dict[str, Any]:
    """Return the summary entry of *provider* (locks, sources) for the saved values."""
    summary = await run_in_threadpool(
        compose.connection_summary, state.values, runtime.engine.profile_catalogue()
    )
    return next(e for e in summary["connections"] if e["provider"] == provider)


@router.get("/connections", operation_id="getConnections")
async def get_connections(_: ReadScope, runtime: RuntimeDep) -> Response:
    """Return `config_dir`, the keychain state and one card per registered provider.

    Each entry has its fields (address or key state), read-only values and
    roles. The key value never leaves the server.
    """
    state = _state(runtime)
    async with admitted(runtime):
        summary = await run_in_threadpool(
            compose.connection_summary,
            state.values if state else None,
            runtime.engine.profile_catalogue(),
        )
    return ok(summary)


@router.put("/connections/{provider}", operation_id="saveProviderFields")
async def save_provider_fields(
    _: ManageScope, provider: str, body: SaveFieldsBody, runtime: RuntimeDep
) -> Response:
    """Save or clear provider addresses. 400 bad address, 404 unknown, 409 locked."""
    descriptor = descriptor_of(provider)
    state = _state(runtime)
    if descriptor is None or state is None:
        return _unknown()
    updates: dict[str, str | None] = {}
    for fid, value in body.fields.items():
        spec = field_of(descriptor, fid)
        if spec is None:
            return error_response(404, "Unknown field.")
        if spec.kind != "url":
            return error_response(400, "A key is saved with the key route, not here.")
        text = None if value is None else value.strip()
        if text is not None and (rule := validate_address(text)):
            return error_response(400, rule)
        updates[fid] = text
    async with admitted(runtime), state.lock:
        entry = await _entry(state, runtime, provider)
        for field in entry["fields"]:
            if field["id"] in updates and field["locked"]:
                return error_response(409, field["lock_reason"] or "This field is locked.")
        try:
            await run_in_threadpool(state.save_fields, runtime.engine, provider, updates)
        except EngineRefused:
            return error_response(409, _REFUSED)
    return ok({})


def _key_field(descriptor: ConnectionDescriptor) -> Any:
    return next((spec for spec in descriptor.fields if spec.kind == "secret"), None)


@router.put("/connections/{provider}/key", operation_id="saveProviderKey")
async def save_provider_key(
    _: CredentialsScope, provider: str, body: KeyBody, runtime: RuntimeDep
) -> Response:
    """Save the API key of *provider* to the system keychain.

    The key joins the redaction set before the keychain sees it. 409 when the
    key comes from the environment or no keychain exists.
    """
    descriptor = descriptor_of(provider)
    state = _state(runtime)
    if descriptor is None or state is None or _key_field(descriptor) is None:
        return _unknown()
    state.secrets.add(body.api_key)
    async with admitted(runtime), state.lock:
        entry = await _entry(state, runtime, provider)
        field = next(f for f in entry["fields"] if f["kind"] == "secret")
        if field["locked"]:
            return error_response(409, field["lock_reason"] or "This key is locked.")
        try:
            await run_in_threadpool(state.save_key, runtime.engine, provider, body.api_key)
        except KeychainUnavailableError:
            return error_response(409, "The system keychain could not save the key.")
        except EngineRefused:
            return error_response(409, _REFUSED)
    return ok({})


@router.delete("/connections/{provider}/key", operation_id="removeProviderKey")
async def remove_provider_key(_: CredentialsScope, provider: str, runtime: RuntimeDep) -> Response:
    """Remove the saved API key of *provider* from the system keychain."""
    descriptor = descriptor_of(provider)
    state = _state(runtime)
    if descriptor is None or state is None or _key_field(descriptor) is None:
        return _unknown()
    async with admitted(runtime), state.lock:
        entry = await _entry(state, runtime, provider)
        field = next(f for f in entry["fields"] if f["kind"] == "secret")
        if field["locked"]:
            return error_response(409, field["lock_reason"] or "This key is locked.")
        try:
            await run_in_threadpool(state.delete_key, runtime.engine, provider)
        except KeychainUnavailableError:
            return error_response(409, "The system keychain could not remove the key.")
        except EngineRefused:
            return error_response(409, _REFUSED)
    return ok({})


async def _typed_target(
    runtime: Any,
    descriptor: ConnectionDescriptor,
    body: FieldValuesBody,
    models: bool,
) -> Any:
    """Validate typed values and return the target built from them, or an error response."""
    state = _state(runtime)
    typed: dict[str, str] = {}
    for fid, value in body.fields.items():
        spec = field_of(descriptor, fid)
        if spec is None:
            return error_response(404, "Unknown field.")
        text = value.strip()
        if not text:
            continue
        if spec.kind == "url" and (rule := validate_address(text)):
            return error_response(400, rule)
        if spec.kind == "secret":
            if not valid_key(text):
                return error_response(400, KEY_RULE)
            if state is not None:
                state.secrets.add(text)
        typed[fid] = text
    saved = state.values if state else compose.ProviderValues()
    values = overlay(saved, typed_settings(descriptor, typed))
    settings = await run_in_threadpool(provider_settings, lambda: values)
    return descriptor.models_target(settings) if models else descriptor.test_targets(settings)


@router.post("/connections/{provider}/test", operation_id="testConnection")
async def test_connection(
    _: ManageScope, provider: str, runtime: RuntimeDep, body: FieldValuesBody | None = None
) -> Response:
    """Send one request to *provider* and report `{reachable, reason}`.

    Typed `fields` are tested and not saved.
    """
    descriptor = descriptor_of(provider)
    if descriptor is None:
        return _unknown()
    async with admitted(runtime):
        target = await _typed_target(runtime, descriptor, body or FieldValuesBody(), False)
        if isinstance(target, Response):
            return target
        result = await probe(target.urls, target.headers)
    logger.info("Connection test for %s: %s", provider, result["reason"] or "reachable")
    return ok(result)


@router.post("/connections/{provider}/models", operation_id="listProviderModels")
async def list_provider_models(
    _: ManageScope, provider: str, runtime: RuntimeDep, body: FieldValuesBody | None = None
) -> Response:
    """List the model names of *provider*: at most 1,000, sorted, nothing else of the body."""
    descriptor = descriptor_of(provider)
    if descriptor is None:
        return _unknown()
    async with admitted(runtime):
        target = await _typed_target(runtime, descriptor, body or FieldValuesBody(), True)
        if isinstance(target, Response):
            return target
        result = await list_models(target.urls, target.headers, descriptor.parse_models)
    logger.info("Model list for %s: %s", provider, result["reason"] or "reachable")
    return ok(result)
