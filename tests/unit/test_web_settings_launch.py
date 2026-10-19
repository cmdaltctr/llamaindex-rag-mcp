"""The web launch hands saved rows to ``omrg.jsonc`` and publishes the notice (task 6.2).

``prepare_settings`` runs in the lifespan before the providers load. The user
config folder is a temporary one (``OMRG_CONFIG_DIR``) and the keychain is a fake.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit import test_web_connections_edit as edit  # noqa: E402

from omrg.config.settings_file import read_settings_file  # noqa: E402
from omrg.core.workspace import WorkspaceLayout  # noqa: E402
from omrg.integrations.workspace_sqlite import SqliteWorkspaceRepository  # noqa: E402
from omrg.integrations.workspace_sqlite.settings import WorkspaceSettings  # noqa: E402

harness = edit.harness


def seed_rows(workspace: Path, *, port: int, mcp: bool) -> WorkspaceSettings:
    """Write the database rows an older build left behind."""
    records = WorkspaceLayout(workspace).records
    records.parent.mkdir(parents=True, exist_ok=True)
    SqliteWorkspaceRepository(records)
    rows = WorkspaceSettings(records)
    rows.set_web_port(port)
    rows.set_mcp_http_enabled(mcp)
    return rows


def test_the_launch_moves_saved_rows_into_the_file(harness: Any, tmp_path: Path) -> None:
    rows = seed_rows(tmp_path / "ws", port=9123, mcp=True)
    with harness() as h:
        values = read_settings_file().values
        assert values["web_port"] == 9123
        assert values["mcp_http_enabled"] is True
        assert rows.get_web_port() is None
        assert rows.get_mcp_http_enabled() is False
        body = h.client.get("/v1/settings/configuration").json()
        assert body["handover"] == {"pending": False, "folder": None}
        assert body["revision"] == read_settings_file().revision


def test_the_configuration_answers_when_no_rows_exist(harness: Any) -> None:
    with harness() as h:
        response = h.client.get("/v1/settings/configuration")
        assert response.status_code == 200
        assert response.json()["handover"]["pending"] is False


def test_a_hand_edit_of_a_restart_only_key_is_pending_not_applied(harness: Any) -> None:
    from omrg.config.settings_file_write import write_settings

    with harness() as h:
        write_settings({"web_port": 9555}, revision=None)
        rows = {r["key"]: r for r in h.client.get("/v1/settings/configuration").json()["settings"]}
        assert rows["web_port"]["restart_pending"] is True
