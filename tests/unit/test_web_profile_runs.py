"""Chat and Knowledge Base requests on a user profile run the graph but add no run record.

unify-profiles-and-pipelines, task 7.9 (design D2, D14, D16). The route calls the
Engine, and the Engine runs the profile graph inside the request. The route does not
submit the graph through ``RunService``, so ``GET /v1/runs`` stays empty. A control
at the end of each test submits a real run to show that the listing would show one.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.fixtures.pipeline_parity.answer.harness import (  # noqa: E402
    CASE_NAMES,
    QUERY,
    case_by_name,
    case_settings,
)
from tests.fixtures.pipeline_parity.retrieval import harness  # noqa: E402
from tests.unit.test_engine_profiles_answer import _build  # noqa: E402
from tests.unit.test_engine_profiles_support import (  # noqa: E402
    COLLECTION,
    PROFILE,
    count_graph_runs,
    make_env,
    tagged_engine,
)
from tests.unit.test_web_runs_support import (  # noqa: E402
    BASE,
    ORIGIN,
    build_app,
    login,
    submit,
    wait_run,
)

from omrs.core.retrieval import registry  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL__HYBRID_ENABLED", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__TOP_K"):
        monkeypatch.delenv(name, raising=False)


def _client(tmp_path: Path, engine: Any) -> Iterator[TestClient]:
    # The in-memory FakeStore does not list collections; the profile routes read the list.
    engine.store.list_collections = lambda: [COLLECTION]
    # ``make_env`` keeps the workspace at ``tmp_path/ws``, the folder that ``build_app`` uses.
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        yield client


def _runs(client: TestClient) -> list[dict[str, Any]]:
    response = client.get("/v1/runs")
    assert response.status_code == 200, response.text
    return response.json()["runs"]


def _control_run(client: TestClient, slot: str) -> None:
    """Submit one run of the profile pipeline; the listing must then show it."""
    pipeline_id = client.get(f"/v1/profiles/{PROFILE}").json()["profile"]["slots"][slot]
    revision = client.get(f"/v1/pipelines/{pipeline_id}").json()["current_revision"]
    response = submit(client, revision["revision_id"], query=QUERY)
    assert response.status_code == 202, response.text
    wait_run(client, response.json()["run"]["run_id"])
    assert len(_runs(client)) == 1, "the run listing does not show a submitted run"


def test_a_knowledge_base_search_runs_the_graph_and_adds_no_run(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunks = harness.load_corpus()["chunks"]
    monkeypatch.setitem(registry._cache, "dense", harness.make_dense(chunks))
    env = make_env(tmp_path, effective_settings)
    engine = tagged_engine(env, effective_settings(), chunks, PROFILE)
    graph_runs = count_graph_runs(engine)
    for client in _client(tmp_path, engine):
        assert _runs(client) == []
        response = client.post(
            f"/v1/collections/{COLLECTION}/search",
            json={"query": harness.load_corpus()["query"], "top_k": 2, "rerank": False},
            headers=ORIGIN,
        )
        assert response.status_code == 200, response.text
        assert len(response.json()) == 2
        assert graph_runs == ["run_pipeline"], "the profile graph did not run"
        assert _runs(client) == [], "a search must not leave a run record"
        _control_run(client, "search")


@pytest.mark.parametrize("name", CASE_NAMES[:1])
def test_a_chat_answer_runs_the_graph_and_adds_no_run(
    name: str, tmp_path: Path, effective_settings: Any
) -> None:
    case = case_by_name(name)
    env = make_env(tmp_path, effective_settings)
    engine, _, _ = _build(env, case, case_settings(effective_settings(), case), PROFILE)
    graph_runs = count_graph_runs(engine)
    for client in _client(tmp_path, engine):
        assert _runs(client) == []
        response = client.post(
            f"/v1/collections/{COLLECTION}/answer", json={"query": QUERY}, headers=ORIGIN
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] != "error", response.text
        assert graph_runs == ["run_pipeline"], "the profile graph did not run"
        assert _runs(client) == [], "an answer must not leave a run record"
        _control_run(client, "answer")
