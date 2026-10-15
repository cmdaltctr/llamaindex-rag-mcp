"""Run artefact route ``GET /v1/runs/{run_id}/artefacts/{name}`` (design D1; task 1.1).

A cut summary is stored in full as a private, redacted artefact. The route
returns it with the same access policy as ``GET /v1/runs/{run_id}``: a
bearer credential bound to an experiment reads only that experiment's
runs. A bad name gets 400 before any file is read. A real Engine over
in-memory fakes, the real SQLite workspace repository and the real
``RunService``. No model calls.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_experiments_support import (  # noqa: E402
    BASE,
    bound_bearer,
    build_experiment_app,
    login,
    register,
    save_revision,
    submit,
    wait_run,
)
from tests.unit.test_web_runs_support import make_engine  # noqa: E402

from omrg.core.pipelines import NodeOutcome, NodeStatus  # noqa: E402
from omrg.core.workspace.artefacts import ArtefactStore  # noqa: E402

SECRET = "sk-live-abcdefghijklmnopqrstuvwx"  # noqa: S105 - fake value the test must not see


@pytest.fixture
def engine(effective_settings: Any) -> Any:
    return make_engine(effective_settings)


@pytest.fixture
def setup(tmp_path: Path, engine: Any, effective_settings: Any) -> Any:
    parts = build_experiment_app(tmp_path, engine, effective_settings)
    with TestClient(parts.app, base_url=BASE) as client:
        login(client, parts.policy)
        yield client, parts


def _cut_summary(client: TestClient, run: dict[str, Any], name: str = "event-big") -> Any:
    """Store a summary too large for a preview; return the cut summary."""
    service = client.app.state.runtime.run_service.service  # type: ignore[attr-defined]
    value = {
        "message": "x" * 40_000,
        "data": {"api_key": SECRET, "embedding": [0.5] * 128, "rows": list(range(300))},
    }
    return service.artefacts_for(run).safe_summary(run["run_id"], name, value)


def _live_run(client: TestClient, headers: dict[str, str] | None = None) -> dict[str, Any]:
    revision_id = save_revision(client)
    return wait_run(client, submit(client, revision_id).json()["run"]["run_id"], headers)


def _url(run_id: str, name: str) -> str:
    return f"/v1/runs/{run_id}/artefacts/{name}"


def test_a_cut_summary_is_returned_in_full(setup: Any) -> None:
    client, _ = setup
    run = _live_run(client)
    summary = _cut_summary(client, run)
    assert summary["truncated"] is True
    owner, _, file_name = summary["artefact_ref"].partition("/")
    assert owner == run["run_id"]
    name = file_name.removesuffix(".json")
    response = client.get(_url(run["run_id"], name))
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"status", "run_id", "name", "value"}
    assert body["status"] == "ok" and body["run_id"] == run["run_id"] and body["name"] == name
    assert body["value"]["message"] == "x" * 40_000
    assert body["value"]["data"]["rows"] == list(range(300))


def test_the_value_holds_no_credential_and_no_raw_vector(setup: Any) -> None:
    client, _ = setup
    run = _live_run(client)
    _cut_summary(client, run)
    response = client.get(_url(run["run_id"], "event-big"))
    assert response.status_code == 200
    assert SECRET not in response.text
    assert response.json()["value"]["data"]["embedding"] == {
        "omitted": "vector data",
        "length": 128,
    }


def test_an_unknown_name_is_404_with_a_generic_message(setup: Any, tmp_path: Path) -> None:
    client, _ = setup
    run = _live_run(client)
    response = client.get(_url(run["run_id"], "event-none"))
    assert response.status_code == 404
    assert response.json()["status"] == "error"
    assert response.json()["message"] == "This run has no such output."
    assert str(tmp_path) not in response.text


@pytest.mark.parametrize(
    "name", ["a/b", "..%2Fsecret", "%2E%2E", "%2E", "a%5Cb", "a..b", ".hidden", "x" * 200]
)
def test_an_unsafe_name_is_400_and_reads_no_file(setup: Any, tmp_path: Path, name: str) -> None:
    client, _ = setup
    run = _live_run(client)
    with patch.object(ArtefactStore, "read_json", side_effect=AssertionError("read")) as read:
        response = client.get(_url(run["run_id"], name))
    assert response.status_code == 400, (name, response.status_code, response.text)
    assert response.json()["message"] == "That output name is not valid."
    assert str(tmp_path) not in response.text
    read.assert_not_called()


def test_an_unknown_run_is_404(setup: Any) -> None:
    client, _ = setup
    response = client.get(_url("no-such-run", "event-big"))
    assert response.status_code == 404
    assert response.json()["message"] == "Unknown run."


def test_a_bound_credential_reads_its_own_runs_only(setup: Any) -> None:
    client, parts = setup
    first = register(client, parts.root, "exp-a")["experiment"]["context_id"]
    second = register(client, parts.root, "exp-b")["experiment"]["context_id"]
    revision_id = save_revision(client)
    live = wait_run(client, submit(client, revision_id).json()["run"]["run_id"])
    other = wait_run(client, submit(client, revision_id, context=second).json()["run"]["run_id"])
    header = bound_bearer(client, first)
    own = wait_run(
        client,
        submit(client, revision_id, context=first, headers=header).json()["run"]["run_id"],
        header,
    )
    for run in (live, other, own):
        _cut_summary(client, run)
    client.cookies.clear()
    allowed = client.get(_url(own["run_id"], "event-big"), headers=header)
    assert allowed.status_code == 200, allowed.text
    for hidden in (live, other):
        refused = client.get(_url(hidden["run_id"], "event-big"), headers=header)
        assert refused.status_code == 404
        assert refused.json()["message"] == "Unknown run."
        assert "x" * 100 not in refused.text


def test_a_cut_node_summary_of_a_run_opens_in_full(setup: Any, engine: Any) -> None:
    client, _ = setup
    original = engine.run_pipeline

    async def big_node(*args: Any, **kwargs: Any) -> Any:
        result = await original(*args, **kwargs)
        node = NodeOutcome(
            node_id="search", status=NodeStatus.SUCCEEDED, summary={"text": "z" * 40_000}
        )
        return result.model_copy(update={"nodes": (node,)})

    engine.run_pipeline = big_node
    run = _live_run(client)
    summary = client.get(f"/v1/runs/{run['run_id']}/result").json()["result"]["nodes"][0]
    summary = summary["summary"]
    assert summary["truncated"] is True
    name = summary["artefact_ref"].partition("/")[2].removesuffix(".json")
    response = client.get(_url(run["run_id"], name))
    assert response.status_code == 200, response.text
    assert response.json()["value"] == {"text": "z" * 40_000}
