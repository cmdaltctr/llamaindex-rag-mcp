"""Tests for the collection display name (add-collection-display-name).

Spec: local-web-workspace, 'Collections have an editable display name'.
Stores are real LanceDB tables under ``tmp_path``; the embedder is a mock.
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
    assert_conforms,
    bearer,
    build_app,
    lance_store,
    login,
    make_engine,
    seed,
)

COLLECTION = "notes"
URL = f"/v1/collections/{COLLECTION}/display-name"


@pytest.fixture
def setup(tmp_path: Path, effective_settings: Any) -> dict[str, Any]:
    store = lance_store(tmp_path)
    seed(store, COLLECTION, str(tmp_path / "a.md"), 2)
    app, policy = build_app(tmp_path, make_engine(store, effective_settings()))
    return {"store": store, "app": app, "policy": policy}


def _patch(client: TestClient, value: Any, url: str = URL) -> Any:
    return client.patch(url, json={"display_name": value}, headers=ORIGIN)


def _listed(client: TestClient) -> dict[str, Any]:
    return {row["name"]: row for row in client.get("/v1/collections").json()}


def test_setting_trims_returns_the_pair_and_lists_it(setup: dict[str, Any]) -> None:
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        response = _patch(client, "  Project docs ")
        listed = _listed(client)
    assert response.status_code == 200, response.text
    assert response.json() == {"collection": COLLECTION, "display_name": "Project docs"}
    assert_conforms("/collections/{collection}/display-name", "patch", 200, response.json())
    assert listed[COLLECTION]["display_name"] == "Project docs"
    assert listed[COLLECTION]["name"] == COLLECTION


@pytest.mark.parametrize("empty", ["", "   ", "\t "])
def test_an_empty_value_clears_the_display_name(setup: dict[str, Any], empty: str) -> None:
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        assert _patch(client, "Project docs").status_code == 200
        cleared = _patch(client, empty)
        listed = _listed(client)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json() == {"collection": COLLECTION, "display_name": None}
    assert listed[COLLECTION]["display_name"] is None


def test_a_collection_without_a_display_name_lists_null(setup: dict[str, Any]) -> None:
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        listed = _listed(client)
    assert listed[COLLECTION]["display_name"] is None
    assert_conforms("/collections", "get", 200, list(listed.values()))


def test_eighty_code_points_pass_and_eighty_one_are_rejected(setup: dict[str, Any]) -> None:
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        assert _patch(client, "a" * 80).status_code == 200
        too_long = _patch(client, "b" * 81)
        listed = _listed(client)
    assert too_long.status_code == 400
    assert too_long.json()["status"] == "error"
    assert_conforms("/collections/{collection}/display-name", "patch", 400, too_long.json())
    assert listed[COLLECTION]["display_name"] == "a" * 80


def test_the_limit_counts_code_points_not_utf16_units(setup: dict[str, Any]) -> None:
    emoji = "\U0001f600"  # one code point, two UTF-16 units
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        fits = _patch(client, emoji * 80)
        over = _patch(client, emoji * 81)
    assert fits.status_code == 200, fits.text
    assert over.status_code == 400


@pytest.mark.parametrize("bad", ["two\nlines", "tab\there", "nul\x00byte", "del\x7fchar"])
def test_a_control_character_is_rejected_and_nothing_changes(
    setup: dict[str, Any], bad: str
) -> None:
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        assert _patch(client, "Kept").status_code == 200
        rejected = _patch(client, bad)
        listed = _listed(client)
    assert rejected.status_code == 400
    assert listed[COLLECTION]["display_name"] == "Kept"


def test_a_bearer_credential_is_refused_before_any_write(setup: dict[str, Any]) -> None:
    notebook = bearer(setup["policy"], "read", "run", "graph")
    with TestClient(setup["app"], base_url=BASE) as client:
        refused = client.patch(URL, json={"display_name": "Nope"}, headers=notebook)
        login(client, setup["policy"])
        listed = _listed(client)
    assert refused.status_code == 403
    assert listed[COLLECTION]["display_name"] is None


def test_an_unknown_collection_returns_404_and_creates_nothing(setup: dict[str, Any]) -> None:
    store = setup["store"]
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        response = _patch(client, "Ghost", "/v1/collections/ghost/display-name")
        listed = _listed(client)
    assert response.status_code == 404
    assert_conforms("/collections/{collection}/display-name", "patch", 404, response.json())
    assert "ghost" not in listed
    assert not store.collection_exists("ghost")


def test_a_session_without_origin_is_refused(setup: dict[str, Any]) -> None:
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        response = client.patch(URL, json={"display_name": "x"})
    assert response.status_code == 403


def test_the_collection_name_and_profile_are_unaffected(setup: dict[str, Any]) -> None:
    store = setup["store"]
    store.update_collection_metadata(COLLECTION, {"profile": "codebase"})
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        assert _patch(client, "Project docs").status_code == 200
        listed = _listed(client)
    assert listed[COLLECTION]["profile"] == "codebase"
    assert listed[COLLECTION]["chunk_count"] == 2
    assert store.collection_exists(COLLECTION)


def test_unreadable_metadata_gives_null_display_name_and_profile(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = lance_store(tmp_path)
    seed(store, COLLECTION, str(tmp_path / "a.md"), 1, profile="documents")

    def broken(_name: str) -> dict:
        raise OSError("metadata unreadable")

    monkeypatch.setattr(store, "get_collection_metadata", broken)
    app, policy = build_app(tmp_path, make_engine(store, effective_settings()))
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.get("/v1/collections")
    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row["display_name"] is None
    assert row["profile"] is None
