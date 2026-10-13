"""Session workspace path and stored collection profiles (task 6.9 API gaps).

``GET /v1/session`` names the workspace directory the server uses, so the
Settings view and notebook clients show the real location. Each
``GET /v1/collections`` item carries the stored profile name from the
collection metadata, or ``null`` when no profile tag is stored. Both
responses must still match ``openapi.yaml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    assert_conforms,
    bearer,
    build_app,
    lance_store,
    login,
    make_engine,
    seed,
)


def test_session_reports_the_workspace_path(tmp_path: Path, effective_settings: Any) -> None:
    """Session and bearer callers both see the canonical workspace path."""
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app(tmp_path, engine)
    expected = str((tmp_path / "ws").resolve())
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        session = client.get("/v1/session")
        client.cookies.clear()
        notebook = client.get("/v1/session", headers=bearer(policy, "read"))
    for response in (session, notebook):
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["workspace"] == expected
        assert_conforms("/session", "get", 200, body)


def test_collections_carry_the_stored_profile_or_null(
    tmp_path: Path, effective_settings: Any
) -> None:
    """A stored profile tag is reported; a collection without one gives null."""
    store = lance_store(tmp_path)
    seed(store, "code", str(tmp_path / "a.py"), 2, profile="codebase")
    seed(store, "notes", str(tmp_path / "b.md"), 1)
    app, policy = build_app(tmp_path, make_engine(store, effective_settings()))
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.get("/v1/collections")
    assert response.status_code == 200, response.text
    rows = {row["name"]: row for row in response.json()}
    assert rows["code"]["profile"] == "codebase"
    assert rows["notes"]["profile"] is None
    assert rows["code"]["chunk_count"] == 2
    assert_conforms("/collections", "get", 200, response.json())


def test_unreadable_collection_metadata_gives_null_profile(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A metadata read failure leaves the listing intact with a null profile."""
    store = lance_store(tmp_path)
    seed(store, "notes", str(tmp_path / "b.md"), 1, profile="documents")

    def broken(_name: str) -> dict:
        raise OSError("metadata unreadable")

    monkeypatch.setattr(store, "get_collection_metadata", broken)
    app, policy = build_app(tmp_path, make_engine(store, effective_settings()))
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.get("/v1/collections")
    assert response.status_code == 200, response.text
    assert response.json()[0]["profile"] is None
