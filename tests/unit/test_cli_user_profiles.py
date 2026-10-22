"""``omrs search``, ``answer`` and ``ingest`` on user-profile collections (tasks 8.10, 8.11).

Spec: user-profiles, "User profiles work in every process that reads the
workspace" (design D11). The default workspace is a temporary home folder.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from tests.fixtures.pipeline_parity.ingestion.snapshot import copy_sources, pin_detection
from tests.unit.test_cli_user_profiles_support import (
    PROFILE,
    USER_COLLECTION,
    count_graph_runs,
    link_workspace,
    one_line,
    tag_collection,
    use_home,
    use_mock_embedder,
)
from typer.testing import CliRunner

from omrs.transports.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _cli_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Use a temporary home folder and the mock embedder; return the home folder."""
    import omrs.transports.cli as cli_module

    monkeypatch.setattr(cli_module, "_runtime_details_enabled", False)
    use_mock_embedder(monkeypatch)
    return use_home(monkeypatch, tmp_path / "home")


class _Completion:
    text = "The notes hold a seed note [1]."


class _Model:
    async def acomplete(self, prompt: str) -> _Completion:
        return _Completion()


@pytest.fixture(autouse=True)
def _answer_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the Engine an answer model that needs no network."""
    monkeypatch.setattr("omrs.compose_answer.build_answer_llm", lambda *_a, **_k: _Model())


@pytest.fixture
def workspace(tmp_path: Path, effective_settings: Any, _cli_env: Path) -> Path:
    """Link a workspace that holds ``my-notes`` and tag ``notes`` with it."""
    link_workspace(tmp_path, effective_settings, _cli_env)
    tag_collection(tmp_path, USER_COLLECTION, PROFILE)
    return tmp_path


def _invoke(command: str, tmp_path: Path, collection: str):
    """Run one command on ``collection`` and return the result."""
    if command == "ingest":
        args = ["ingest", str(copy_sources(tmp_path / "src")), "-c", collection, "--json"]
    else:
        args = [command, "what is in the notes", "-c", collection, "--json"]
    return runner.invoke(app, args)


# ── A collection that follows a user profile ──────────────────────────


@pytest.mark.parametrize("command", ["search", "answer", "ingest"])
def test_the_command_runs_the_user_profile_pipeline(
    command: str, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin_detection(monkeypatch)
    runs = count_graph_runs(monkeypatch)
    result = _invoke(command, workspace, USER_COLLECTION)
    assert result.exit_code == 0, result.output
    assert runs == ["run_pipeline"]
    assert result.stdout == "", "CLI output must go to stderr"


def test_ingest_into_a_user_profile_collection_indexes_the_files(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pin_detection(monkeypatch)
    result = _invoke("ingest", workspace, USER_COLLECTION)
    assert result.exit_code == 0, result.output
    assert '"files_indexed": 3' in result.stderr


# ── A built-in collection keeps the direct call ───────────────────────

_DIRECT = {
    "search": ("omrs.core.retrieval.search", {"return_value": []}),
    "answer": ("omrs.core.answer.answer", {"new_callable": AsyncMock}),
    "ingest": ("omrs.core.ingestion.ingest_path_async", {"new_callable": AsyncMock}),
}
_DIRECT_RESULT = {
    "answer": {"status": "no_evidence", "citations": [], "evidence": []},
    "ingest": {"status": "ok", "files_indexed": 0, "chunks_created": 0},
}


@pytest.mark.parametrize("command", ["search", "answer", "ingest"])
@pytest.mark.parametrize("tag", [None, "documents", "codebase"])
def test_a_built_in_collection_calls_the_core_function_directly(
    command: str, tag: str | None, workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tag_collection(workspace, "plain", tag)
    runs = count_graph_runs(monkeypatch)
    target, options = _DIRECT[command]
    with patch(target, **options) as direct:
        if command != "search":
            direct.return_value = _DIRECT_RESULT[command]
        result = _invoke(command, workspace, "plain")
    assert result.exit_code == 0, result.output
    direct.assert_called_once()
    assert runs == []


# ── No workspace database ─────────────────────────────────────────────


@pytest.mark.parametrize("command", ["search", "answer", "ingest"])
def test_a_user_profile_without_a_workspace_fails_with_the_binding_message(
    command: str, tmp_path: Path
) -> None:
    tag_collection(tmp_path, USER_COLLECTION, PROFILE)
    result = _invoke(command, tmp_path, USER_COLLECTION)
    assert result.exit_code == 1
    text = one_line(result.stderr)
    assert "'my-notes'" in text and "~/.omrs/workspace/workspace.db" in text
    assert "Start `omrs web` once" in text
    assert "'documents' or 'codebase'" in text
    assert result.stdout == ""
