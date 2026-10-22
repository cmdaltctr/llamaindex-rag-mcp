"""A web start builds the Engine with the workspace catalogue and upgrades saved pipelines.

unify-profiles-and-pipelines, task 7.7 (design D10). The test calls ``create_app``
without an ``engine_factory`` so the real default factory runs. Only
``compose.build_engine`` is replaced, to capture the ``catalogue`` argument and
to return a test Engine.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    lance_store,
    login,
    make_engine,
    seed,
)

from omrs import compose  # noqa: E402
from omrs.compose_templates import profile_templates  # noqa: E402
from omrs.core.profiles.resolver import ProfileResolver  # noqa: E402
from omrs.integrations.workspace_sqlite import SqliteWorkspaceRepository  # noqa: E402
from omrs.transports.api.app import create_app  # noqa: E402
from omrs.transports.api.lifespan import WebConfig  # noqa: E402
from omrs.transports.api.security import AccessPolicy  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL__HYBRID_ENABLED", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__TOP_K"):
        monkeypatch.delenv(name, raising=False)


class Launcher:
    """Starts the real default app for one workspace and records each Engine build."""

    def __init__(self, tmp_path: Path, effective_settings: Any) -> None:
        self.workspace = tmp_path / "ws"
        self.records = self.workspace / "workspace.db"
        self.catalogues: list[Any] = []
        self.tmp_path = tmp_path
        self.settings = effective_settings()
        self.engine = self._new_engine()

    def _new_engine(self) -> Any:
        """Return a test Engine; a shut-down closes it, so each start needs its own."""
        store = lance_store(self.tmp_path)
        seed(store, "notes", "/data/a.md", 2)
        resolver = ProfileResolver(store=store, server_profile="documents", base=self.settings)
        return make_engine(store, self.settings, profile_resolver=resolver)

    def build_engine(self, *args: Any, **kwargs: Any) -> Any:
        """Stand-in for ``compose.build_engine``: capture the catalogue, return a test Engine."""
        assert not args, "the default factory must pass the catalogue by keyword"
        self.catalogues.append(kwargs.get("catalogue"))
        return self.engine if len(self.catalogues) == 1 else self._new_engine()

    def save_search_pipeline(self, title: str = "Docs search") -> str:
        """Write a loose pipeline with a Search graph into the workspace database."""
        graph = copy.deepcopy(profile_templates(self.engine, "documents")["search"])
        graph["profile"] = "documents"
        repository = SqliteWorkspaceRepository(self.records)
        pipeline_id = repository.create_pipeline(title, layout={})["pipeline_id"]
        repository.save_revision(pipeline_id, graph, schema_version=1)
        return pipeline_id

    def start(self) -> TestClient:
        """Return a started client of a new app (default factory, no ``engine_factory``)."""
        config = WebConfig(workspace=self.workspace, port=8765, static_dir=None)
        policy = AccessPolicy.for_launch(config.host, config.port)
        client = TestClient(create_app(config, policy=policy), base_url=BASE)
        client.__enter__()
        login(client, policy)
        return client


@pytest.fixture
def launcher(tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch) -> Launcher:
    launcher = Launcher(tmp_path, effective_settings)
    monkeypatch.setattr(compose, "build_engine", launcher.build_engine)
    return launcher


def _profiles(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/v1/profiles")
    assert response.status_code == 200, response.text
    return [p for p in response.json()["profiles"] if p["kind"] == "user"]


def test_the_engine_is_built_with_the_catalogue_of_the_workspace(launcher: Launcher) -> None:
    client = launcher.start()
    try:
        assert len(launcher.catalogues) == 1
        catalogue = launcher.catalogues[0]
        assert catalogue is not None, "the Engine was built without a profile catalogue"
        assert Path(catalogue.path) == launcher.workspace / "workspace.db"
    finally:
        client.__exit__(None, None, None)


def test_a_start_turns_a_saved_pipeline_into_a_profile_and_a_second_start_adds_none(
    launcher: Launcher,
) -> None:
    pipeline_id = launcher.save_search_pipeline()
    first = launcher.start()
    try:
        profiles = _profiles(first)
        assert [p["title"] for p in profiles] == ["Docs search"]
        assert profiles[0]["slots"]["search"] == pipeline_id
    finally:
        first.__exit__(None, None, None)
    second = launcher.start()
    try:
        assert [p["profile_id"] for p in _profiles(second)] == [profiles[0]["profile_id"]]
    finally:
        second.__exit__(None, None, None)
    assert len(launcher.catalogues) == 2
