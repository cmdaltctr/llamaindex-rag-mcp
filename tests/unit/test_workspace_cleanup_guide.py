"""Every path and name that the workspace guide cites exists (task 5.5)."""

from __future__ import annotations

import importlib
import re
import sqlite3
from pathlib import Path

import pytest

from omrs.core.workspace import (
    DEFAULT_CLEANUP_TTL_SECONDS,
    MAX_ARTEFACT_BYTES,
    MAX_PREVIEW_ROWS,
    MAX_SUMMARY_BYTES,
    MAX_TEXT_BYTES,
    WorkspaceLayout,
)
from omrs.integrations.workspace_sqlite import SqliteWorkspaceRepository

REPO = Path(__file__).resolve().parents[2]
GUIDE = REPO / "docs" / "guides" / "workspace.md"
_CODE = re.compile(r"`([^`\n]+)`")
_DOTTED = re.compile(r"omrs(?:\.[A-Za-z_]\w*)+")
_LAYOUT = re.compile(r"<!-- workspace-layout -->(.*?)<!-- /workspace-layout -->", re.S)
_EXAMPLE = re.compile(r"<!-- cleanup-example -->\s*```python\n(.*?)```", re.S)
_LINK = re.compile(r"\]\(([\w-]+\.md)(?:#([\w-]+))?\)")


def _text() -> str:
    return GUIDE.read_text(encoding="utf-8")


def _spans() -> list[str]:
    return _CODE.findall(_text())


def _anchor(heading: str) -> str:
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def test_cited_repository_paths_exist() -> None:
    cited = [s for s in _spans() if s.startswith(("src/", "tests/", "docs/"))]
    assert cited, "the guide cites no repository path"
    assert [path for path in cited if not (REPO / path).exists()] == []


def test_cited_python_names_resolve() -> None:
    names = sorted({m.group() for span in _spans() for m in _DOTTED.finditer(span)})
    assert "omrs.core.workspace.WorkspaceCleanup.preview_cleanup" in names
    for name in names:
        parts = name.split(".")
        for split in range(len(parts), 0, -1):
            try:
                target: object = importlib.import_module(".".join(parts[:split]))
            except ImportError:
                continue
            for attribute in parts[split:]:
                target = getattr(target, attribute)
            break
        else:
            pytest.fail(f"cannot import {name}")


def test_cited_selector_methods_and_errors_exist() -> None:
    import omrs.core.workspace as workspace

    methods = [m for s in _spans() for m in re.findall(r"^CleanupSelector\.(\w+)\(", s)]
    assert sorted(methods) == ["by_status", "older_than", "run"]
    assert all(callable(getattr(workspace.CleanupSelector, name)) for name in methods)
    for name in ("UnsafeInputError", "WorkspaceLock"):
        assert name in _spans()
    assert hasattr(workspace, "UnsafeInputError")
    assert "class WorkspaceLock" in _api_source()


def test_layout_table_matches_workspace_layout(tmp_path: Path) -> None:
    rows = _LAYOUT.search(_text())
    assert rows is not None
    names = re.findall(r"^\| `([^`]+)` \|", rows.group(1), re.M)
    layout = WorkspaceLayout(tmp_path)
    expected = {
        layout.records.name,
        layout.lock.name,
        layout.artefacts.name + "/",
        layout.uploads.name + "/",
    }
    assert expected <= set(names)
    backup = [name for name in names if name.endswith(".bak")]
    assert backup == [f"{layout.records.name}.v<old>-to-v<new>.<time>.bak"]


def _api_files() -> list[Path]:
    return sorted((REPO / "src/omrs/transports/api").rglob("*.py"))


def _api_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in _api_files())


def test_api_source_reads_the_route_modules() -> None:
    """The scan must reach ``api/routes/``, or the checks below read nothing there."""
    assert any(path.parent.name == "routes" for path in _api_files())


def test_layout_names_match_the_web_wiring(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path)
    source = _api_source()
    # The web wiring takes every name from WorkspaceLayout, never a local copy.
    assert "WorkspaceLayout(" in source
    for path in (layout.records, layout.lock, layout.artefacts, layout.uploads):
        assert f'"{path.name}"' not in source, f"duplicate literal {path.name!r}"
    web_source = (REPO / "src/omrs/transports/cli/web.py").read_text(encoding="utf-8")
    cleanup_source = (REPO / "src/omrs/core/workspace/cleanup.py").read_text(encoding="utf-8")
    assert '".omrs" / "workspace"' in cleanup_source
    assert "~/.omrs/workspace" in _spans()
    for option in [s for s in _spans() if s.startswith("--")]:
        assert f'"{option}"' in web_source, option


def test_table_names_and_backup_name_match_the_database(tmp_path: Path) -> None:
    layout = WorkspaceLayout(tmp_path / "ws")
    SqliteWorkspaceRepository(layout.records)
    conn = sqlite3.connect(layout.records)
    try:
        query = "SELECT name FROM sqlite_master WHERE type = 'table'"
        tables = {row[0] for row in conn.execute(query)}
    finally:
        conn.close()
    assert tables == {
        "pipelines",
        "pipeline_revisions",
        "runs",
        "run_events",
        "plugin_registrations",
        "workspace_settings",
        "mcp_tokens",
        "profiles",
        "chat_folders",
        "chats",
        "chat_turns",
    }
    assert tables <= set(_spans())
    schema = (REPO / "src/omrs/integrations/workspace_sqlite/schema.py").read_text("utf-8")
    assert '.v{current}-to-v{target}.{stamp}.bak"' in schema


def test_documented_limits_match_the_code() -> None:
    text = _text()
    assert MAX_TEXT_BYTES == 4 * 1024 and "first 4 KiB" in text
    assert MAX_PREVIEW_ROWS == 100 and "first 100 entries" in text
    assert MAX_SUMMARY_BYTES == 16 * 1024 and "16 KiB or less" in text
    assert MAX_ARTEFACT_BYTES == 64 * 1024 * 1024 and "64 MiB or less" in text
    assert f"expires after {int(DEFAULT_CLEANUP_TTL_SECONDS)} seconds" in text


def test_relative_links_and_anchors_exist() -> None:
    links = _LINK.findall(_text())
    assert links
    for file_name, anchor in links:
        target = GUIDE.parent / file_name
        assert target.is_file(), file_name
        if anchor:
            headings = re.findall(r"^#+ (.+)$", target.read_text(encoding="utf-8"), re.M)
            assert anchor in {_anchor(h) for h in headings}, f"{file_name}#{anchor}"


def test_cleanup_example_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    example = _EXAMPLE.search(_text())
    assert example is not None
    monkeypatch.setenv("HOME", str(tmp_path))
    exec(compile(example.group(1), str(GUIDE), "exec"), {})  # noqa: S102 - guide example
    assert WorkspaceLayout(tmp_path / ".omrs" / "workspace").records.is_file()
