"""REST error bodies carry no provider credentials (design D9, task 1.8)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_jobs import build_app  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    RecordingEngine,
    lance_store,
    login,
    wait_for,
)
from tests.unit.test_web_runs_support import graph  # noqa: E402

from omrg.core.pipelines import PipelineIssue, PipelineValidationError  # noqa: E402
from omrg.core.vectordb.identity import RedactionSecrets  # noqa: E402

_TENANT = "9" * 8 + "-tenant"
_OPENROUTER = "sk-or-" + "4" * 12


class LeakyEngine(RecordingEngine):
    """Engine whose graph validation fails with provider values in the text."""

    def validate_pipeline(self, *args: Any, **kwargs: Any) -> Any:
        raise PipelineValidationError(
            [PipelineIssue(code="unknown_port", message=f"bad tenant={_TENANT} key={_OPENROUTER}")]
        )


def _engine(cls: type, tmp_path: Path, effective_settings: Any) -> Any:
    return cls(
        effective_settings(),
        store=lance_store(tmp_path),
        embed_model=object(),
        redaction=RedactionSecrets(
            chroma_cloud_tenant=_TENANT,
            openrouter_api_key=_OPENROUTER,
        ),
    )


def test_job_failure_body_has_no_provider_values(tmp_path: Path, effective_settings: Any) -> None:
    approved = tmp_path / "approved"
    approved.mkdir()
    engine = _engine(RecordingEngine, tmp_path, effective_settings)
    engine.raise_on["ingest"] = RuntimeError(f"401 tenant={_TENANT} key={_OPENROUTER}")
    app, policy = build_app(tmp_path, engine, roots=[approved])
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        job = client.post("/v1/ingestions", json={"path": str(approved)}, headers=ORIGIN).json()
        done = wait_for(lambda: client.get(f"/v1/jobs/{job['job_id']}").json())
    assert done["status"] == "failed"
    assert done["error"].startswith("RuntimeError")
    assert _TENANT not in done["error"]
    assert _OPENROUTER not in done["error"]


def test_graph_validation_failure_body_has_no_provider_values(
    tmp_path: Path, effective_settings: Any
) -> None:
    engine = _engine(LeakyEngine, tmp_path, effective_settings)
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.post(
            "/v1/pipelines/validate", json={"document": graph(top_k=2)}, headers=ORIGIN
        )
    assert response.status_code == 422, response.text
    text = response.text
    assert _TENANT not in text
    assert _OPENROUTER not in text
    assert response.json()["issues"][0]["code"] == "unknown_port"


def test_unhandled_http_error_detail_is_redacted(tmp_path: Path, effective_settings: Any) -> None:
    from fastapi import HTTPException

    engine = _engine(RecordingEngine, tmp_path, effective_settings)
    app, policy = build_app(tmp_path, engine)

    @app.get("/v1/_leak")
    async def leak() -> None:
        raise HTTPException(400, f"provider said tenant={_TENANT}")

    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.get("/v1/_leak")
    assert response.status_code == 400
    assert _TENANT not in response.text
