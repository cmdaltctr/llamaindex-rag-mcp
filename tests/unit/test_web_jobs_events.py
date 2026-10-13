"""Event inspection of ingestion and codebase-map jobs (``listJobEvents``).

``GET /v1/jobs/{job_id}/events`` pages the committed events of the hidden
run behind a job, with ``after_sequence`` polling like run events. It has
the scope of ``GET /v1/jobs/{job_id}`` and returns 404 for graph runs and
unknown ids. Real Engine over fakes, real run service; no model call.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_runs_service import wait_job  # noqa: E402
from tests.unit.test_web_runs_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    build_app,
    login,
    make_engine,
    save_revision,
    submit,
    wait_run,
)


@pytest.fixture
def setup(tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    root = tmp_path / "approved"
    root.mkdir()
    engine = make_engine(effective_settings)

    async def ingest(path: str, *, collection_name: str) -> dict[str, Any]:
        return {"status": "ok", "files_processed": 1}

    monkeypatch.setattr(engine, "ingest", ingest)
    app, policy = build_app(tmp_path, engine, roots=(root,))
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        yield client, policy, root


def _job(client: Any, root: Path) -> str:
    response = client.post("/v1/ingestions", json={"path": str(root)}, headers=ORIGIN)
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    assert wait_job(client, job_id)["status"] == "completed"
    return job_id


def test_job_events_page_the_hidden_run_events(setup: Any) -> None:
    client, _, root = setup
    job_id = _job(client, root)
    page = client.get(f"/v1/jobs/{job_id}/events")
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["status"] == "ok" and body["job_id"] == job_id
    assert body["job_status"] == "completed" and body["complete"] is True
    sequences = [event["sequence"] for event in body["events"]]
    assert sequences == sorted(sequences) and sequences[0] == 1
    statuses = [e["summary"].get("status") for e in body["events"] if e["kind"] == "run.status"]
    assert statuses[-1] == "succeeded"
    later = client.get(f"/v1/jobs/{job_id}/events", params={"after_sequence": sequences[0]})
    assert [e["sequence"] for e in later.json()["events"]] == sequences[1:]
    assert later.json()["last_sequence"] == sequences[-1]


def test_job_events_have_the_scope_of_job_status(setup: Any) -> None:
    client, policy, root = setup
    job_id = _job(client, root)
    reader = bearer(policy, "read")
    assert client.get(f"/v1/jobs/{job_id}", headers=reader).status_code == 200
    assert client.get(f"/v1/jobs/{job_id}/events", headers=reader).status_code == 200
    no_read = bearer(policy, "graph")
    assert client.get(f"/v1/jobs/{job_id}/events", headers=no_read).status_code == 403


def test_job_events_refuse_graph_runs_and_unknown_ids(setup: Any) -> None:
    client, _, _ = setup
    revision = save_revision(client)
    run = wait_run(client, submit(client, revision["revision_id"]).json()["run"]["run_id"])
    assert client.get(f"/v1/jobs/{run['run_id']}/events").status_code == 404
    assert client.get("/v1/jobs/not-a-uuid/events").status_code == 404
    unknown = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/v1/jobs/{unknown}/events").status_code == 404
