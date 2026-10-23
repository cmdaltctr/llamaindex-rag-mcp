"""Profile routes: list, create, read, rename, delete (unify-profiles-and-pipelines, task 7.1).

A real Engine with a profile resolver and a LanceDB store gives real standard
graphs. The records live in a real SQLite workspace on ``tmp_path``.
"""

from __future__ import annotations

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
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402
from tests.unit.test_web_runs_support import build_app  # noqa: E402

from omrs.core.profiles.resolver import ProfileResolver  # noqa: E402

COLLECTION = "notes"
SLOTS = ("ingest", "search", "answer")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL__HYBRID_ENABLED", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__TOP_K"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def setup(tmp_path: Path, effective_settings: Any) -> dict[str, Any]:
    store = lance_store(tmp_path)
    seed(store, COLLECTION, "/data/a.md", 2)
    settings = effective_settings()
    resolver = ProfileResolver(store=store, server_profile="documents", base=settings)
    engine = make_engine(store, settings, profile_resolver=resolver)
    app, policy = build_app(tmp_path, engine)
    return {"store": store, "engine": engine, "app": app, "policy": policy}


@pytest.fixture
def client(setup: dict[str, Any]) -> Iterator[TestClient]:
    with TestClient(setup["app"], base_url=BASE) as test_client:
        login(test_client, setup["policy"])
        test_client.policy = setup["policy"]  # type: ignore[attr-defined]
        test_client.store = setup["store"]  # type: ignore[attr-defined]
        yield test_client


def _create(client: TestClient, title: str = "My notes", **body: Any) -> Any:
    return client.post("/v1/profiles", json={"title": title, **body}, headers=ORIGIN)


def _ids(client: TestClient) -> list[str]:
    return [p["profile_id"] for p in client.get("/v1/profiles").json()["profiles"]]


# ── List ─────────────────────────────────────────────────────────────────


def test_a_fresh_workspace_lists_the_built_in_profiles(client: TestClient) -> None:
    response = client.get("/v1/profiles")
    assert response.status_code == 200, response.text
    profiles = response.json()["profiles"]
    assert [p["profile_id"] for p in profiles] == ["documents", "codebase"]
    for item in profiles:
        assert item["kind"] == "builtin" and item["ready"] is True
        assert item["not_ready_reasons"] == [] and item["used_by"] == []
        assert item["slots"] == {"ingest": None, "search": None, "answer": None}
        assert item["base_profile"] == item["profile_id"]
        assert "standard_graphs" not in item


def test_a_user_profile_in_use_shows_its_slots_and_collections(client: TestClient) -> None:
    created = _create(client, source="documents").json()["profile"]
    client.store.update_collection_metadata(COLLECTION, {"profile": created["profile_id"]})
    item = next(p for p in client.get("/v1/profiles").json()["profiles"] if p["kind"] == "user")
    assert set(item["slots"]) == set(SLOTS) and all(item["slots"].values())
    assert item["used_by"] == [COLLECTION]
    assert item["ready"] is True


# ── Create ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("source", ["documents", "codebase"])
def test_create_from_a_built_in_profile(client: TestClient, source: str) -> None:
    response = _create(client, source=source, description="Mine")
    assert response.status_code == 201, response.text
    item = response.json()["profile"]
    assert (item["kind"], item["base_profile"], item["description"]) == ("user", source, "Mine")
    assert item["ready"] is True and item["profile_id"] == "my-notes"
    assert "standard_graphs" not in item
    revision = client.get(f"/v1/pipelines/{item['slots']['search']}").json()["current_revision"]
    assert revision["revision_number"] == 1
    assert revision["document"]["profile"] == source


def test_create_from_a_user_profile_copies_its_graphs(client: TestClient) -> None:
    first = _create(client, source="codebase").json()["profile"]
    copy = _create(client, "Copy", source=first["profile_id"])
    assert copy.status_code == 201, copy.text
    item = copy.json()["profile"]
    assert item["base_profile"] == "codebase" and item["profile_id"] == "copy"
    assert set(item["slots"].values()).isdisjoint(first["slots"].values())


def test_create_empty_is_not_ready(client: TestClient) -> None:
    response = _create(client, "Blank", source=None)
    assert response.status_code == 201
    item = response.json()["profile"]
    assert item["ready"] is False and item["base_profile"] == "documents"
    assert len(item["not_ready_reasons"]) == 3
    assert all("no saved graph" in reason for reason in item["not_ready_reasons"])


def test_create_without_a_source_field_is_empty(client: TestClient) -> None:
    response = client.post("/v1/profiles", json={"title": "Blank"}, headers=ORIGIN)
    assert response.status_code == 201 and response.json()["profile"]["ready"] is False


def test_a_second_profile_with_the_same_title_gets_a_new_id(client: TestClient) -> None:
    assert _create(client, "Documents", source="documents").json()["profile"]["profile_id"] == (
        "documents-2"
    )
    _create(client, "Notes")
    assert _create(client, "Notes").json()["profile"]["profile_id"] == "notes-2"


@pytest.mark.parametrize("title", ["", "   ", "x" * 81, "bad\x07"])
def test_create_with_an_invalid_title_is_refused(client: TestClient, title: str) -> None:
    response = _create(client, title, source="documents")
    assert response.status_code == 400, response.text
    assert response.json()["status"] == "error"
    assert _ids(client) == ["documents", "codebase"]


def test_create_from_an_unknown_source_is_404(client: TestClient) -> None:
    assert _create(client, source="nope").status_code == 404


# ── Read ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["documents", "codebase"])
def test_reading_a_built_in_returns_its_standard_graphs(client: TestClient, name: str) -> None:
    response = client.get(f"/v1/profiles/{name}")
    assert response.status_code == 200, response.text
    item = response.json()["profile"]
    assert tuple(item["standard_graphs"]) == SLOTS
    for graph in item["standard_graphs"].values():
        assert graph["profile"] == name and graph["collection"] is None


def test_codebase_graphs_follow_codebase_settings(client: TestClient) -> None:
    graphs = client.get("/v1/profiles/codebase").json()["profile"]["standard_graphs"]
    nodes = {node["id"] for node in graphs["search"]["nodes"]}
    assert {"sparse", "fuse"} <= nodes


def test_the_standard_graphs_equal_revision_one_of_a_duplicate(client: TestClient) -> None:
    standard = client.get("/v1/profiles/documents").json()["profile"]["standard_graphs"]
    item = _create(client, source="documents").json()["profile"]
    for slot in SLOTS:
        revision = client.get(f"/v1/pipelines/{item['slots'][slot]}").json()["current_revision"]
        assert revision["document"] == standard[slot]


def test_reading_a_user_profile_has_null_standard_graphs(client: TestClient) -> None:
    item = _create(client, source="documents").json()["profile"]
    read = client.get(f"/v1/profiles/{item['profile_id']}").json()["profile"]
    assert read["standard_graphs"] is None and read["profile_id"] == item["profile_id"]


def test_reading_an_unknown_profile_is_404(client: TestClient) -> None:
    assert client.get("/v1/profiles/nope").status_code == 404


# ── Rename ───────────────────────────────────────────────────────────────


def test_rename_changes_title_and_description_and_keeps_the_id(client: TestClient) -> None:
    item = _create(client, source="documents").json()["profile"]
    response = client.patch(
        f"/v1/profiles/{item['profile_id']}",
        json={"title": "Meeting notes", "description": "Weekly"},
        headers=ORIGIN,
    )
    assert response.status_code == 200, response.text
    renamed = response.json()["profile"]
    assert (renamed["profile_id"], renamed["title"], renamed["description"]) == (
        item["profile_id"],
        "Meeting notes",
        "Weekly",
    )
    assert renamed["slots"] == item["slots"]


def test_rename_a_built_in_is_403_and_changes_nothing(client: TestClient) -> None:
    response = client.patch("/v1/profiles/documents", json={"title": "Mine"}, headers=ORIGIN)
    assert response.status_code == 403
    assert client.get("/v1/profiles/documents").json()["profile"]["title"] == "Documents"


def test_rename_an_unknown_profile_is_404(client: TestClient) -> None:
    response = client.patch("/v1/profiles/nope", json={"title": "X"}, headers=ORIGIN)
    assert response.status_code == 404


@pytest.mark.parametrize("title", ["", "  ", "x" * 81, "a\nb"])
def test_rename_with_an_invalid_title_is_400(client: TestClient, title: str) -> None:
    item = _create(client, source="documents").json()["profile"]
    response = client.patch(
        f"/v1/profiles/{item['profile_id']}", json={"title": title}, headers=ORIGIN
    )
    assert response.status_code == 400, response.text


def test_rename_with_no_field_is_400(client: TestClient) -> None:
    item = _create(client, source="documents").json()["profile"]
    response = client.patch(f"/v1/profiles/{item['profile_id']}", json={}, headers=ORIGIN)
    assert response.status_code == 400


# ── Delete ───────────────────────────────────────────────────────────────


def test_delete_an_unused_profile(client: TestClient) -> None:
    item = _create(client, source="documents").json()["profile"]
    response = client.delete(f"/v1/profiles/{item['profile_id']}", headers=ORIGIN)
    assert response.status_code == 200, response.text
    assert response.json()["profile"]["profile_id"] == item["profile_id"]
    assert item["profile_id"] not in _ids(client)
    assert client.get(f"/v1/profiles/{item['profile_id']}").status_code == 404
    # The pipelines and revisions stay in the workspace.
    assert client.get(f"/v1/pipelines/{item['slots']['search']}").status_code == 200


def test_a_deleted_profile_cannot_be_renamed_or_deleted_again(client: TestClient) -> None:
    item = _create(client, source="documents").json()["profile"]
    client.delete(f"/v1/profiles/{item['profile_id']}", headers=ORIGIN)
    path = f"/v1/profiles/{item['profile_id']}"
    assert client.patch(path, json={"title": "X"}, headers=ORIGIN).status_code == 404
    assert client.delete(path, headers=ORIGIN).status_code == 404


def test_delete_is_refused_while_a_collection_uses_the_profile(client: TestClient) -> None:
    item = _create(client, source="documents").json()["profile"]
    client.store.update_collection_metadata(COLLECTION, {"profile": item["profile_id"]})
    response = client.delete(f"/v1/profiles/{item['profile_id']}", headers=ORIGIN)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["status"] == "error" and body["used_by"] == [COLLECTION]
    assert item["profile_id"] in _ids(client)


def test_delete_a_built_in_is_403(client: TestClient) -> None:
    assert client.delete("/v1/profiles/codebase", headers=ORIGIN).status_code == 403
    assert "codebase" in _ids(client)


def test_delete_an_unknown_profile_is_404(client: TestClient) -> None:
    assert client.delete("/v1/profiles/nope", headers=ORIGIN).status_code == 404


# ── Access ───────────────────────────────────────────────────────────────


def test_reads_need_read_scope_and_writes_need_graph_scope(client: TestClient) -> None:
    policy = client.policy  # type: ignore[attr-defined]
    client.cookies.clear()
    assert client.get("/v1/profiles").status_code == 401
    assert client.post("/v1/profiles", json={"title": "X"}).status_code in (401, 403)
    reader = bearer(policy, "read")
    assert client.get("/v1/profiles", headers=reader).status_code == 200
    assert client.get("/v1/profiles/documents", headers=reader).status_code == 200
    assert client.post("/v1/profiles", json={"title": "X"}, headers=reader).status_code == 403
    assert client.patch("/v1/profiles/x", json={"title": "X"}, headers=reader).status_code == 403
    assert client.delete("/v1/profiles/x", headers=reader).status_code == 403
    writer = bearer(policy, "graph")
    assert client.post("/v1/profiles", json={"title": "X"}, headers=writer).status_code == 201


# ── OpenAPI conformance ──────────────────────────────────────────────────


def test_profile_responses_conform_to_the_contract(client: TestClient) -> None:
    check = ContractChecker()
    listed = check.check(client.get("/v1/profiles"), 200)
    assert [p["profile_id"] for p in listed["profiles"]] == ["documents", "codebase"]
    detail = check.check(client.get("/v1/profiles/codebase"), 200)
    assert detail["profile"]["standard_graphs"]
    created = check.check(_create(client, source="documents"), 201)["profile"]
    check.check(_create(client, "Blank", source=None), 201)
    check.check(_create(client, "", source="documents"), 400)
    check.check(_create(client, "X", source="nope"), 404)
    pid = created["profile_id"]
    check.check(client.get(f"/v1/profiles/{pid}"), 200)
    check.check(client.get("/v1/profiles/nope"), 404)
    path = f"/v1/profiles/{pid}"
    check.check(client.patch(path, json={"title": "Renamed"}, headers=ORIGIN), 200)
    check.check(client.patch("/v1/profiles/documents", json={"title": "x"}, headers=ORIGIN), 403)
    client.store.update_collection_metadata(COLLECTION, {"profile": pid})  # type: ignore[attr-defined]
    check.check(client.delete(path, headers=ORIGIN), 409)
    client.store.update_collection_metadata(COLLECTION, {"profile": "documents"})  # type: ignore[attr-defined]
    check.check(client.delete(path, headers=ORIGIN), 200)
    check.check(client.delete("/v1/profiles/codebase", headers=ORIGIN), 403)
    check.check(client.post("/v1/pipelines", json={"title": "x"}, headers=ORIGIN), 410)
    assert check.operations >= FAMILIES["profiles"] | {"createPipeline"}
