"""An approved ingestion experiment keeps its index and outputs in its workspace.

A bearer credential bound to an experiment context that permits ingestion
runs the canonical ingestion graph over HTTP. The context store and the
run result both stay below ``<experiment workspace>/output/``. The result
still resolves through the protected result route, the live library is
not touched, and workspace cleanup removes the run record but never the
experiment outputs. Real LanceDB stores on ``tmp_path``, the conftest mock
embedder, no model or network call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.fixtures.pipeline_parity.ingestion.snapshot import (  # noqa: E402
    copy_sources,
    pin_detection,
)
from tests.unit.test_experiment_contexts_support import RecordingBuilder, under  # noqa: E402
from tests.unit.test_web_experiments_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bound_bearer,
    build_experiment_app,
    login,
    register,
    wait_run,
)
from tests.unit.test_web_runs_support import make_engine, new_pipeline  # noqa: E402

from omrs.core.ingestion.graph_adapters import canonical_ingestion_definition  # noqa: E402


@pytest.fixture
def setup(tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    pin_detection(monkeypatch)
    live = make_engine(effective_settings)
    parts = build_experiment_app(tmp_path, live, effective_settings)
    builder = RecordingBuilder()
    with TestClient(parts.app, base_url=BASE) as client:
        login(client, parts.policy)
        # Real context Engines over LanceDB below the context output directory.
        parts.experiments._build = builder
        yield client, parts, live, builder


def _ingestion_revision(client: TestClient) -> str:
    pipeline = new_pipeline(client.app, "Ingest")
    document = canonical_ingestion_definition("graph").model_dump(mode="json")
    response = client.post(
        f"/v1/pipelines/{pipeline['pipeline_id']}/revisions",
        json={"document": document},
        headers=ORIGIN,
    )
    assert response.status_code == 201, response.text
    return response.json()["revision"]["revision_id"]


def test_ingestion_experiment_keeps_index_and_outputs_in_its_workspace(
    setup: Any, tmp_path: Path
) -> None:
    client, parts, live, builder = setup
    body = register(client, parts.root, actions=["read", "ingest"])
    context_id = body["experiment"]["context_id"]
    output = Path(body["experiment"]["output_dir"])
    header = bound_bearer(client, context_id)
    sources = copy_sources(tmp_path)
    response = client.post(
        "/v1/runs",
        json={
            "revision_id": _ingestion_revision(client),
            "inputs": {"path": str(sources)},
            "experiment_context": context_id,
        },
        headers={**ORIGIN, **header},
    )
    assert response.status_code == 202, response.text
    run = wait_run(client, response.json()["run"]["run_id"], header)
    assert run["status"] == "succeeded", run["failure"]

    # The index lives below the experiment workspace.
    backend = run["resources"]["experiment"]["backend"]
    assert under(backend["store_path"], output)
    assert run["resources"]["index"]["backend"]["index_identity"] == backend["index_identity"]
    assert run["resources"]["index"]["collections"]["graph"]["exists"] is False
    assert "graph" in builder.engines[0].list_collections()
    # The run outputs live below the experiment workspace too.
    assert under(run["resources"]["artefact_root"], output)
    result_file = Path(run["resources"]["artefact_root"]) / run["run_id"] / "result.json"
    assert result_file.is_file() and under(result_file, output)
    workspace_artefacts = tmp_path / "ws" / "artefacts"
    assert not (workspace_artefacts / run["run_id"]).exists()
    # The protected result route still resolves the stored result.
    result = client.get(f"/v1/runs/{run['run_id']}/result", headers=header)
    assert result.status_code == 200, result.text
    assert len(result.json()["result"]["completed_effects"]) == 3
    # The live library is untouched.
    assert live.runs == [] and live.store.writes == []
    assert not (tmp_path / "live").exists()

    # Cleanup removes the record and never the experiment outputs.
    preview = client.post(
        "/v1/workspace/cleanup/preview",
        json={"selector": {"run_id": run["run_id"]}},
        headers=ORIGIN,
    ).json()["preview"]
    assert [item["run_id"] for item in preview["runs"]] == [run["run_id"]]
    assert preview["totals"]["files"] == 0, "experiment outputs are not cleanup files"
    applied = client.post(
        "/v1/workspace/cleanup",
        json={"token": preview["token"], "selector": {"run_id": run["run_id"]}},
        headers=ORIGIN,
    )
    assert applied.status_code == 200, applied.text
    assert client.get(f"/v1/runs/{run['run_id']}").status_code == 404
    assert result_file.is_file()
    assert Path(backend["store_path"]).is_dir()


def test_linked_run_output_directory_is_refused_before_any_run(setup: Any, tmp_path: Path) -> None:
    client, parts, live, _ = setup
    body = register(client, parts.root, actions=["read", "ingest"])
    output = Path(body["experiment"]["output_dir"])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    output.mkdir(exist_ok=True)
    (output / "omrs-runs").symlink_to(elsewhere, target_is_directory=True)
    response = client.post(
        "/v1/runs",
        json={
            "revision_id": _ingestion_revision(client),
            "inputs": {"path": str(copy_sources(tmp_path))},
            "experiment_context": body["experiment"]["context_id"],
        },
        headers=ORIGIN,
    )
    assert response.status_code == 403, response.text
    assert list(elsewhere.iterdir()) == []
    assert live.runs == []
