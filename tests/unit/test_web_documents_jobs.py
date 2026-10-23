"""Tests for ingestion jobs, job polling and chunk inspection (tasks 6.4, 6.6).

Ingestion and codebase-map requests return a ``Job`` (202) backed by the
workspace run service (one consumer, one queue, persisted records);
``GET /v1/jobs/{jobId}`` polls it. Paths must sit inside an approved
root. Chunk inspection serves stored text as JSON data with neighbour
navigation and never needs the original file.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    RecordingEngine,
    assert_conforms,
    bearer,
    lance_store,
    login,
    make_engine,
    seed,
    wait_for,
)

from omrs.transports.api.app import create_app  # noqa: E402
from omrs.transports.api.lifespan import WebConfig  # noqa: E402
from omrs.transports.api.runs_wiring import run_service_factory  # noqa: E402
from omrs.transports.api.security import AccessPolicy  # noqa: E402

COLLECTION = "notes"


def build_app(tmp_path: Path, engine: Any, roots: Any = ()) -> tuple[Any, AccessPolicy]:
    """Build the app around *engine* with the workspace run service wired in."""
    config = WebConfig(workspace=tmp_path / "ws", port=8765, roots=tuple(roots), static_dir=None)
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(
        config,
        policy=policy,
        engine_factory=lambda: engine,
        run_service_factory=run_service_factory,
    )
    return app, policy


@pytest.fixture
def approved(tmp_path: Path) -> Path:
    root = tmp_path / "approved"
    root.mkdir()
    (root / "a.md").write_text("# a", encoding="utf-8")
    return root


def _engine(tmp_path: Path, effective_settings) -> RecordingEngine:
    return RecordingEngine(effective_settings(), store=lance_store(tmp_path), embed_model=object())


# ── Ingestion jobs ───────────────────────────────────────────────────────


def test_ingestion_inside_root_runs_as_polled_job(
    tmp_path: Path, approved: Path, effective_settings
) -> None:
    engine = _engine(tmp_path, effective_settings)
    engine.ingest_result = {"status": "ok", "files_processed": 1}
    app, policy = build_app(tmp_path, engine, roots=[approved])
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        accepted = client.post(
            "/v1/ingestions",
            json={"path": str(approved / "a.md"), "collection": COLLECTION},
            headers=ORIGIN,
        )
        assert accepted.status_code == 202, accepted.text
        job = accepted.json()
        assert_conforms("/ingestions", "post", 202, job)
        uuid.UUID(job["job_id"])
        done = wait_for(lambda: client.get(f"/v1/jobs/{job['job_id']}").json())
    assert_conforms("/jobs/{jobId}", "get", 200, done)
    assert done["status"] == "completed"
    assert done["result"] == {"status": "ok", "files_processed": 1}
    assert done["error"] is None
    ((name, args, kwargs),) = engine.calls
    assert (name, args, kwargs) == (
        "ingest",
        (str((approved / "a.md").resolve()),),
        {"collection_name": COLLECTION},
    )


def test_ingestion_defaults_to_documents_collection(
    tmp_path: Path, approved: Path, effective_settings
) -> None:
    engine = _engine(tmp_path, effective_settings)
    app, policy = build_app(tmp_path, engine, roots=[approved])
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        job = client.post("/v1/ingestions", json={"path": str(approved)}, headers=ORIGIN).json()
        wait_for(lambda: client.get(f"/v1/jobs/{job['job_id']}").json())
    assert engine.calls[0][2] == {"collection_name": "documents"}


@pytest.mark.parametrize("target", ["outside", "relative", "traversal", "missing"])
def test_ingestion_outside_grants_is_denied_before_admission(
    tmp_path: Path, approved: Path, effective_settings, target: str
) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("secret", encoding="utf-8")
    paths = {
        "outside": str(outside),
        "relative": "a.md",
        "traversal": str(approved / ".." / "outside.md"),
        "missing": str(approved / "nope.md"),
    }
    engine = _engine(tmp_path, effective_settings)
    app, policy = build_app(tmp_path, engine, roots=[approved])
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.post("/v1/ingestions", json={"path": paths[target]}, headers=ORIGIN)
    assert response.status_code == 403
    assert_conforms("/ingestions", "post", 403, response.json())
    assert engine.calls == []


def test_uploaded_file_can_be_ingested_through_managed_root(
    tmp_path: Path, effective_settings
) -> None:
    engine = _engine(tmp_path, effective_settings)
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        upload = client.post(
            "/v1/uploads",
            content=b"# uploaded",
            headers={**ORIGIN, "X-Upload-Name": "up.md"},
        ).json()["upload"]
        managed = next(r for r in client.get("/v1/roots").json()["roots"] if r["kind"] == "managed")
        path = str(Path(managed["path"]) / upload["id"] / upload["name"])
        job = client.post("/v1/ingestions", json={"path": path}, headers=ORIGIN).json()
        done = wait_for(lambda: client.get(f"/v1/jobs/{job['job_id']}").json())
    assert done["status"] == "completed"
    assert engine.calls[0][1] == (path,)


def test_failed_ingestion_reports_redacted_error(
    tmp_path: Path, approved: Path, effective_settings
) -> None:
    engine = _engine(tmp_path, effective_settings)
    engine.raise_on["ingest"] = RuntimeError("boom omrs_bt_abc.secretvalue")
    app, policy = build_app(tmp_path, engine, roots=[approved])
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        job = client.post("/v1/ingestions", json={"path": str(approved)}, headers=ORIGIN).json()
        done = wait_for(lambda: client.get(f"/v1/jobs/{job['job_id']}").json())
    assert_conforms("/jobs/{jobId}", "get", 200, done)
    assert done["status"] == "failed"
    assert done["result"] is None
    assert done["error"].startswith("RuntimeError")
    assert "secretvalue" not in done["error"]


def test_ingestion_needs_session_file_scope(
    tmp_path: Path, approved: Path, effective_settings
) -> None:
    engine = _engine(tmp_path, effective_settings)
    app, policy = build_app(tmp_path, engine, roots=[approved])
    notebook = bearer(policy, "read", "run", "graph")
    with TestClient(app, base_url=BASE) as client:
        response = client.post("/v1/ingestions", json={"path": str(approved)}, headers=notebook)
    assert response.status_code == 403
    assert engine.calls == []


def test_unknown_job_is_404_envelope(tmp_path: Path, effective_settings) -> None:
    app, policy = build_app(tmp_path, _engine(tmp_path, effective_settings))
    with TestClient(app, base_url=BASE) as client:
        anonymous = client.get(f"/v1/jobs/{uuid.uuid4()}")
        login(client, policy)
        response = client.get(f"/v1/jobs/{uuid.uuid4()}")
    assert response.status_code == 404
    assert_conforms("/jobs/{jobId}", "get", 404, response.json())
    assert anonymous.status_code == 401


def test_job_polling_accepts_read_bearer(
    tmp_path: Path, approved: Path, effective_settings
) -> None:
    engine = _engine(tmp_path, effective_settings)
    app, policy = build_app(tmp_path, engine, roots=[approved])
    reader = bearer(policy, "read")
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        job = client.post("/v1/ingestions", json={"path": str(approved)}, headers=ORIGIN).json()
        client.cookies.clear()
        done = wait_for(lambda: client.get(f"/v1/jobs/{job['job_id']}", headers=reader).json())
    assert done["status"] == "completed"


# ── Codebase map jobs ────────────────────────────────────────────────────


def test_codebase_map_job_passes_engine_settings_and_store(
    tmp_path: Path, approved: Path, effective_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrs.core.codebase import codebase_map

    seen: dict[str, Any] = {}

    def fake_map(path: str = ".", refresh: bool = False, *, settings=None, store=None) -> str:
        seen.update(path=path, refresh=refresh, settings=settings, store=store)
        return "MAP"

    monkeypatch.setattr(codebase_map, "get_codebase_map_text", fake_map)
    store = lance_store(tmp_path)
    settings = effective_settings()
    engine = make_engine(store, settings)
    app, policy = build_app(tmp_path, engine, roots=[approved])
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        accepted = client.post(
            "/v1/codebase-maps", json={"path": str(approved), "refresh": True}, headers=ORIGIN
        )
        assert accepted.status_code == 202, accepted.text
        assert_conforms("/codebase-maps", "post", 202, accepted.json())
        job_id = accepted.json()["job_id"]
        done = wait_for(lambda: client.get(f"/v1/jobs/{job_id}").json())
        denied = client.post("/v1/codebase-maps", json={"path": str(tmp_path)}, headers=ORIGIN)
    assert done["status"] == "completed"
    assert done["result"] == {"map": "MAP"}
    assert seen["path"] == str(approved.resolve())
    assert seen["refresh"] is True
    assert seen["store"] is store
    # This Engine has no profile resolver, so its own settings are used.
    assert seen["settings"] is settings
    assert denied.status_code == 403


# ── Chunk inspection ─────────────────────────────────────────────────────


@pytest.fixture
def inspect_app(tmp_path: Path, effective_settings) -> tuple[Any, Any, list[str]]:
    store = lance_store(tmp_path)
    # The source path is outside every approved root: inspection must
    # still work because it reads stored chunks, never the original file.
    ids = seed(store, COLLECTION, "/elsewhere/report.md", 5)
    app, policy = build_app(tmp_path, make_engine(store, effective_settings()))
    return app, policy, ids


def test_chunk_inspection_returns_text_and_neighbours(inspect_app: Any) -> None:
    app, policy, ids = inspect_app
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.get(f"/v1/collections/{COLLECTION}/chunks/{ids[2]}")
        wide = client.get(f"/v1/collections/{COLLECTION}/chunks/{ids[0]}?window=3")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["chunk"]["chunk_id"] == ids[2]
    assert body["chunk"]["source_chunk_index"] == 2
    assert body["chunk"]["source"] == "/elsewhere/report.md"
    assert [row["chunk_id"] for row in body["previous"]] == [ids[1]]
    assert [row["chunk_id"] for row in body["next"]] == [ids[3]]
    wide_body = wide.json()
    assert wide_body["previous"] == []
    assert [row["chunk_id"] for row in wide_body["next"]] == ids[1:4]


def test_chunk_text_is_served_as_json_data_not_html(inspect_app: Any) -> None:
    app, policy, ids = inspect_app
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.get(f"/v1/collections/{COLLECTION}/chunks/{ids[0]}")
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["x-content-type-options"] == "nosniff"
    body = response.json()
    assert body["text_format"] == "plain"
    # The stored markup is returned verbatim as a string for text rendering.
    assert body["chunk"]["text"] == "<b>chunk 0</b> of /elsewhere/report.md"
    assert "id" not in body["chunk"]  # internal row ids stay private


def test_unknown_chunk_and_bad_window(inspect_app: Any) -> None:
    app, policy, ids = inspect_app
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        missing = client.get(f"/v1/collections/{COLLECTION}/chunks/chk_nope")
        other = client.get(f"/v1/collections/absent/chunks/{ids[0]}")
        wide = client.get(f"/v1/collections/{COLLECTION}/chunks/{ids[0]}?window=6")
    assert missing.status_code == 404
    assert missing.json()["status"] == "error"
    assert other.status_code == 404
    assert wide.status_code == 400


def test_chunk_inspection_needs_read_scope(inspect_app: Any) -> None:
    app, policy, ids = inspect_app
    with TestClient(app, base_url=BASE) as client:
        anonymous = client.get(f"/v1/collections/{COLLECTION}/chunks/{ids[0]}")
        runner = client.get(
            f"/v1/collections/{COLLECTION}/chunks/{ids[0]}", headers=bearer(policy, "run")
        )
        reader = client.get(
            f"/v1/collections/{COLLECTION}/chunks/{ids[0]}", headers=bearer(policy, "read")
        )
    assert anonymous.status_code == 401
    assert runner.status_code == 403
    assert reader.status_code == 200
