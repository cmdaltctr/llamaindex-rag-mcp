"""Shared helpers for the runtime OpenAPI conformance tests (task 6.7).

Not a test module. It reads the runtime routes of a real application and
the reviewed ``openapi.yaml``, and gives the tests one checker that
validates a real response against the schema the contract declares for
its operation and status. No model, LLM or network call happens.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

pytest.importorskip("fastapi")

import jsonschema  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from tests.unit.test_web_documents_support import openapi_doc  # noqa: E402

from omrg.transports.api.app import create_app  # noqa: E402
from omrg.transports.api.lifespan import WebConfig, get_runtime  # noqa: E402
from omrg.transports.api.security import BEARER_SCOPES  # noqa: E402

API_PREFIX = "/v1"
METHODS = ("get", "put", "post", "delete", "patch")
_PARAM = re.compile(r"\{[^}]+\}")

#: Operation ids each response-flow test must exercise. Together they must
#: cover every operation in the contract (checked by the static module).
FAMILIES: dict[str, frozenset[str]] = {
    "foundation": frozenset(
        {
            "getHealth",
            "createSession",
            "getSession",
            "issueCredential",
            "listCredentials",
            "revokeCredential",
            "listRoots",
            "preflightUpload",
            "uploadFile",
        }
    ),
    "jobs": frozenset({"ingestPath", "generateCodebaseMap", "getJobStatus", "listJobEvents"}),
    "documents": frozenset(
        {
            "listCollections",
            "listDocuments",
            "searchCollection",
            "answerCollection",
            "streamAnswer",
            "getChunk",
            "deleteDocuments",
            "changeCollectionProfile",
            "setCollectionDisplayName",
        }
    ),
    "graphs": frozenset(
        {
            "listPipelineOperations",
            "createPipeline",
            "listPipelines",
            "getPipeline",
            "savePipelineLayout",
            "savePipelineRevision",
            "listPipelineRevisions",
            "getPipelineRevision",
            "validatePipeline",
        }
    ),
    "profiles": frozenset(
        {"listProfiles", "createProfile", "getProfile", "updateProfile", "deleteProfile"}
    ),
    "chats": frozenset(
        {
            "listChats",
            "createChat",
            "getChat",
            "moveChat",
            "deleteChat",
            "deleteChats",
            "appendChatTurn",
            "createChatFolder",
            "renameChatFolder",
            "deleteChatFolder",
        }
    ),
    "embedding": frozenset(
        {"listEmbeddingProviders", "checkEmbeddingModel", "setProfileEmbedding"}
    ),
    "runs": frozenset(
        {
            "submitRun",
            "listRuns",
            "getRun",
            "getRunResult",
            "getRunArtefact",
            "cancelRun",
            "retryRun",
            "listRunEvents",
            "streamRunEvents",
        }
    ),
    "cleanup": frozenset({"previewWorkspaceCleanup", "applyWorkspaceCleanup"}),
    "mcp": frozenset(
        {
            "getMcpState",
            "setMcpEnabled",
            "rotateMcpToken",
            "revokeMcpToken",
            "getWebPort",
            "setWebPort",
            "getUploadLimit",
            "setUploadLimit",
        }
    ),
    "templates": frozenset({"listPipelineTemplates"}),
    "integrations": frozenset({"listIntegrations"}),
    "connections": frozenset(
        {
            "getConnections",
            "testConnection",
            "saveProviderFields",
            "saveProviderKey",
            "removeProviderKey",
            "listProviderModels",
        }
    ),
    "chat_settings": frozenset({"getChatSettings", "setChatSettings", "testChatModel"}),
    "judge_settings": frozenset({"getJudgeSettings", "setJudgeSettings"}),
    "llamacpp_server": frozenset(
        {
            "getLlamacppServer",
            "saveLlamacppServer",
            "startLlamacppServer",
            "stopLlamacppServer",
            "restartLlamacppServer",
        }
    ),
    "logs": frozenset({"getLogs", "streamLogs"}),
    "power": frozenset({"getServerPower", "requestServerPower"}),
    "configuration": frozenset({"getSettingsConfiguration"}),
    "document_reading": frozenset({"getDocumentReadingSettings", "setDocumentReadingSettings"}),
    "experiments": frozenset(
        {
            "createExperiment",
            "createExperimentFolder",
            "listExperiments",
            "getExperiment",
            "revokeExperiment",
        }
    ),
    "plugins": frozenset(
        {
            "listPlugins",
            "registerPlugin",
            "unregisterPlugin",
            "recheckPlugin",
            "openPluginEditor",
            "stopPluginEditor",
        }
    ),
}


# ── Runtime routes ───────────────────────────────────────────────────────


def build_bare_app(tmp_path: Path) -> Any:
    """Return an application for route inspection only (no lifespan runs)."""
    config = WebConfig(workspace=tmp_path / "ws", port=8765, static_dir=None)
    return create_app(config, engine_factory=lambda: None)


def iter_api_routes(app: Any) -> Iterator[tuple[str, APIRoute]]:
    """Yield ``(effective path, route)`` for every API route of *app*.

    FastAPI 0.143 wraps included routers; ``iter_route_contexts`` flattens
    them. Older releases list the routes directly.
    """
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError:  # pragma: no cover - older FastAPI
        for route in app.routes:
            if isinstance(route, APIRoute):
                yield route.path, route
        return
    for context in iter_route_contexts(app.routes):
        route = context.original_route
        if isinstance(route, APIRoute):
            yield context.path or route.path, route


def normalise(path: str) -> str:
    """Replace every path parameter name with ``{}`` for comparison."""
    return _PARAM.sub("{}", path)


def runtime_operations(app: Any) -> dict[tuple[str, str], APIRoute]:
    """Return ``(method, normalised /v1 path) -> route`` for public routes.

    A route with ``include_in_schema=False`` is internal and is left out.
    """
    found: dict[tuple[str, str], APIRoute] = {}
    for path, route in iter_api_routes(app):
        if not path.startswith(API_PREFIX) or not route.include_in_schema:
            continue
        for method in route.methods - {"HEAD", "OPTIONS"}:
            found[(method.lower(), normalise(path))] = route
    return found


def walk_dependencies(route: APIRoute) -> Iterator[Any]:
    """Yield every dependency callable of *route*, depth first."""
    stack = list(route.dependant.dependencies)
    while stack:
        dependant = stack.pop()
        yield dependant.call
        stack.extend(dependant.dependencies)


@dataclass(frozen=True)
class RouteAccess:
    """The access policy a route enforces at runtime."""

    scope: str | None
    session_only: bool
    needs_runtime: bool


def route_access(route: APIRoute) -> RouteAccess:
    """Read the scope, session-only flag and runtime need of *route*."""
    calls = list(walk_dependencies(route))
    scopes = {call.omrg_scope for call in calls if getattr(call, "omrg_scope", None)}
    assert len(scopes) <= 1, f"{route.path} requires several scopes: {sorted(scopes)}"
    scope = next(iter(scopes), None)
    flagged = any(getattr(call, "omrg_session_only", False) for call in calls)
    session_only = scope is not None and (flagged or scope not in BEARER_SCOPES)
    return RouteAccess(scope, session_only, any(call is get_runtime for call in calls))


# ── Contract ─────────────────────────────────────────────────────────────


def contract_operations() -> dict[tuple[str, str], dict[str, Any]]:
    """Return ``(method, normalised /v1 path) -> operation`` from the contract."""
    found = {}
    for path, item in openapi_doc()["paths"].items():
        for method in METHODS:
            if method in item:
                found[(method, normalise(API_PREFIX + path))] = item[method]
    return found


def resolve(node: dict[str, Any]) -> dict[str, Any]:
    """Follow ``$ref`` links inside the contract."""
    doc = openapi_doc()
    while "$ref" in node:
        target: Any = doc
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        node = target
    return node


def with_components(schema: dict[str, Any]) -> dict[str, Any]:
    """Return *schema* with the contract components, so ``$ref`` links resolve."""
    return {**copy.deepcopy(schema), "components": openapi_doc()["components"]}


def match_operation(method: str, path: str) -> tuple[str, dict[str, Any]] | None:
    """Return the contract template and operation for a concrete request.

    The template with the fewest parameters wins, so ``/pipelines/validate``
    beats ``/pipelines/{pipeline_id}``.
    """
    candidates = []
    for template, item in openapi_doc()["paths"].items():
        if method not in item:
            continue
        pieces = (re.escape(piece) for piece in _PARAM.split(API_PREFIX + template))
        if re.fullmatch("[^/]+".join(pieces), path):
            candidates.append((template.count("{"), template, item[method]))
    if not candidates:
        return None
    _, template, operation = min(candidates, key=lambda item: item[0])
    return template, operation


def parse_sse(text: str) -> list[dict[str, Any]]:
    """Split an event-stream body into frames of ``id``, ``event``, ``data``, ``retry``."""
    frames = []
    for block in text.split("\n\n"):
        frame: dict[str, Any] = {}
        for line in block.splitlines():
            name, _, value = line.partition(": ")
            if name == "data":
                frame["data"] = json.loads(value)
            elif name in {"id", "event", "retry"}:
                frame[name] = value
        if frame:
            frames.append(frame)
    return frames


def validate(schema: dict[str, Any], body: Any) -> None:
    """Validate *body* against a contract schema (Draft 2020-12)."""
    jsonschema.Draft202012Validator(with_components(schema)).validate(body)


@dataclass
class ContractChecker:
    """Validates real responses against the contract and records coverage.

    Attributes:
        operations: Operation ids whose responses were checked.
        statuses: ``(operation id, status)`` pairs that were checked.
    """

    operations: set[str] = field(default_factory=set)
    statuses: set[tuple[str, int]] = field(default_factory=set)

    def check(self, response: Any, expect: int | None = None) -> Any:
        """Validate one response; return its decoded body (frames for SSE).

        Args:
            response: A ``TestClient`` response to a ``/v1`` request.
            expect: Status the test expects, checked first.

        Returns:
            The JSON body, or the parsed frames of an event stream.
        """
        if expect is not None:
            assert response.status_code == expect, (response.status_code, response.text)
        method = response.request.method.lower()
        path = urlsplit(str(response.request.url)).path
        matched = match_operation(method, path)
        assert matched is not None, f"{method.upper()} {path} is not in the contract"
        template, operation = matched
        status = response.status_code
        declared = operation["responses"].get(str(status))
        assert declared is not None, (
            f"{method.upper()} {template} returned {status}, which the contract does not declare"
        )
        declared = resolve(declared)
        media = response.headers.get("content-type", "").split(";")[0].strip()
        content = declared.get("content", {})
        assert media in content, f"{template} {status}: undeclared media type {media!r}"
        for header in declared.get("headers", {}):
            if header.lower() != "set-cookie":
                assert header in response.headers, f"{template} {status}: missing {header}"
        if media == "text/event-stream":
            body: Any = parse_sse(response.text)
            self._check_frames(operation, body)
        else:
            body = response.json()
            validate(content[media]["schema"], body)
        self.operations.add(operation["operationId"])
        self.statuses.add((operation["operationId"], status))
        return body

    @staticmethod
    def _check_frames(operation: dict[str, Any], frames: list[dict[str, Any]]) -> None:
        """Validate every event frame against ``x-omrg-sse-events``.

        A GET stream reconnects, so it must open with a ``retry`` hint. A
        stream answering a request body (``streamAnswer``) never reconnects
        and sends no hint.
        """
        schemas = operation["x-omrg-sse-events"]
        assert frames, "the stream sent no frame"
        if "requestBody" not in operation:
            assert frames[0].get("retry"), "the stream must open with a retry hint"
            frames = frames[1:]
        for frame in frames:
            assert "event" in frame and "data" in frame, frame
            name = schemas.get(frame["event"]) or schemas["*"]
            validate({"$ref": f"#/components/schemas/{name}"}, frame["data"])
