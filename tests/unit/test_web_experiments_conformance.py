"""Response conformance for experiment routes and experiment refusals (task 8.5).

Every response, including the stable experiment refusal bodies on
credential issue and run submission, is validated against
``openapi.yaml``.
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
    save_revision,
    submit,
)
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402
from tests.unit.test_web_runs_support import make_engine  # noqa: E402


def test_experiment_responses_conform(tmp_path: Path, effective_settings: Any) -> None:
    parts = build_experiment_app(tmp_path, make_engine(effective_settings), effective_settings)
    workspace = parts.root / "exp-a"
    workspace.mkdir()
    check = ContractChecker()
    with TestClient(parts.app, base_url=BASE) as client:
        login(client, parts.policy)
        check.check(client.get("/v1/experiments"), 200)
        folder = check.check(
            client.post("/v1/experiment-folders", json={"path": "main/sub"}, headers=ORIGIN), 201
        )
        assert folder["folder"]["path"] == "main/sub"
        again = client.post("/v1/experiment-folders", json={"path": "main/sub"}, headers=ORIGIN)
        assert check.check(again, 409)["code"] == "exists"
        escape = client.post("/v1/experiment-folders", json={"path": "a/../b"}, headers=ORIGIN)
        assert check.check(escape, 400)["code"] == "traversal"
        bad = client.post("/v1/experiments", json={"workspace": "relative"}, headers=ORIGIN)
        assert check.check(bad, 400)["code"] == "not_absolute"
        body = {"workspace": str(workspace), "name": "a", "actions": ["read"]}
        created = check.check(client.post("/v1/experiments", json=body, headers=ORIGIN), 201)
        context_id = created["experiment"]["context_id"]
        check.check(client.get(f"/v1/experiments/{context_id}"), 200)
        check.check(client.get("/v1/experiments"), 200)
        issued = check.check(
            client.post(
                "/v1/credentials",
                json={"scopes": ["run", "read"], "experiment_context": context_id},
                headers=ORIGIN,
            ),
            201,
        )
        check.check(client.get("/v1/credentials"), 200)
        unknown = client.post(
            "/v1/credentials",
            json={"scopes": ["run"], "experiment_context": "exp_ffffffffffffffff"},
            headers=ORIGIN,
        )
        check.check(unknown, 400)
        header = {"Authorization": f"Bearer {issued['token']}"}
        revision_id = save_revision(client)
        live = check.check(submit(client, revision_id, headers=header), 403)
        assert live["code"] == "live_library_target"
        check.check(submit(client, revision_id, context=context_id, headers=header), 202)
        check.check(client.get("/v1/experiments/exp_0000000000000000"), 404)
        check.check(client.delete(f"/v1/experiments/{context_id}", headers=ORIGIN), 200)
        check.check(client.delete("/v1/experiments/exp_0000000000000000", headers=ORIGIN), 404)
    assert check.operations >= FAMILIES["experiments"]


def test_register_without_roots_conforms(tmp_path: Path, effective_settings: Any) -> None:
    parts = build_experiment_app(
        tmp_path,
        make_engine(effective_settings),
        effective_settings,
        experiment_roots=(),
        experiments_factory=None,
    )
    check = ContractChecker()
    with TestClient(parts.app, base_url=BASE) as client:
        login(client, parts.policy)
        refused = client.post("/v1/experiments", json={"workspace": str(tmp_path)}, headers=ORIGIN)
        check.check(refused, 409)
        no_root = client.post("/v1/experiment-folders", json={"path": "x"}, headers=ORIGIN)
        check.check(no_root, 409)
        check.check(client.get("/v1/experiments"), 200)
