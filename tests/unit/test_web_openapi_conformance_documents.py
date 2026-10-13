"""Response conformance for the foundation, document and job routes (task 6.7).

Each flow drives the real application (real Engine over a real LanceDB
store, real SQLite run service, mock embedder, fake answer model) and
validates every response, success and error, against the schema that
``openapi.yaml`` declares for its operation and status. A status the
contract does not declare fails the check.
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
    FakeLLM,
    RecordingEngine,
    build_app,
    lance_store,
    login,
    make_engine,
    seed,
)
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402

from omrg.transports.api.app import create_app  # noqa: E402
from omrg.transports.api.lifespan import WebConfig  # noqa: E402
from omrg.transports.api.runs_wiring import run_service_factory  # noqa: E402
from omrg.transports.api.security import AccessPolicy  # noqa: E402

COLLECTION = "notes"


def _jobs_app(tmp_path: Path, engine: Any, root: Path) -> tuple[Any, AccessPolicy]:
    config = WebConfig(workspace=tmp_path / "ws", port=8765, roots=(root,), static_dir=None)
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(
        config,
        policy=policy,
        engine_factory=lambda: engine,
        run_service_factory=run_service_factory,
    )
    return app, policy


def _poll(client: TestClient, check: ContractChecker, job_id: str) -> dict[str, Any]:
    import time

    deadline = time.monotonic() + 10
    while True:
        body = check.check(client.get(f"/v1/jobs/{job_id}"), 200)
        if body["status"] in {"completed", "failed"}:
            return body
        assert time.monotonic() < deadline, body
        time.sleep(0.02)


def test_foundation_and_job_responses_conform(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrg.core.codebase import codebase_map

    monkeypatch.setattr(codebase_map, "get_codebase_map_text", lambda **_: "MAP")
    root = tmp_path / "approved"
    root.mkdir()
    (root / "a.md").write_text("# a", encoding="utf-8")
    engine = RecordingEngine(
        effective_settings(), store=lance_store(tmp_path), embed_model=object()
    )
    engine.ingest_result = {"status": "ok", "files_processed": 1}
    app, policy = _jobs_app(tmp_path, engine, root)
    check = ContractChecker()
    with TestClient(app, base_url=BASE) as client:
        # Public and bootstrap.
        assert check.check(client.get("/v1/health"), 200)["ready"] is True
        check.check(client.get("/v1/session"), 401)
        check.check(client.post("/v1/session", json={"bootstrap": "x"}, headers=ORIGIN), 401)
        check.check(client.get("/v1/collections", params={"token": "x"}), 400)
        login(client, policy)
        assert check.check(client.get("/v1/session"), 200)["kind"] == "session"
        check.check(client.post("/v1/ingestions", json={"path": "/x"}), 403)  # no Origin
        # Credentials.
        issued = check.check(
            client.post(
                "/v1/credentials", json={"scopes": ["read"], "label": "nb"}, headers=ORIGIN
            ),
            201,
        )
        check.check(client.post("/v1/credentials", json={"scopes": ["files"]}, headers=ORIGIN), 400)
        assert check.check(client.get("/v1/credentials"), 200)["credentials"]
        auth = {"Authorization": f"Bearer {issued['token']}"}
        assert check.check(client.get("/v1/session", headers=auth), 200)["kind"] == "bearer"
        check.check(client.get("/v1/roots", headers=auth), 403)
        check.check(client.delete(f"/v1/credentials/{issued['id']}", headers=ORIGIN), 200)
        check.check(client.delete("/v1/credentials/unknown", headers=ORIGIN), 404)
        check.check(client.get("/v1/session", headers=auth), 401)
        # Roots and uploads.
        assert check.check(client.get("/v1/roots"), 200)["roots"]
        preflight = "/v1/uploads/preflight"
        check.check(client.post(preflight, json={"name": "a.md", "size": 3}, headers=ORIGIN), 200)
        check.check(client.post(preflight, json={"name": "a.zip"}, headers=ORIGIN), 415)
        check.check(
            client.post(preflight, json={"name": "a.md", "size": 2**40}, headers=ORIGIN), 413
        )
        check.check(client.post(preflight, json={"name": "../a.md"}, headers=ORIGIN), 400)
        upload = {**ORIGIN, "X-Upload-Name": "b.md"}
        stored = check.check(client.post("/v1/uploads", content=b"# b", headers=upload), 201)
        assert "path" not in stored["upload"]
        check.check(client.post("/v1/uploads", content=b"# b", headers=ORIGIN), 400)
        # Jobs: 202 with an id, polling to a terminal state.
        job = check.check(
            client.post("/v1/ingestions", json={"path": str(root / "a.md")}, headers=ORIGIN), 202
        )
        assert job["status"] in {"queued", "running"} and uuid.UUID(job["job_id"])
        assert _poll(client, check, job["job_id"])["status"] == "completed"
        events = check.check(client.get(f"/v1/jobs/{job['job_id']}/events"), 200)
        assert events["job_status"] == "completed" and events["events"]
        check.check(client.get("/v1/jobs/not-a-uuid/events"), 404)
        check.check(
            client.post("/v1/ingestions", json={"path": str(tmp_path)}, headers=ORIGIN), 403
        )
        check.check(client.post("/v1/ingestions", json={"path": 1, "x": 2}, headers=ORIGIN), 400)
        mapped = check.check(
            client.post("/v1/codebase-maps", json={"path": str(root)}, headers=ORIGIN), 202
        )
        assert _poll(client, check, mapped["job_id"])["result"] == {"map": "MAP"}
        check.check(client.get("/v1/jobs/not-a-uuid"), 404)
        engine.raise_on["ingest"] = RuntimeError("disk gone")
        failing = client.post("/v1/ingestions", json={"path": str(root)}, headers=ORIGIN)
        failed = _poll(client, check, check.check(failing, 202)["job_id"])
        assert failed["status"] == "failed" and failed["error"]
    assert check.operations >= FAMILIES["foundation"] | FAMILIES["jobs"]


@pytest.fixture
def seeded(tmp_path: Path) -> Any:
    store = lance_store(tmp_path)
    seed(store, COLLECTION, str(tmp_path / "a.md"), 3)
    seed(store, COLLECTION, str(tmp_path / "b.md"), 2)
    return store


def test_document_and_destructive_responses_conform(
    tmp_path: Path, seeded: Any, effective_settings: Any
) -> None:
    engine = make_engine(seeded, effective_settings(), answer_llm_factory=FakeLLM)
    app, policy = build_app(tmp_path, engine)
    check = ContractChecker()
    base = f"/v1/collections/{COLLECTION}"
    query = {"query": "chunk", "rerank": False, "hybrid": False, "similarity_threshold": 0.0}
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        assert check.check(client.get("/v1/collections"), 200)
        assert check.check(client.get(f"{base}/documents"), 200)
        rows = check.check(client.post(f"{base}/search", json=query, headers=ORIGIN), 200)
        check.check(
            client.post(f"{base}/search", json={**query, "diagnostics": True}, headers=ORIGIN), 200
        )
        check.check(
            client.post(f"{base}/search", json={"query": "q", "top_k": 0}, headers=ORIGIN), 400
        )
        answer = check.check(client.post(f"{base}/answer", json=query, headers=ORIGIN), 200)
        assert answer["status"] == "ok"
        chunk = check.check(client.get(f"{base}/chunks/{rows[0]['chunk_id']}"), 200)
        assert chunk["text_format"] == "plain"
        check.check(client.get(f"{base}/chunks/nope"), 404)
        check.check(client.get(f"{base}/chunks/nope", params={"window": 9}), 400)
        # Deletion: preview, missing token, confirm, reuse.
        selector = {"path": str(tmp_path / "a.md")}
        preview = check.check(
            client.request(
                "DELETE", f"{base}/documents", json={**selector, "dry_run": True}, headers=ORIGIN
            ),
            200,
        )
        assert preview["would_delete"] == 3
        check.check(
            client.request("DELETE", f"{base}/documents", json=selector, headers=ORIGIN), 428
        )
        token = {**selector, "confirmation_token": preview["confirmation"]["token"]}
        done = check.check(
            client.request("DELETE", f"{base}/documents", json=token, headers=ORIGIN), 200
        )
        assert done["chunks_removed"] == 3
        check.check(client.request("DELETE", f"{base}/documents", json=token, headers=ORIGIN), 409)
        # Profile change: preview, confirm, stale reuse.
        body = {"profile": "codebase"}
        shown = check.check(client.patch(f"{base}/profile", json=body, headers=ORIGIN), 200)
        assert shown["status"] == "preview" and shown["contract"]["new_profile"] == "codebase"
        confirm = {**body, "confirm": True, "confirmation_token": shown["confirmation"]["token"]}
        applied = check.check(client.patch(f"{base}/profile", json=confirm, headers=ORIGIN), 200)
        assert applied == {
            "status": "ok",
            "collection": COLLECTION,
            "profile": "codebase",
            "chunk_count_unchanged": 2,
        }
        check.check(client.patch(f"{base}/profile", json=confirm, headers=ORIGIN), 409)
        check.check(
            client.patch(f"{base}/profile", json={**body, "confirm": True}, headers=ORIGIN), 428
        )
        reader = {"Authorization": f"Bearer {policy.issue_bearer({'read', 'run'}).token}"}
        check.check(client.patch(f"{base}/profile", json=body, headers=reader), 403)
    assert check.operations >= FAMILIES["documents"]


def test_unavailable_runtime_returns_503_envelope(tmp_path: Path) -> None:
    """Without a started runtime, protected engine routes give a declared 503."""
    config = WebConfig(workspace=tmp_path / "ws", port=8765, static_dir=None)
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(config, policy=policy, engine_factory=lambda: None)
    client = TestClient(app, base_url=BASE)  # no lifespan: the runtime never starts
    check = ContractChecker()
    login(client, policy)
    assert check.check(client.get("/v1/health"), 200)["ready"] is False
    for path in ("/v1/collections", "/v1/roots", "/v1/pipelines", "/v1/runs"):
        check.check(client.get(path), 503)
