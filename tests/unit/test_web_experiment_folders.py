"""Experiment folders over HTTP: ``POST /v1/experiment-folders`` and the listing tree.

The route is session-only (``manage``). A refused path creates no
directory, inside or outside the approved root. The experiments listing
carries the directory tree of every approved root, so a folder without a
context still shows. No model, LLM or network call happens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_experiments_support import (  # noqa: E402
    BASE,
    ORIGIN,
    build_experiment_app,
    login,
)
from tests.unit.test_web_runs_support import make_engine  # noqa: E402


@pytest.fixture
def setup(tmp_path: Path, effective_settings: Any):
    parts = build_experiment_app(tmp_path, make_engine(effective_settings), effective_settings)
    with TestClient(parts.app, base_url=BASE) as client:
        login(client, parts.policy)
        yield client, parts


def _create(client: TestClient, path: str, **body: Any) -> Any:
    return client.post("/v1/experiment-folders", json={"path": path, **body}, headers=ORIGIN)


def _tree(client: TestClient) -> list[dict[str, Any]]:
    listed = client.get("/v1/experiments").json()
    assert len(listed["folders"]) == 1
    return listed["folders"][0]["tree"]


def test_create_a_main_folder_and_see_it_in_the_listing(setup: Any) -> None:
    client, parts = setup
    response = _create(client, "hybrid-search")
    assert response.status_code == 201, response.text
    folder = response.json()["folder"]
    root = parts.root.resolve()
    assert folder == {
        "root": str(root),
        "path": "hybrid-search",
        "name": "hybrid-search",
        "workspace": str(root / "hybrid-search"),
    }
    assert (root / "hybrid-search").is_dir()
    node = _tree(client)[0]
    assert node["name"] == "hybrid-search"
    assert node["context_id"] is None and node["children"] == []


def test_listing_groups_sub_experiments_under_their_folder(setup: Any) -> None:
    client, parts = setup
    folder = _create(client, "hybrid-search/run-1").json()["folder"]
    registered = client.post(
        "/v1/experiments",
        json={"workspace": folder["workspace"], "name": "run-1", "declared_factors": ["k"]},
        headers=ORIGIN,
    )
    assert registered.status_code == 201, registered.text
    context_id = registered.json()["experiment"]["context_id"]
    _create(client, "hybrid-search/run-2")
    _create(client, "input-quality")
    names = [node["name"] for node in _tree(client)]
    assert names == ["hybrid-search", "input-quality"]
    children = _tree(client)[0]["children"]
    assert [(c["name"], c["context_id"]) for c in children] == [
        ("run-1", context_id),
        ("run-2", None),
    ]
    assert _tree(client)[1]["children"] == []


def test_an_existing_directory_on_disk_shows_without_a_context(setup: Any) -> None:
    client, parts = setup
    (parts.root / "made-by-hand").mkdir()
    assert [node["name"] for node in _tree(client)] == ["made-by-hand"]


@pytest.mark.parametrize(
    "path", ["..", "../escape", "a/../../escape", "a/../b", "/tmp/escape", "a\\..\\b"]
)
def test_traversal_and_absolute_paths_fail_with_no_directory_created(
    setup: Any, tmp_path: Path, path: str
) -> None:
    client, parts = setup
    response = _create(client, path)
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["status"] == "error" and body["code"] in {
        "traversal",
        "not_relative",
        "invalid_name",
    }
    assert list(parts.root.iterdir()) == []
    assert not (tmp_path / "escape").exists()
    assert not Path("/tmp/escape").exists()


def test_traversal_code_is_stable(setup: Any) -> None:
    client, _ = setup
    assert _create(client, "a/../b").json()["code"] == "traversal"
    assert _create(client, "/abs").json()["code"] == "not_relative"
    assert _create(client, "a/b/c/d/e").json()["code"] == "too_deep"
    assert _create(client, "bad name!").json()["code"] == "invalid_name"


def test_a_linked_directory_is_not_followed(setup: Any, tmp_path: Path) -> None:
    client, parts = setup
    outside = tmp_path / "outside"
    outside.mkdir()
    (parts.root / "link").symlink_to(outside, target_is_directory=True)
    response = _create(client, "link/inside")
    assert response.status_code == 400 and response.json()["code"] == "symlink_escape"
    assert list(outside.iterdir()) == []


def test_existing_folder_gives_409(setup: Any) -> None:
    client, _ = setup
    assert _create(client, "once").status_code == 201
    again = _create(client, "once")
    assert again.status_code == 409 and again.json()["code"] == "exists"


def test_root_must_be_an_approved_root(setup: Any, tmp_path: Path) -> None:
    client, parts = setup
    wrong = _create(client, "x", root=str(tmp_path))
    assert wrong.status_code == 400 and wrong.json()["code"] == "root_unknown"
    right = _create(client, "x", root=str(parts.root.resolve()))
    assert right.status_code == 201


def test_unknown_body_fields_and_missing_path_fail_validation(setup: Any) -> None:
    client, parts = setup
    extra = client.post(
        "/v1/experiment-folders", json={"path": "x", "mode": "0777"}, headers=ORIGIN
    )
    assert extra.status_code == 400 and extra.json()["error_type"] == "validation"
    missing = client.post("/v1/experiment-folders", json={}, headers=ORIGIN)
    assert missing.status_code == 400
    assert list(parts.root.iterdir()) == []


def test_folder_creation_is_session_only(setup: Any) -> None:
    client, parts = setup
    token = parts.policy.issue_bearer({"graph", "read", "run"}).token
    header = {"Authorization": f"Bearer {token}"}
    response = client.post("/v1/experiment-folders", json={"path": "x"}, headers=header)
    assert response.status_code == 403
    assert list(parts.root.iterdir()) == []
    client.cookies.clear()
    assert (
        client.post("/v1/experiment-folders", json={"path": "x"}, headers=ORIGIN).status_code == 401
    )


def test_cookie_post_needs_the_application_origin(setup: Any) -> None:
    client, parts = setup
    response = client.post(
        "/v1/experiment-folders", json={"path": "x"}, headers={"Origin": "http://evil.example"}
    )
    assert response.status_code == 403
    assert list(parts.root.iterdir()) == []


def test_no_experiment_root_gives_guidance(tmp_path: Path, effective_settings: Any) -> None:
    parts = build_experiment_app(
        tmp_path,
        make_engine(effective_settings),
        effective_settings,
        experiment_roots=(),
        experiments_factory=None,
    )
    with TestClient(parts.app, base_url=BASE) as client:
        login(client, parts.policy)
        refused = _create(client, "x")
        assert refused.status_code == 409
        assert "--experiment-root" in refused.json()["message"]
        listed = client.get("/v1/experiments").json()
        assert listed["roots"] == [] and listed["folders"] == []
