"""Provider connections: summary, saved addresses and keys, tests, model lists (design D6, D7).

``GET /v1/connections`` shows the registered LLM providers and sends no
request. ``PUT /v1/connections/{provider}`` writes addresses to ``omrg.jsonc``,
the key routes use the system keychain and write ``keychain://<provider>`` to
the file, and ``test`` and ``models`` contact a provider only when called. The
read returns the file ``revision``; each save may send it back (ADR-087). Every
write, test and list route needs the browser session. No route returns a key,
a response body or exception text.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Body
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .... import compose
from ....compose_providers import provider_settings
from ....config.settings_file_write import SettingsFileError
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
    check_field,
    descriptor_of,
    field_of,
    overlay,
    typed_settings,
    valid_key,
)
from ..settings_store import refusal_response
from .experiments import ManageScope
from .graphs import ok
from .mcp import CredentialsScope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

_REFUSED = "The running engine cannot take this change. Restart the server to apply it."


Revision = Annotated[str, Field(max_length=128)] | None


class FieldValuesBody(BaseModel):
    """Typed values for a test or a model list. Nothing is saved."""

    model_config = ConfigDict(extra="forbid")

    fields: dict[str, str] = Field(default_factory=dict, max_length=16)


class SaveFieldsBody(BaseModel):
    """Body of ``PUT /v1/connections/{provider}``; ``null`` clears a saved address."""

    model_config = ConfigDict(extra="forbid")

    fields: dict[str, str | int | float | None] = Field(min_length=1, max_length=16)
    revision: Revision = None


class RevisionBody(BaseModel):
    """Optional body of ``DELETE /v1/connections/{provider}/key``."""

    model_config = ConfigDict(extra="forbid")

    revision: Revision = None


class KeyBody(BaseModel):
    """Body of ``PUT /v1/connections/{provider}/key``."""

    model_config = ConfigDict(extra="forbid")

    api_key: str = Field(min_length=MIN_KEY_CHARS, max_length=MAX_KEY_CHARS)
    revision: Revision = None

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
    return ok({**summary, "revision": state.revision if state else "absent"})


@router.put("/connections/{provider}", operation_id="saveProviderFields")
async def save_provider_fields(
    _: ManageScope, provider: str, body: SaveFieldsBody, runtime: RuntimeDep
) -> Response:
    """Save or clear provider addresses. 400 bad address, 404 unknown, 409 locked."""
    descriptor = descriptor_of(provider)
    state = _state(runtime)
    if descriptor is None or state is None:
        return _unknown()
    updates: dict[str, str | int | None] = {}
    for fid, value in body.fields.items():
        spec = field_of(descriptor, fid)
        if spec is None:
            return error_response(404, "Unknown field.")
        if spec.kind == "secret":
            return error_response(400, "A key is saved with the key route, not here.")
        text, rule = check_field(spec, value)
        if rule:
            return error_response(400, rule)
        updates[spec.settings_field] = int(text) if spec.kind == "int" and text else text
    async with admitted(runtime), state.lock:
        entry = await _entry(state, runtime, provider)
        wanted = {f.id for f in descriptor.fields if f.settings_field in updates}
        for field in entry["fields"]:
            if field["id"] in wanted and field["locked"]:
                return error_response(409, field["lock_reason"] or "This field is locked.")
        try:
            result = await run_in_threadpool(
                state.save_fields, runtime.engine, updates, body.revision
            )
        except SettingsFileError as exc:
            return refusal_response(exc)
        except EngineRefused:
            return error_response(409, _REFUSED)
    return ok({"revision": result.revision})


def _key_field(descriptor: ConnectionDescriptor) -> Any:
    return next((spec for spec in descriptor.fields if spec.kind == "secret"), None)


@router.put("/connections/{provider}/key", operation_id="saveProviderKey")
async def save_provider_key(
    _: CredentialsScope, provider: str, body: KeyBody, runtime: RuntimeDep
) -> Response:
    """Save the API key of *provider* to the system keychain.

    The reference `keychain://<provider>` goes to `omrg.jsonc`; the key goes to
    no file. The key joins the redaction set before the keychain sees it. 409
    when the key comes from the environment or `.env`, no keychain exists, or the
    file changed since `revision`.
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
            result = await run_in_threadpool(
                state.save_key,
                runtime.engine,
                provider,
                _key_field(descriptor).settings_field,
                body.api_key,
                body.revision,
            )
        except SettingsFileError as exc:
            return refusal_response(exc)
        except KeychainUnavailableError:
            return error_response(409, "The system keychain could not save the key.")
        except EngineRefused:
            return error_response(409, _REFUSED)
    return ok({"revision": result.revision})


@router.delete("/connections/{provider}/key", operation_id="removeProviderKey")
async def remove_provider_key(
    _: CredentialsScope,
    provider: str,
    runtime: RuntimeDep,
    body: Annotated[RevisionBody | None, Body()] = None,
) -> Response:
    """Remove the API key of *provider* from the keychain, and its `keychain://` reference."""
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
            result = await run_in_threadpool(
                state.delete_key,
                runtime.engine,
                provider,
                _key_field(descriptor).settings_field,
                body.revision if body else None,
            )
        except SettingsFileError as exc:
            return refusal_response(exc)
        except KeychainUnavailableError:
            return error_response(409, "The system keychain could not remove the key.")
        except EngineRefused:
            return error_response(409, _REFUSED)
    return ok({"revision": result.revision})


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
        if spec.kind in ("url", "int") and (rule := check_field(spec, text)[1]):
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
