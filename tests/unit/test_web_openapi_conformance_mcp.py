"""Response conformance for the MCP state, token, web-port and upload-limit routes.

Every response, including the refusals, is validated against ``openapi.yaml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    build_app,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402

from omrg.transports.api.app import create_app  # noqa: E402
from omrg.transports.api.lifespan import WebConfig  # noqa: E402
from omrg.transports.api.security import AccessPolicy  # noqa: E402


def test_mcp_and_port_responses_conform(tmp_path: Path, effective_settings: Any) -> None:
    check = ContractChecker()
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        check.check(client.get("/v1/mcp"), 200)
        check.check(client.put("/v1/mcp", json={"enabled": True}, headers=ORIGIN), 200)
        check.check(client.put("/v1/mcp", json={"enabled": "yes"}, headers=ORIGIN), 400)
        check.check(client.post("/v1/mcp/token", headers=ORIGIN), 201)
        check.check(client.get("/v1/mcp"), 200)
        check.check(client.delete("/v1/mcp/token", headers=ORIGIN), 200)
        check.check(client.delete("/v1/mcp/token", headers=ORIGIN), 200)
        check.check(client.get("/v1/settings/web-port"), 200)
        check.check(client.put("/v1/settings/web-port", json={"port": 9100}, headers=ORIGIN), 200)
        check.check(client.put("/v1/settings/web-port", json={"port": 80}, headers=ORIGIN), 400)
        check.check(client.get("/v1/settings/upload-limit"), 200)
        limit = {"max_mib": 200}
        check.check(client.put("/v1/settings/upload-limit", json=limit, headers=ORIGIN), 200)
        check.check(
            client.put("/v1/settings/upload-limit", json={"max_mib": 0}, headers=ORIGIN), 400
        )

        read_only = bearer(policy, "read")
        client.cookies.clear()
        check.check(client.get("/v1/mcp", headers=read_only), 200)
        check.check(client.get("/v1/settings/web-port", headers=read_only), 200)
        check.check(client.put("/v1/mcp", json={"enabled": True}, headers=read_only), 403)
        check.check(client.post("/v1/mcp/token", headers=read_only), 403)
        check.check(client.delete("/v1/mcp/token", headers=read_only), 403)
        check.check(
            client.put("/v1/settings/web-port", json={"port": 9100}, headers=read_only), 403
        )
        check.check(client.get("/v1/settings/upload-limit", headers=read_only), 200)
        check.check(
            client.put("/v1/settings/upload-limit", json={"max_mib": 9}, headers=read_only), 403
        )
        check.check(client.get("/v1/mcp"), 401)

    assert check.operations >= FAMILIES["mcp"]


def test_upload_limit_set_at_launch_conforms(tmp_path: Path, effective_settings: Any) -> None:
    check = ContractChecker()
    engine = make_engine(lance_store(tmp_path), effective_settings())
    config = WebConfig(
        workspace=tmp_path / "ws", port=8765, static_dir=None, launch_upload_limit_mib=300
    )
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(config, policy=policy, engine_factory=lambda: engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        assert check.check(client.get("/v1/settings/upload-limit"), 200)["source"] == "launch"
        limit = {"max_mib": 200}
        check.check(client.put("/v1/settings/upload-limit", json=limit, headers=ORIGIN), 409)
