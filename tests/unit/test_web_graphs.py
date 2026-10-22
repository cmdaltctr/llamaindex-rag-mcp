"""Tests for the graph routes: catalogue, pipelines, layouts, revisions, validation.

Task 6.6. A real Engine over in-memory fakes gives the real catalogue and
graph validation; the records live in a real SQLite workspace on
``tmp_path``. Direct invalid submissions get the structured issues and
never reach execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_runs_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    build_app,
    graph,
    login,
    make_engine,
    new_pipeline,
    save_revision,
    submit,
)


@pytest.fixture
def engine(effective_settings: Any) -> Any:
    return make_engine(effective_settings)


@pytest.fixture
def client(tmp_path: Path, engine: Any) -> Any:
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as test_client:
        login(test_client, policy)
        test_client.policy = policy  # type: ignore[attr-defined]
        yield test_client


# ── Catalogue ────────────────────────────────────────────────────────────


def test_catalogue_lists_operations_with_unavailable_reasons(client: Any) -> None:
    response = client.get("/v1/pipeline-operations")
    assert response.status_code == 200, response.text
    operations = {op["operation_id"]: op for op in response.json()["operations"]}
    assert operations["retrieve.dense"]["available"] is True
    # This Engine has no reranker: the catalogue says so and why.
    rerank = operations["select.rerank"]
    assert rerank["available"] is False
    assert any("reranker" in reason for reason in rerank["unavailable_reasons"])


def test_catalogue_needs_read_scope(client: Any) -> None:
    client.cookies.clear()
    assert client.get("/v1/pipeline-operations").status_code == 401
    runner = bearer(client.policy, "run")
    assert client.get("/v1/pipeline-operations", headers=runner).status_code == 403
    reader = bearer(client.policy, "read")
    assert client.get("/v1/pipeline-operations", headers=reader).status_code == 200


# ── Pipelines, layouts and revisions ─────────────────────────────────────


def test_pipeline_lifecycle_keeps_layout_out_of_revisions(client: Any) -> None:
    pipeline_id = new_pipeline(client.app, "Search", {"zoom": 1})["pipeline_id"]
    first = client.post(
        f"/v1/pipelines/{pipeline_id}/revisions", json={"document": graph()}, headers=ORIGIN
    )
    assert first.status_code == 201
    revision = first.json()["revision"]
    assert first.json()["created"] is True

    moved = client.put(
        f"/v1/pipelines/{pipeline_id}/layout",
        json={"layout": {"positions": {"dense": {"x": 5, "y": 9}}}},
        headers=ORIGIN,
    )
    assert moved.status_code == 200
    fetched = client.get(f"/v1/pipelines/{pipeline_id}").json()
    assert fetched["pipeline"]["layout"] == {"positions": {"dense": {"x": 5, "y": 9}}}
    assert fetched["current_revision"]["revision_id"] == revision["revision_id"]
    revisions = client.get(f"/v1/pipelines/{pipeline_id}/revisions").json()["revisions"]
    assert len(revisions) == 1  # a layout save never creates a revision
    listed = client.get("/v1/pipelines").json()["pipelines"]
    assert [p["pipeline_id"] for p in listed] == [pipeline_id]


def test_identical_content_returns_the_existing_revision(client: Any) -> None:
    revision = save_revision(client)
    pipeline_id = revision["pipeline_id"]
    # Key order and a wrapped layout do not change the execution content.
    wrapped = {"graph": dict(reversed(list(graph(top_k=2).items()))), "layout": {"title": "x"}}
    again = client.post(
        f"/v1/pipelines/{pipeline_id}/revisions", json={"document": wrapped}, headers=ORIGIN
    )
    assert again.status_code == 200
    assert again.json()["created"] is False
    assert again.json()["revision"]["revision_id"] == revision["revision_id"]
    changed = client.post(
        f"/v1/pipelines/{pipeline_id}/revisions",
        json={"document": graph(top_k=3)},
        headers=ORIGIN,
    )
    assert changed.status_code == 201
    assert changed.json()["revision"]["revision_number"] == 2
    one = client.get(f"/v1/pipelines/{pipeline_id}/revisions/{revision['revision_id']}")
    assert one.json()["revision"]["content_hash"] == revision["content_hash"]


def test_unknown_pipeline_and_revision_are_404(client: Any) -> None:
    assert client.get("/v1/pipelines/nope").status_code == 404
    assert client.get("/v1/pipelines/nope/revisions").status_code == 404
    response = client.put("/v1/pipelines/nope/layout", json={"layout": {}}, headers=ORIGIN)
    assert response.status_code == 404
    assert response.json()["status"] == "error"
    revision = save_revision(client)
    other = new_pipeline(client.app, "Other")
    wrong = client.get(f"/v1/pipelines/{other['pipeline_id']}/revisions/{revision['revision_id']}")
    assert wrong.status_code == 404


def test_graph_saves_need_graph_scope(client: Any) -> None:
    pipeline_id = new_pipeline(client.app, "x")["pipeline_id"]
    revisions = f"/v1/pipelines/{pipeline_id}/revisions"
    client.cookies.clear()
    reader = bearer(client.policy, "read", "run")
    body = {"document": graph()}
    assert client.post(revisions, json=body, headers=reader).status_code == 403
    editor = bearer(client.policy, "graph")
    assert client.post(revisions, json=body, headers=editor).status_code == 201


def test_reserved_layout_key_is_refused(client: Any) -> None:
    pipeline_id = new_pipeline(client.app, "x")["pipeline_id"]
    response = client.put(
        f"/v1/pipelines/{pipeline_id}/layout",
        json={"layout": {"omrs_task": "ingest"}},
        headers=ORIGIN,
    )
    assert response.status_code == 400


# ── Direct invalid submissions ───────────────────────────────────────────


def _invalid_documents() -> dict[str, tuple[dict[str, Any], str]]:
    bad_port = graph()
    bad_port["nodes"].append({"id": "loop", "operation": "context.assemble"})
    bad_port["edges"] += [
        {"source": {"node": "context", "port": "context"}, "target": {"node": "loop", "port": "x"}},
    ]
    unknown = graph()
    unknown["nodes"][1]["operation"] = "retrieve.nothing"
    executable = graph()
    executable["nodes"][0]["params"] = {"query_prefix": "__import__('os').system('id')"}
    version = graph()
    version["schema_version"] = 99
    return {
        "unknown operation": (unknown, "unknown_operation"),
        "executable text": (executable, "executable_text"),
        "schema version": (version, "unsupported_schema_version"),
        "bad port": (bad_port, "unknown_port"),
    }


@pytest.mark.parametrize("case", list(_invalid_documents()))
def test_invalid_graph_gets_structured_issues_and_never_runs(
    client: Any, engine: Any, case: str
) -> None:
    document, code = _invalid_documents()[case]
    response = client.post("/v1/pipelines/validate", json={"document": document}, headers=ORIGIN)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["status"] == "error"
    assert body["error_type"] == "validation"
    assert code in {issue["code"] for issue in body["issues"]}, body["issues"]
    assert all(set(issue) >= {"code", "message", "node_id", "port"} for issue in body["issues"])
    assert engine.runs == []


def _edge(src: str, src_port: str, dst: str, dst_port: str) -> dict[str, Any]:
    return {"source": {"node": src, "port": src_port}, "target": {"node": dst, "port": dst_port}}


def test_cycle_is_rejected_with_node_names(client: Any, engine: Any) -> None:
    document = graph()
    document["nodes"].append({"id": "again", "operation": "select.threshold"})
    # select -> again -> select replaces dense -> select: a feedback loop.
    document["edges"] = [
        _edge("prepare", "query", "dense", "query"),
        _edge("select", "evidence", "again", "evidence"),
        _edge("again", "evidence", "select", "evidence"),
        _edge("select", "evidence", "context", "evidence"),
    ]
    response = client.post("/v1/pipelines/validate", json={"document": document}, headers=ORIGIN)
    assert response.status_code == 422
    cycles = [i for i in response.json()["issues"] if i["code"] == "cycle"]
    assert cycles, response.json()["issues"]
    assert "select" in cycles[0]["message"] and "again" in cycles[0]["message"]
    assert engine.runs == []


def test_revision_save_rejects_unsupported_schema_before_storage(client: Any) -> None:
    pipeline_id = new_pipeline(client.app, "x")["pipeline_id"]
    document = graph()
    document["schema_version"] = 2
    response = client.post(
        f"/v1/pipelines/{pipeline_id}/revisions", json={"document": document}, headers=ORIGIN
    )
    assert response.status_code == 422
    assert response.json()["issues"][0]["code"] == "unsupported_schema_version"
    assert client.get(f"/v1/pipelines/{pipeline_id}/revisions").json()["revisions"] == []


def test_invalid_saved_revision_is_refused_at_submission(client: Any, engine: Any) -> None:
    document = graph()
    document["nodes"][1]["operation"] = "retrieve.nothing"
    revision = save_revision(client, document)
    response = submit(client, revision["revision_id"])
    assert response.status_code == 422
    assert "unknown_operation" in {issue["code"] for issue in response.json()["issues"]}
    assert client.get("/v1/runs").json()["runs"] == []  # no record was written
    assert engine.runs == []


def test_valid_draft_and_admission_checks(client: Any, engine: Any) -> None:
    draft = client.post("/v1/pipelines/validate", json={"document": graph()}, headers=ORIGIN)
    assert draft.status_code == 200, draft.text
    assert draft.json()["valid"] is True
    assert draft.json()["admitted"] is False
    assert draft.json()["order"] == ["prepare", "dense", "select", "context"]
    admitted = client.post(
        "/v1/pipelines/validate",
        json={"document": graph(), "inputs": {"query": "text"}},
        headers=ORIGIN,
    )
    assert admitted.status_code == 200
    body = admitted.json()
    assert body["admitted"] is True
    assert body["graph_identity"]
    assert {n["node_id"] for n in body["nodes"]} == {"prepare", "dense", "select", "context"}
    missing = client.post(
        "/v1/pipelines/validate", json={"document": graph(), "inputs": {}}, headers=ORIGIN
    )
    assert missing.status_code == 422
    assert "missing_graph_input" in {i["code"] for i in missing.json()["issues"]}
    assert engine.runs == []


def test_routes_without_run_service_answer_503(tmp_path: Path, engine: Any) -> None:
    app, policy = build_app(tmp_path, engine, with_runs=False)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.get("/v1/pipelines")
    assert response.status_code == 503
    assert response.json()["status"] == "error"


# ── Draft check: effective step values (unify-profiles-and-pipelines, D24) ──


class _ByCollection:
    """A resolver with a distinct ``top_k`` per collection, so the value shows the collection."""

    def __init__(self, effective_settings: Any, tops: dict[str, int]) -> None:
        self._settings = {
            name: effective_settings(**{"retrieval.top_k": top}) for name, top in tops.items()
        }
        self._env_overrides: dict[str, str] = {}

    def resolve(self, collection: str) -> Any:
        if collection not in self._settings:
            raise ValueError(f"Collection {collection!r} has an invalid profile tag.")
        return self._settings[collection]

    def _load_effective(self, profile: str) -> Any:
        raise ValueError(f"unknown profile {profile!r}")


_TOPS = {"documents": 10, "kb": 20, "graphcol": 30, "nodecol": 40}


@pytest.fixture
def tops_client(tmp_path: Path, effective_settings: Any) -> Any:
    from tests.unit.test_engine_pipelines_support import FakeEmbedder, FakeStore, chunks
    from tests.unit.test_web_runs_support import GatedEngine

    engine = GatedEngine(
        effective_settings(),
        store=FakeStore(chunks()),
        embed_model=FakeEmbedder(),
        profile_resolver=_ByCollection(effective_settings, _TOPS),
    )
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as test_client:
        login(test_client, policy)
        yield test_client


def _validate(client: Any, document: dict[str, Any], **extra: Any) -> Any:
    return client.post(
        "/v1/pipelines/validate", json={"document": document, **extra}, headers=ORIGIN
    )


def _top_k(body: dict[str, Any], node_id: str) -> dict[str, Any]:
    node = next(n for n in body["nodes"] if n["node_id"] == node_id)
    return next(c for c in node["controls"] if c["lever"] == "retrieval.top_k")


def test_a_valid_draft_returns_the_controls_of_each_node(client: Any) -> None:
    response = _validate(client, graph())
    assert response.status_code == 200, response.text
    nodes = response.json()["nodes"]
    assert [n["node_id"] for n in nodes] == ["prepare", "dense", "select", "context"]
    prepare = next(n for n in nodes if n["node_id"] == "prepare")
    control = next(c for c in prepare["controls"] if c["lever"] == "retrieval.top_k")
    assert set(control) == {"lever", "value", "source", "detail"}
    assert control["source"] == "profile"


def test_draft_controls_equal_the_admitted_controls(client: Any) -> None:
    document = graph(top_k=3)
    draft = _validate(client, document).json()["nodes"]
    admitted = client.post(
        "/v1/pipelines/validate",
        json={"document": document, "inputs": {"query": "q"}},
        headers=ORIGIN,
    ).json()["nodes"]
    assert {n["node_id"]: n["controls"] for n in draft} == {
        n["node_id"]: n["controls"] for n in admitted
    }
    assert _top_k({"nodes": draft}, "prepare") == {
        "lever": "retrieval.top_k",
        "value": 3,
        "source": "node",
        "detail": "node 'prepare' parameter",
    }


def test_the_collection_comes_from_the_node_then_graph_then_request_then_host(
    tops_client: Any,
) -> None:
    def value(document: dict[str, Any], **extra: Any) -> int:
        response = _validate(tops_client, document, **extra)
        assert response.status_code == 200, response.text
        return _top_k(response.json(), "prepare")["value"]

    plain = graph()
    assert value(plain) == 10  # host default collection
    assert value(plain, collection="kb") == 20  # request collection
    named = graph()
    named["collection"] = "graphcol"
    assert value(named, collection="kb") == 30  # graph collection wins over the request
    node = graph()
    node["collection"] = "graphcol"
    next(n for n in node["nodes"] if n["id"] == "prepare")["params"] = {"collection": "nodecol"}
    assert value(node, collection="kb") == 40  # node parameter wins over the graph


def test_a_draft_with_an_unconnected_port_returns_422_with_nodes_for_valid_nodes(
    client: Any,
) -> None:
    document = graph()
    document["edges"] = [e for e in document["edges"] if e["target"]["node"] != "select"]
    response = _validate(client, document)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["issues"]
    assert {n["node_id"] for n in body["nodes"]} >= {"prepare", "dense"}
    assert all(n["controls"] is not None for n in body["nodes"])


def test_a_node_with_invalid_parameters_gets_no_controls(client: Any) -> None:
    document = graph()
    next(n for n in document["nodes"] if n["id"] == "prepare")["params"] = {"top_k": 0}
    response = _validate(client, document)
    assert response.status_code == 422
    node_ids = {n["node_id"] for n in response.json()["nodes"]}
    assert "prepare" not in node_ids and "dense" in node_ids


def test_a_collection_whose_profile_does_not_resolve_gives_that_node_no_controls(
    tops_client: Any,
) -> None:
    document = graph()
    next(n for n in document["nodes"] if n["id"] == "prepare")["params"] = {"collection": "missing"}
    response = _validate(tops_client, document)
    ids = {n["node_id"] for n in (response.json().get("nodes") or [])}
    assert "prepare" not in ids and "dense" in ids


def test_an_admission_failure_carries_no_draft_nodes(client: Any) -> None:
    response = client.post(
        "/v1/pipelines/validate", json={"document": graph(), "inputs": {}}, headers=ORIGIN
    )
    assert response.status_code == 422
    assert "nodes" not in response.json()
