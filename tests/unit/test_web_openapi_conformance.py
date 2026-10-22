"""Runtime conformance of the versioned OpenAPI contract (task 6.7).

These tests read the real FastAPI routes and compare them with
``transports/api/openapi.yaml``: route set, operation ids, scopes and
session-only access, declared failure statuses, request bodies (fields,
required values, defaults, nullability, bounds and unknown-key policy)
and parameters. Every check derives the runtime side from the code, so a
new route, field or default fails here until the contract changes too.
The response flows live in the ``_documents`` and ``_runs`` modules.
"""

from __future__ import annotations

import types
import typing
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

import yaml  # noqa: E402
from openapi_spec_validator import validate as validate_spec  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from tests.unit.test_web_documents_support import OPENAPI, openapi_doc  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import (  # noqa: E402
    FAMILIES,
    build_bare_app,
    contract_operations,
    resolve,
    route_access,
    runtime_operations,
)

from omrs.transports.api.security import BEARER_SCOPES, SESSION_SCOPES  # noqa: E402

BOUNDS = ("minimum", "maximum", "minLength", "maxLength", "minItems", "maxItems")
_METADATA_BOUNDS = {
    "ge": "minimum",
    "le": "maximum",
    "min_length": "minLength",
    "max_length": "maxLength",
}


@pytest.fixture(scope="module")
def runtime(tmp_path_factory: pytest.TempPathFactory) -> dict[tuple[str, str], Any]:
    return runtime_operations(build_bare_app(tmp_path_factory.mktemp("bare")))


def _label(key: tuple[str, str]) -> str:
    return f"{key[0].upper()} {key[1]}"


# ── Document ─────────────────────────────────────────────────────────────


def test_contract_is_valid_openapi_31_and_versioned() -> None:
    with OPENAPI.open(encoding="utf-8") as handle:
        doc = yaml.safe_load(handle)
    validate_spec(doc)
    assert doc["openapi"].startswith("3.1")
    major = int(doc["info"]["version"].split(".")[0])
    assert major >= 2, "the runtime contract replaced the 1.x contract-only document"
    assert "no runtime" not in doc["info"]["description"].lower()
    assert set(doc["components"]["securitySchemes"]) == {"sessionCookie", "bearerToken"}


# ── Routes ───────────────────────────────────────────────────────────────


def test_every_runtime_route_is_declared(runtime: dict) -> None:
    missing = sorted(_label(key) for key in set(runtime) - set(contract_operations()))
    assert not missing, f"Runtime routes missing from openapi.yaml: {missing}"


def test_every_declared_operation_is_implemented(runtime: dict) -> None:
    extra = sorted(_label(key) for key in set(contract_operations()) - set(runtime))
    assert not extra, f"openapi.yaml declares operations the runtime lacks: {extra}"


def test_response_flows_cover_every_operation() -> None:
    """Each flow test asserts its family; together they cover the contract."""
    declared = {operation["operationId"] for operation in contract_operations().values()}
    covered = frozenset().union(*FAMILIES.values())
    assert declared == covered, {
        "not exercised": sorted(declared - covered),
        "unknown": sorted(covered - declared),
    }


def test_operation_ids_agree_where_the_runtime_names_them(runtime: dict) -> None:
    contract = contract_operations()
    wrong = {
        _label(key): (route.operation_id, contract[key]["operationId"])
        for key, route in runtime.items()
        if key in contract and route.operation_id
        if route.operation_id != contract[key]["operationId"]
    }
    assert not wrong, f"operationId drift (runtime, contract): {wrong}"
    ids = [operation["operationId"] for operation in contract.values()]
    assert len(ids) == len(set(ids)), "operationId values must be unique"


# ── Authorisation ────────────────────────────────────────────────────────


def test_scope_catalogue_matches_the_access_policy() -> None:
    catalogue = openapi_doc()["x-omrs-scope-catalogue"]
    assert set(catalogue) == set(SESSION_SCOPES)
    for scope, entry in catalogue.items():
        assert entry["session_only"] is (scope not in BEARER_SCOPES), scope


def test_declared_scopes_match_route_dependencies(runtime: dict) -> None:
    contract = contract_operations()
    problems = []
    for key, route in sorted(runtime.items()):
        operation = contract.get(key)
        if operation is None:
            continue
        access = route_access(route)
        expected = [] if access.scope is None else [access.scope]
        if operation.get("x-omrs-scopes") != expected:
            problems.append(f"{_label(key)}: x-omrs-scopes {operation.get('x-omrs-scopes')}")
        if access.scope is None:
            wanted: list[dict[str, list[str]]] = []
        else:
            wanted = [{"sessionCookie": expected}]
            if not access.session_only:
                wanted.append({"bearerToken": expected})
        if operation.get("security") != wanted:
            problems.append(f"{_label(key)}: security {operation.get('security')} != {wanted}")
    assert not problems, "Scope drift (runtime scope wins):\n" + "\n".join(problems)


def test_public_operations_are_only_health_and_bootstrap(runtime: dict) -> None:
    public = sorted(_label(k) for k, route in runtime.items() if route_access(route).scope is None)
    assert public == ["GET /v1/health", "POST /v1/session"]


def test_access_and_failure_statuses_are_declared(runtime: dict) -> None:
    contract = contract_operations()
    problems = []
    for key, route in sorted(runtime.items()):
        operation = contract.get(key)
        if operation is None:
            continue
        access = route_access(route)
        needed = {"400", "403", "500"}  # request guard, origin guard, envelope handler
        if access.scope is not None:
            needed |= {"401"}
        if access.needs_runtime:
            needed |= {"503"}
        missing = needed - set(operation["responses"])
        if missing:
            problems.append(f"{_label(key)} lacks {sorted(missing)}")
    assert not problems, "\n".join(problems)


# ── Request bodies ───────────────────────────────────────────────────────


def _model_of(annotation: Any) -> type[BaseModel] | None:
    """Return the model inside *annotation* (``Model`` or ``Model | None``)."""
    options = typing.get_args(annotation) if _is_union(annotation) else (annotation,)
    for option in options:
        if isinstance(option, type) and issubclass(option, BaseModel):
            return option
    return None


def _is_union(annotation: Any) -> bool:
    return typing.get_origin(annotation) in (typing.Union, types.UnionType)


def _allows_none(annotation: Any) -> bool:
    return _is_union(annotation) and type(None) in typing.get_args(annotation)


def _branches(prop: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the resolved branches of a property (``oneOf``/``anyOf`` or itself)."""
    options = prop.get("oneOf") or prop.get("anyOf") or [prop]
    return [resolve(option) for option in options]


def _types(prop: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for branch in _branches(prop):
        kind = branch.get("type", "object" if "properties" in branch else None)
        found |= set(kind) if isinstance(kind, list) else {kind}
    return found - {None}


def _merged(schema: dict[str, Any]) -> dict[str, Any]:
    """Merge the non-null branches of a schema into one mapping."""
    merged: dict[str, Any] = {}
    for branch in _branches(schema):
        if branch.get("type") != "null":
            merged.update(branch)
    return merged


def _runtime_merged(schema: dict[str, Any]) -> dict[str, Any]:
    """Merge a pydantic property schema; nested model links are compared separately."""
    merged: dict[str, Any] = {}
    for branch in schema.get("anyOf", [schema]):
        if branch.get("type") != "null" and "$ref" not in branch:
            merged.update(branch)
    return merged


def _compare_model(model: type[BaseModel], schema: dict[str, Any], where: str) -> list[str]:
    schema = resolve(schema)
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    problems = []
    fields = model.model_fields
    for name in sorted(set(fields) - set(props)):
        problems.append(f"{where}.{name}: implemented field missing from the contract")
    for name in sorted(set(props) - set(fields)):
        problems.append(f"{where}.{name}: declared field the runtime does not accept")
    forbid = model.model_config.get("extra") == "forbid"
    if forbid != (schema.get("additionalProperties") is False):
        problems.append(f"{where}: additionalProperties must be {not forbid}")
    runtime_json = model.model_json_schema()["properties"]
    for name in sorted(set(fields) & set(props)):
        info, prop, label = fields[name], props[name], f"{where}.{name}"
        if info.is_required() != (name in required):
            problems.append(f"{label}: required is {info.is_required()} at runtime")
        problems += _compare_default(info, prop, label)
        if _allows_none(info.annotation) != ("null" in _types(prop)):
            problems.append(f"{label}: nullable is {_allows_none(info.annotation)} at runtime")
        runtime_prop, contract_prop = _runtime_merged(runtime_json[name]), _merged(prop)
        for bound in BOUNDS:
            if runtime_prop.get(bound) != contract_prop.get(bound):
                problems.append(
                    f"{label}: {bound} {contract_prop.get(bound)!r} != {runtime_prop.get(bound)!r}"
                )
        if "enum" in runtime_prop and set(runtime_prop["enum"]) != set(
            contract_prop.get("enum", ())
        ):
            problems.append(f"{label}: enum differs from {runtime_prop['enum']}")
        nested = _model_of(info.annotation)
        if nested is not None:
            branch = next(b for b in prop.get("oneOf", [prop]) if b.get("type") != "null")
            problems += _compare_model(nested, branch, label)
    return problems


def _compare_default(info: Any, prop: dict[str, Any], label: str) -> list[str]:
    """Apply the default rules: concrete defaults match; ``None`` declares none."""
    if info.default_factory is not None:
        expected: Any = info.default_factory()
    elif info.is_required() or info.default is None:
        if "default" in prop:
            return [f"{label}: declares default {prop['default']!r}; runtime has none"]
        return []
    else:
        expected = info.default
    if prop.get("default", ...) != expected:
        return [f"{label}: default {prop.get('default', '<absent>')!r} != {expected!r}"]
    return []


def test_request_bodies_match_runtime_models(runtime: dict) -> None:
    contract = contract_operations()
    problems = []
    for key, route in sorted(runtime.items()):
        operation = contract.get(key)
        if operation is None:
            continue
        content = operation.get("requestBody", {}).get("content", {})
        model = _model_of(route.body_field.field_info.annotation) if route.body_field else None
        if model is None:
            if "application/json" in content:
                problems.append(f"{_label(key)}: declares a JSON body the runtime does not read")
            continue
        if "application/json" not in content:
            problems.append(f"{_label(key)}: JSON body {model.__name__} is not declared")
            continue
        required = operation["requestBody"].get("required", False)
        if required != route.body_field.field_info.is_required():
            problems.append(f"{_label(key)}: requestBody.required should be {not required}")
        schema = content["application/json"]["schema"]
        problems += _compare_model(model, schema, f"{_label(key)} {model.__name__}")
    assert not problems, "Request body drift:\n" + "\n".join(problems)


# ── Parameters ───────────────────────────────────────────────────────────


def _declared_parameters(operation: dict[str, Any], where: str) -> dict[str, dict]:
    params = [resolve(p) for p in operation.get("parameters", [])]
    return {p["name"].lower(): p for p in params if p["in"] == where}


def _parameter_problems(param: Any, declared: dict[str, Any], label: str) -> list[str]:
    info, schema = param.field_info, declared["schema"]
    problems = []
    if info.is_required() != declared.get("required", False):
        problems.append(f"{label}: required is {info.is_required()} at runtime")
    problems += _compare_default(info, schema, label)
    merged = _merged(schema)
    for item in info.metadata:
        for attribute, bound in _METADATA_BOUNDS.items():
            value = getattr(item, attribute, None)
            if value is not None and merged.get(bound) != value:
                problems.append(f"{label}: {bound} {merged.get(bound)!r} != {value!r}")
    return problems


def test_parameters_match_runtime(runtime: dict) -> None:
    contract = contract_operations()
    problems = []
    for key, route in sorted(runtime.items()):
        operation = contract.get(key)
        if operation is None:
            continue
        dependant = route.dependant
        if len(_declared_parameters(operation, "path")) != len(dependant.path_params):
            problems.append(f"{_label(key)}: path parameter count differs")
        declared = _declared_parameters(operation, "query")
        names = {param.alias.lower(): param for param in dependant.query_params}
        if set(names) != set(declared):
            problems.append(f"{_label(key)}: query {sorted(declared)} != {sorted(names)}")
        for name in set(names) & set(declared):
            problems += _parameter_problems(names[name], declared[name], f"{_label(key)} ?{name}")
        headers = _declared_parameters(operation, "header")
        for param in dependant.header_params:
            if param.alias.lower() not in headers:
                problems.append(f"{_label(key)}: header {param.alias} is not declared")
    assert not problems, "Parameter drift:\n" + "\n".join(problems)


# ── Job and destructive semantics ────────────────────────────────────────


def _operation(operation_id: str) -> dict[str, Any]:
    matches = [op for op in contract_operations().values() if op["operationId"] == operation_id]
    assert len(matches) == 1, operation_id
    return matches[0]


def _response_ref(operation_id: str, status: str) -> str:
    content = resolve(_operation(operation_id)["responses"][status])["content"]
    return content["application/json"]["schema"]["$ref"].rsplit("/", 1)[1]


@pytest.mark.parametrize(
    ("operation_id", "resource"),
    [
        ("ingestPath", "Job"),
        ("generateCodebaseMap", "Job"),
        ("submitRun", "RunEnvelope"),
        ("retryRun", "RunEnvelope"),
    ],
)
def test_long_running_operations_declare_202_with_an_identifier(
    operation_id: str, resource: str
) -> None:
    assert _response_ref(operation_id, "202") == resource
    assert "429" in _operation(operation_id)["responses"]
    schemas = openapi_doc()["components"]["schemas"]
    if resource == "Job":
        assert {"job_id", "status"} <= set(schemas["Job"]["required"])
        assert schemas["Job"]["properties"]["status"]["enum"] == [
            "queued",
            "running",
            "completed",
            "failed",
        ]
    else:
        assert {"run_id", "status"} <= set(schemas["RunRecord"]["required"])


def test_status_event_and_cancel_routes_are_protected() -> None:
    for operation_id in ("getJobStatus", "getRun", "listRunEvents", "streamRunEvents"):
        assert _operation(operation_id)["x-omrs-scopes"] == ["read"], operation_id
    assert _operation("cancelRun")["x-omrs-scopes"] == ["run"]
    stream = _operation("streamRunEvents")
    assert "text/event-stream" in stream["responses"]["200"]["content"]
    assert set(stream["x-omrs-sse-events"].values()) <= set(openapi_doc()["components"]["schemas"])


def test_display_name_operation_is_session_only_without_confirmation() -> None:
    operation = _operation("setCollectionDisplayName")
    assert operation["security"] == [{"sessionCookie": ["manage"]}]
    assert operation["x-omrs-scopes"] == ["manage"]
    assert {"400", "403", "404"} <= set(operation["responses"])
    assert not {"409", "428"} & set(operation["responses"])


@pytest.mark.parametrize(
    ("operation_id", "statuses"),
    [
        ("deleteDocuments", {"409", "428"}),
        ("changeCollectionProfile", {"409", "428"}),
        ("applyWorkspaceCleanup", {"409"}),
    ],
)
def test_destructive_operations_are_session_only_with_confirmation(
    operation_id: str, statuses: set[str]
) -> None:
    operation = _operation(operation_id)
    assert operation["security"] == [{"sessionCookie": ["manage"]}]
    assert statuses <= set(operation["responses"])


def test_profile_change_branches_are_mutually_exclusive() -> None:
    schemas = openapi_doc()["components"]["schemas"]
    preview, applied = schemas["ProfilePreview"], schemas["ProfileChangeResult"]
    assert set(preview["required"]) >= {"status", "contract", "confirm_required"}
    assert set(applied["required"]) >= {"status", "collection", "profile", "chunk_count_unchanged"}
    assert preview["properties"]["status"]["enum"] == ["preview"]
    assert applied["properties"]["status"]["enum"] == ["ok"]
    assert "new_profile" in preview["properties"]["contract"]["properties"]


def test_unknown_api_path_never_serves_html(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient
    from tests.unit.test_web_openapi_conformance_support import validate

    from omrs.transports.api.app import create_app
    from omrs.transports.api.lifespan import WebConfig

    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    config = WebConfig(workspace=tmp_path / "ws", port=8765, static_dir=static)
    app = create_app(config, engine_factory=lambda: None)
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    assert client.get("/library").headers["content-type"].startswith("text/html")
    for method, path in (("get", "/v1/nope"), ("post", "/v1/nope/deeper"), ("put", "/v1/health")):
        response = client.request(method, path, headers={"Accept": "text/html"})
        assert response.status_code in {404, 405}, (path, response.status_code)
        assert response.headers["content-type"].startswith("application/json"), path
        assert "<html" not in response.text.lower()
        validate({"$ref": "#/components/schemas/Error"}, response.json())
