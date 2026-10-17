"""Canonical templates over HTTP (``GET /v1/pipeline-templates``, task 8.6).

The route returns ``compose_pipelines.pipeline_templates(engine)`` for the
live Engine. Each document saves as a revision and validates against the
same Engine, and a saved search template runs end to end with its output
stored as public search rows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402
from tests.unit.test_web_runs_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    build_app,
    login,
    make_engine,
    new_pipeline,
    wait_run,
)

from omrg.compose_pipelines import pipeline_templates  # noqa: E402


@pytest.fixture
def engine(effective_settings: Any) -> Any:
    return make_engine(effective_settings)


@pytest.fixture
def client(tmp_path: Path, engine: Any) -> Any:
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as test_client:
        login(test_client, policy)
        test_client.policy = policy  # type: ignore[attr-defined]
        yield test_client


def test_templates_match_the_composition_root(client: Any, engine: Any) -> None:
    check = ContractChecker()
    body = check.check(client.get("/v1/pipeline-templates"), 200)
    expected = pipeline_templates(engine)
    assert [t["name"] for t in body["templates"]] == [t.name for t in expected]
    for entry, template in zip(body["templates"], expected, strict=True):
        assert entry["document"] == template.definition.graph.model_dump(mode="json")
        assert entry["title"] == template.title
        assert entry["standard_operation"] == template.standard_operation
        assert [o["name"] for o in entry["outputs"]] == [
            o.name for o in template.definition.graph.outputs
        ]
    search = next(t for t in body["templates"] if t["name"] == "search")
    assert "public_rows" in search["outputs"][0]["description"]
    assert check.operations >= FAMILIES["templates"]


def test_templates_need_the_read_scope(client: Any) -> None:
    token = client.policy.issue_bearer({"run"}).token
    refused = client.get("/v1/pipeline-templates", headers={"Authorization": f"Bearer {token}"})
    assert refused.status_code == 403
    allowed = client.get("/v1/pipeline-templates", headers=bearer(client.policy, "read"))
    assert allowed.status_code == 200


def test_a_saved_search_template_runs_with_public_rows(client: Any) -> None:
    templates = client.get("/v1/pipeline-templates").json()["templates"]
    search = next(t for t in templates if t["name"] == "search")
    pipeline = new_pipeline(client.app, "From template")
    saved = client.post(
        f"/v1/pipelines/{pipeline['pipeline_id']}/revisions",
        json={"document": search["document"]},
        headers=ORIGIN,
    )
    assert saved.status_code == 201, saved.text
    submitted = client.post(
        "/v1/runs",
        json={"revision_id": saved.json()["revision"]["revision_id"], "inputs": {"query": "text"}},
        headers=ORIGIN,
    )
    assert submitted.status_code == 202, submitted.text
    run = wait_run(client, submitted.json()["run"]["run_id"])
    assert run["status"] == "succeeded", run["failure"]
    result = client.get(f"/v1/runs/{run['run_id']}/result").json()["result"]
    rows = result["outputs"]["results"]
    assert isinstance(rows, list) and rows
    assert {"text", "score"} <= set(rows[0])
