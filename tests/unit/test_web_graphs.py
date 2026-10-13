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
    created = client.post(
        "/v1/pipelines", json={"title": "Search", "layout": {"zoom": 1}}, headers=ORIGIN
    )
    assert created.status_code == 201, created.text
    pipeline_id = created.json()["pipeline"]["pipeline_id"]
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
    other = client.post("/v1/pipelines", json={"title": "Other"}, headers=ORIGIN).json()
    wrong = client.get(
        f"/v1/pipelines/{other['pipeline']['pipeline_id']}/revisions/{revision['revision_id']}"
    )
    assert wrong.status_code == 404


def test_graph_saves_need_graph_scope(client: Any) -> None:
    client.cookies.clear()
    reader = bearer(client.policy, "read", "run")
    assert client.post("/v1/pipelines", json={"title": "x"}, headers=reader).status_code == 403
    editor = bearer(client.policy, "graph")
    assert client.post("/v1/pipelines", json={"title": "x"}, headers=editor).status_code == 201


def test_reserved_layout_key_is_refused(client: Any) -> None:
    response = client.post(
        "/v1/pipelines", json={"title": "x", "layout": {"omrg_task": "ingest"}}, headers=ORIGIN
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
    pipeline = client.post("/v1/pipelines", json={"title": "x"}, headers=ORIGIN).json()
    pipeline_id = pipeline["pipeline"]["pipeline_id"]
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
