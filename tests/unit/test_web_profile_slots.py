"""Slot pipelines of a profile: saves, layouts, reads and the withdrawn createPipeline.

unify-profiles-and-pipelines, design D7, D8, D19, D20, tasks 7.5-7.6.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    lance_store,
    login,
    make_engine,
    seed,
)
from tests.unit.test_web_runs_support import build_app  # noqa: E402

from omrg.core.profiles.resolver import ProfileResolver  # noqa: E402
from omrg.core.workspace import TASK_LAYOUT_KEY  # noqa: E402

COLLECTIONS = ("notes", "papers")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL__HYBRID_ENABLED", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__TOP_K"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def client(tmp_path: Path, effective_settings: Any) -> Iterator[TestClient]:
    store = lance_store(tmp_path)
    for name in COLLECTIONS:
        seed(store, name, f"/data/{name}.md", 2)
    settings = effective_settings()
    resolver = ProfileResolver(store=store, server_profile="documents", base=settings)
    engine = make_engine(store, settings, profile_resolver=resolver)
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as test_client:
        login(test_client, policy)
        test_client.policy = policy  # type: ignore[attr-defined]
        test_client.store = store  # type: ignore[attr-defined]
        yield test_client


def _profile(client: TestClient, title: str = "Mine", **body: Any) -> dict[str, Any]:
    payload = {"title": title, "source": "documents", **body}
    response = client.post("/v1/profiles", json=payload, headers=ORIGIN)
    assert response.status_code == 201, response.text
    return response.json()["profile"]


def _use(client: TestClient, profile_id: str, *collections: str) -> None:
    for name in collections:
        client.store.update_collection_metadata(name, {"profile": profile_id})  # type: ignore[attr-defined]


def _document(client: TestClient, pipeline_id: str) -> dict[str, Any]:
    revision = client.get(f"/v1/pipelines/{pipeline_id}").json()["current_revision"]
    return copy.deepcopy(revision["document"])


def _save(client: TestClient, pipeline_id: str, document: dict[str, Any]) -> Any:
    return client.post(
        f"/v1/pipelines/{pipeline_id}/revisions", json={"document": document}, headers=ORIGIN
    )


def _standalone(client: TestClient, title: str = "Loose", layout: dict | None = None) -> str:
    runs = client.app.state.runtime.run_service  # type: ignore[attr-defined]
    return runs.service.repository.create_pipeline(title, layout=layout)["pipeline_id"]


def _revision_count(client: TestClient, pipeline_id: str) -> int:
    return len(client.get(f"/v1/pipelines/{pipeline_id}/revisions").json()["revisions"])


# ── affected_collections ──────────────────────────────────────────────


def test_a_save_on_a_profile_in_use_names_the_affected_collections(client: TestClient) -> None:
    item = _profile(client)
    _use(client, item["profile_id"], *COLLECTIONS)
    document = _document(client, item["slots"]["search"])
    document["overrides"] = {"retrieval.top_k": 3}
    response = _save(client, item["slots"]["search"], document)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created"] is True and body["revision"]["revision_number"] == 2
    assert body["affected_collections"] == ["notes", "papers"]


def test_a_save_on_a_profile_in_no_use_lists_no_collection(client: TestClient) -> None:
    item = _profile(client)
    document = _document(client, item["slots"]["answer"])
    document["overrides"] = {"retrieval.top_k": 3}
    response = _save(client, item["slots"]["answer"], document)
    assert response.status_code == 201 and response.json()["affected_collections"] == []


def test_a_save_on_a_loose_pipeline_has_no_affected_collections_field(client: TestClient) -> None:
    pipeline_id = _standalone(client)
    document = _document(client, _profile(client)["slots"]["search"])
    document["profile"] = None
    response = _save(client, pipeline_id, document)
    assert response.status_code == 201, response.text
    assert "affected_collections" not in response.json()


# ── Breaking saves ────────────────────────────────────────────────────


def test_a_save_that_would_break_a_profile_in_use_is_refused(client: TestClient) -> None:
    item = _profile(client)
    _use(client, item["profile_id"], "notes")
    pipeline_id = item["slots"]["search"]
    document = _document(client, pipeline_id)
    before = client.get(f"/v1/pipelines/{pipeline_id}").json()["pipeline"]["current_revision_id"]
    document["outputs"] = []
    response = _save(client, pipeline_id, document)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["status"] == "error"
    assert any("needs an output named `results`" in r for r in body["not_ready_reasons"])
    assert _revision_count(client, pipeline_id) == 1
    now = client.get(f"/v1/pipelines/{pipeline_id}").json()["pipeline"]["current_revision_id"]
    assert now == before


def test_a_breaking_save_on_a_profile_in_no_use_is_accepted_and_shows_not_ready(
    client: TestClient,
) -> None:
    item = _profile(client)
    pipeline_id = item["slots"]["search"]
    document = _document(client, pipeline_id)
    document["outputs"] = []
    assert _save(client, pipeline_id, document).status_code == 201
    shown = client.get(f"/v1/profiles/{item['profile_id']}").json()["profile"]
    assert shown["ready"] is False
    assert any("Search pipeline" in r for r in shown["not_ready_reasons"])


def test_a_graph_that_fails_validation_is_refused_as_before(client: TestClient) -> None:
    item = _profile(client)
    pipeline_id = item["slots"]["search"]
    document = _document(client, pipeline_id)
    document["schema_version"] = 99
    response = _save(client, pipeline_id, document)
    assert response.status_code == 422 and _revision_count(client, pipeline_id) == 1


# ── The graph names the base profile (D8) ─────────────────────────────


@pytest.mark.parametrize("profile", [None, "codebase"])
def test_a_graph_that_names_another_profile_than_the_base_is_refused(
    client: TestClient, profile: str | None
) -> None:
    item = _profile(client)
    pipeline_id = item["slots"]["search"]
    document = _document(client, pipeline_id)
    document["profile"] = profile
    response = _save(client, pipeline_id, document)
    assert response.status_code == 400, response.text
    assert "documents" in response.json()["message"]
    assert _revision_count(client, pipeline_id) == 1


def test_a_codebase_profile_needs_the_codebase_name(client: TestClient) -> None:
    item = _profile(client, "Code", source="codebase")
    pipeline_id = item["slots"]["ingest"]
    document = _document(client, pipeline_id)
    document["profile"] = "documents"
    assert _save(client, pipeline_id, document).status_code == 400
    document["profile"] = "codebase"
    document["overrides"] = {"chunking.chunk_size": 400}
    assert _save(client, pipeline_id, document).status_code == 201


# ── Deleted profiles ──────────────────────────────────────────────────


def test_a_deleted_profile_refuses_new_revisions_and_layouts(client: TestClient) -> None:
    item = _profile(client)
    pipeline_id = item["slots"]["search"]
    document = _document(client, pipeline_id)
    document["overrides"] = {"retrieval.top_k": 3}
    assert client.delete(f"/v1/profiles/{item['profile_id']}", headers=ORIGIN).status_code == 200
    save = _save(client, pipeline_id, document)
    layout = client.put(
        f"/v1/pipelines/{pipeline_id}/layout", json={"layout": {"title": "x"}}, headers=ORIGIN
    )
    assert save.status_code == 409 and "deleted" in save.json()["message"]
    assert layout.status_code == 409 and "deleted" in layout.json()["message"]
    assert _revision_count(client, pipeline_id) == 1
    assert client.get(f"/v1/pipelines/{pipeline_id}").status_code == 200  # still readable


def test_a_layout_save_on_a_live_slot_is_accepted(client: TestClient) -> None:
    item = _profile(client)
    response = client.put(
        f"/v1/pipelines/{item['slots']['search']}/layout",
        json={"layout": {"title": "My search"}},
        headers=ORIGIN,
    )
    assert response.status_code == 200, response.text


# ── createPipeline is withdrawn (D20) ─────────────────────────────────


def test_create_pipeline_answers_410_and_creates_nothing(client: TestClient) -> None:
    before = client.get("/v1/pipelines").json()["pipelines"]
    response = client.post("/v1/pipelines", json={"title": "Old client"}, headers=ORIGIN)
    assert response.status_code == 410, response.text
    body = response.json()
    assert body["status"] == "error" and "POST /v1/profiles" in body["message"]
    assert client.get("/v1/pipelines").json()["pipelines"] == before


def test_create_pipeline_still_needs_a_credential(client: TestClient) -> None:
    client.cookies.clear()
    assert client.post("/v1/pipelines", json={"title": "x"}).status_code in (401, 403)
    reader = bearer(client.policy, "read")  # type: ignore[attr-defined]
    assert client.post("/v1/pipelines", json={"title": "x"}, headers=reader).status_code == 403


# ── getPipeline shows the owning profile ──────────────────────────────


def test_a_slot_pipeline_shows_its_profile_and_slot(client: TestClient) -> None:
    item = _profile(client)
    for slot in ("ingest", "search", "answer"):
        body = client.get(f"/v1/pipelines/{item['slots'][slot]}").json()
        assert body["profile_slot"] == {"profile_id": item["profile_id"], "slot": slot}


def test_a_loose_pipeline_has_no_profile_slot(client: TestClient) -> None:
    body = client.get(f"/v1/pipelines/{_standalone(client)}").json()
    assert "profile_slot" in body and body["profile_slot"] is None


def test_a_slot_of_a_deleted_profile_still_names_it(client: TestClient) -> None:
    item = _profile(client)
    client.delete(f"/v1/profiles/{item['profile_id']}", headers=ORIGIN)
    body = client.get(f"/v1/pipelines/{item['slots']['answer']}").json()
    assert body["profile_slot"] == {"profile_id": item["profile_id"], "slot": "answer"}


def test_the_pipeline_list_keeps_slot_pipelines_and_hides_job_pipelines(
    client: TestClient,
) -> None:
    item = _profile(client)
    job = _standalone(client, "Workspace job: ingest", layout={TASK_LAYOUT_KEY: "ingest"})
    listed = {p["pipeline_id"] for p in client.get("/v1/pipelines").json()["pipelines"]}
    assert set(item["slots"].values()) <= listed and job not in listed
