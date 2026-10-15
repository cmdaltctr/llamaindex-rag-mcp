"""Tests for the reviewed document endpoints (task 6.4).

Covers collection and source listing, search and answer delegation to
the owning Engine, profile-resolved defaults, the error envelope, scope
checks, and conformance of every response with ``openapi.yaml``.
Stores are real LanceDB tables under ``tmp_path``; the embedder is a
mock and the answer model is a fake. No model or network call happens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    FakeLLM,
    RecordingEngine,
    assert_conforms,
    bearer,
    build_app,
    lance_store,
    login,
    make_engine,
    seed,
)

COLLECTION = "notes"
SEARCH = f"/v1/collections/{COLLECTION}/search"
ANSWER = f"/v1/collections/{COLLECTION}/answer"


@pytest.fixture
def store(tmp_path: Path) -> Any:
    store = lance_store(tmp_path)
    seed(store, COLLECTION, str(tmp_path / "present.md"), 3)
    (tmp_path / "present.md").write_text("present", encoding="utf-8")
    seed(store, COLLECTION, str(tmp_path / "gone.md"), 2)
    seed(store, COLLECTION, "relative/name.md", 1)
    seed(store, "other", str(tmp_path / "x.md"), 1)
    return store


# ── Listing ──────────────────────────────────────────────────────────────


def test_collections_list_counts_and_conforms(
    tmp_path: Path, store: Any, effective_settings
) -> None:
    app, policy = build_app(tmp_path, make_engine(store, effective_settings()))
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.get("/v1/collections")
    assert response.status_code == 200
    body = response.json()
    assert_conforms("/collections", "get", 200, body)
    by_name = {row["name"]: row for row in body}
    assert by_name[COLLECTION] == {
        "name": COLLECTION,
        "document_count": 3,
        "chunk_count": 6,
        "profile": None,
        "store": {"name": "lancedb", "label": "LanceDB"},
    }
    assert by_name["other"]["chunk_count"] == 1


def test_sources_list_keeps_machine_local_orphan_semantics(
    tmp_path: Path, store: Any, effective_settings
) -> None:
    app, policy = build_app(tmp_path, make_engine(store, effective_settings()))
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.get(f"/v1/collections/{COLLECTION}/documents")
    assert response.status_code == 200
    body = response.json()
    assert_conforms("/collections/{collection}/documents", "get", 200, body)
    by_source = {row["source"]: row for row in body}
    assert by_source[str(tmp_path / "present.md")]["orphaned"] is False
    assert by_source[str(tmp_path / "gone.md")]["orphaned"] is True
    # Unknown availability is null, never reported as global loss.
    assert by_source["relative/name.md"]["orphaned"] is None
    assert by_source[str(tmp_path / "present.md")]["chunks"] == 3
    assert all(row["source_id"].startswith("src_") for row in body)


def test_sources_of_missing_collection_are_empty(
    tmp_path: Path, store: Any, effective_settings
) -> None:
    app, policy = build_app(tmp_path, make_engine(store, effective_settings()))
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.get("/v1/collections/absent/documents")
    assert response.status_code == 200
    assert response.json() == []


# ── Search ───────────────────────────────────────────────────────────────


def test_search_result_shape_conforms_with_lineage_and_score_kind(
    tmp_path: Path, store: Any, effective_settings
) -> None:
    app, policy = build_app(tmp_path, make_engine(store, effective_settings()))
    request = {"query": "chunk", "rerank": False, "hybrid": False, "similarity_threshold": 0.0}
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        plain = client.post(SEARCH, json=request, headers=ORIGIN)
        diag = client.post(SEARCH, json={**request, "diagnostics": True}, headers=ORIGIN)
    assert plain.status_code == 200, plain.text
    rows = plain.json()
    assert rows, "seeded collection must return rows"
    assert_conforms("/collections/{collection}/search", "post", 200, rows)
    assert_conforms("/collections/{collection}/search", "post", 200, diag.json())
    first = rows[0]
    assert first["score_kind"] == "dense_similarity_v1"
    assert first["source_id"].startswith("src_")
    assert first["chunk_id"].startswith("chk_")
    assert "id" not in first  # diagnostics-only key stays out
    assert "id" in diag.json()[0]


def test_search_passes_profile_resolved_controls_as_none(
    tmp_path: Path, store: Any, effective_settings
) -> None:
    engine = RecordingEngine(effective_settings(), store=store, embed_model=object())
    engine.search_rows = []
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.post(SEARCH, json={"query": "q"}, headers=ORIGIN)
    assert response.status_code == 200
    assert response.json() == []
    ((name, args, kwargs),) = engine.calls
    assert (name, args) == ("search", ("q",))
    assert kwargs["collection_name"] == COLLECTION
    # Omitted controls stay None so the Engine resolves the collection profile.
    for key in ("top_k", "similarity_threshold", "rerank", "hybrid", "metadata_filter"):
        assert kwargs[key] is None, key
    assert kwargs["expand_window"] == 0
    assert kwargs["include_diagnostics"] is False
    # The synchronous Engine search runs off the event loop.
    assert kwargs["_on_event_loop"] is False


def test_search_forwards_explicit_controls(tmp_path: Path, store: Any, effective_settings) -> None:
    engine = RecordingEngine(effective_settings(), store=store, embed_model=object())
    app, policy = build_app(tmp_path, engine)
    body = {
        "query": "q",
        "top_k": 3,
        "similarity_threshold": 0.4,
        "rerank": True,
        "hybrid": False,
        "expand_window": 2,
        "diagnostics": True,
        "metadata_filter": {"file_name": "a.md"},
    }
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        assert client.post(SEARCH, json=body, headers=ORIGIN).status_code == 200
    kwargs = engine.calls[0][2]
    assert kwargs["top_k"] == 3
    assert kwargs["similarity_threshold"] == 0.4
    assert kwargs["rerank"] is True
    assert kwargs["hybrid"] is False
    assert kwargs["expand_window"] == 2
    assert kwargs["include_diagnostics"] is True
    assert kwargs["metadata_filter"] == {"file_name": "a.md"}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"query": "q", "top_k": 0},
        {"query": "q", "similarity_threshold": 1.5},
        {"query": "q", "expand_window": -1},
        {"query": "q", "unknown_control": True},
    ],
)
def test_search_validation_uses_error_envelope(
    tmp_path: Path, store: Any, effective_settings, body: dict
) -> None:
    engine = RecordingEngine(effective_settings(), store=store, embed_model=object())
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.post(SEARCH, json=body, headers=ORIGIN)
    assert response.status_code == 400
    assert_conforms("/collections/{collection}/search", "post", 400, response.json())
    assert response.json()["error_type"] == "validation"
    assert engine.calls == []


def test_search_profile_error_is_validation_and_failure_is_not_leaked(
    tmp_path: Path, store: Any, effective_settings
) -> None:
    engine = RecordingEngine(effective_settings(), store=store, embed_model=object())
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        engine.raise_on["search"] = ValueError("Collection 'notes' has profile tag 'hybrid'.")
        invalid = client.post(SEARCH, json={"query": "q"}, headers=ORIGIN)
        engine.raise_on["search"] = RuntimeError("secret detail /private/path")
        failed = client.post(
            SEARCH, json={"query": "q", "metadata_filter": {"a": 1}}, headers=ORIGIN
        )
    assert invalid.status_code == 400
    assert invalid.json()["error_type"] == "validation"
    assert "hybrid" in invalid.json()["message"]
    assert failed.status_code == 500
    assert_conforms("/collections/{collection}/search", "post", 500, failed.json())
    assert failed.json()["error_type"] == "retrieval"
    assert "secret detail" not in failed.text


# ── Answer ───────────────────────────────────────────────────────────────


def test_answer_shape_conforms_with_deterministic_citations(
    tmp_path: Path, store: Any, effective_settings
) -> None:
    llm = FakeLLM()
    engine = make_engine(store, effective_settings(), answer_llm_factory=lambda: llm)
    app, policy = build_app(tmp_path, engine)
    request = {"query": "first?", "rerank": False, "hybrid": False, "similarity_threshold": 0.0}
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.post(ANSWER, json=request, headers=ORIGIN)
    assert response.status_code == 200, response.text
    body = response.json()
    assert_conforms("/collections/{collection}/answer", "post", 200, body)
    assert body["status"] == "ok"
    assert body["completion_source"] == "server"
    citation = body["citations"][0]
    assert citation["chunk_id"] in {row["chunk_id"] for row in body["evidence"]}
    assert len(llm.prompts) == 1


def test_answer_without_evidence_makes_no_model_call(
    tmp_path: Path, store: Any, effective_settings
) -> None:
    llm = FakeLLM()
    engine = make_engine(store, effective_settings(), answer_llm_factory=lambda: llm)
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.post("/v1/collections/empty/answer", json={"query": "q"}, headers=ORIGIN)
    body = response.json()
    assert response.status_code == 200
    assert_conforms("/collections/{collection}/answer", "post", 200, body)
    assert body["status"] == "no_evidence"
    assert llm.prompts == []


def test_answer_forwards_controls_and_validates_bounds(
    tmp_path: Path, store: Any, effective_settings
) -> None:
    engine = RecordingEngine(effective_settings(), store=store, embed_model=object())
    engine.answer_result = {"status": "ok"}
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        ok = client.post(ANSWER, json={"query": "q", "top_k": 4}, headers=ORIGIN)
        too_wide = client.post(ANSWER, json={"query": "q", "expand_window": 11}, headers=ORIGIN)
        too_long = client.post(ANSWER, json={"query": "x" * 4097}, headers=ORIGIN)
    assert ok.status_code == 200
    ((name, args, kwargs),) = engine.calls
    assert (name, args, kwargs["collection_name"], kwargs["top_k"]) == (
        "answer",
        ("q",),
        COLLECTION,
        4,
    )
    assert kwargs["rerank"] is None and kwargs["hybrid"] is None
    assert too_wide.status_code == 400
    assert too_long.status_code == 400


def test_answer_engine_failure_keeps_answer_error_shape(
    tmp_path: Path, store: Any, effective_settings
) -> None:
    engine = RecordingEngine(effective_settings(), store=store, embed_model=object())
    engine.raise_on["answer"] = RuntimeError("provider exploded")
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.post(ANSWER, json={"query": "q"}, headers=ORIGIN)
    body = response.json()
    assert response.status_code == 200
    assert_conforms("/collections/{collection}/answer", "post", 200, body)
    assert (body["status"], body["failure_stage"], body["completion_source"]) == (
        "error",
        None,
        "none",
    )
    assert body["error"].startswith("RuntimeError")


# ── Authorisation ────────────────────────────────────────────────────────


def test_read_routes_need_credentials_and_accept_read_bearer(
    tmp_path: Path, store: Any, effective_settings
) -> None:
    app, policy = build_app(tmp_path, make_engine(store, effective_settings()))
    reader = bearer(policy, "read")
    runner = bearer(policy, "run")
    with TestClient(app, base_url=BASE) as client:
        anonymous = client.get("/v1/collections")
        read_ok = client.get("/v1/collections", headers=reader)
        wrong_scope = client.get("/v1/collections", headers=runner)
        search_ok = client.post(
            SEARCH,
            json={"query": "q", "rerank": False, "hybrid": False},
            headers=reader,
        )
    assert anonymous.status_code == 401
    assert_conforms("/collections", "get", 401, anonymous.json())
    assert read_ok.status_code == 200
    assert wrong_scope.status_code == 403
    assert search_ok.status_code == 200


def test_cross_origin_search_with_session_is_rejected_before_engine(
    tmp_path: Path, store: Any, effective_settings
) -> None:
    engine = RecordingEngine(effective_settings(), store=store, embed_model=object())
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.post(SEARCH, json={"query": "q"}, headers={"Origin": "http://evil.test"})
    assert response.status_code == 403
    assert engine.calls == []
