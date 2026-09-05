"""Security regression tests for path boundary validation in get_codebase_map.

Regression: ``get_codebase_map_text`` previously accepted any directory path
that existed on disk. An MCP caller could pass ``path="/etc"`` or
``path="../../../Users"`` and receive a full file-type inventory of a
directory outside the intended project root.

These tests verify the boundary is enforced BEFORE any scanning happens. The
rejection cases mock ``build_codebase_map`` and assert it is never called —
this isolates the boundary control from filesystem permission quirks (a real
``/etc`` scan can raise ``PermissionError``, which would produce an error
dict for the wrong reason and mask a missing boundary check).

The tests FAIL against the unpatched codebase (no boundary check → the mock
IS called → ``assert_not_called`` fails) and PASS once the fix is applied.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from omrg.core.codebase.codebase_map import CodebaseMap, get_codebase_map_text


class TestPathBoundaryValidation:
    """Security regression: get_codebase_map_text must enforce the project boundary."""

    def test_rejects_absolute_path_outside_project(self) -> None:
        """An absolute path outside the project root returns an error dict.

        ``/etc`` exists and is a directory, so without a boundary check it
        would be scanned. The mock sentinel ensures that if the check is
        missing, ``build_codebase_map`` IS invoked and the
        ``assert_not_called`` assertion fails deterministically.
        """
        sentinel = CodebaseMap(commit_hash="SENTINEL")
        with patch(
            "omrg.core.codebase.codebase_map.build_codebase_map",
            return_value=sentinel,
        ) as mock_build:
            result = get_codebase_map_text(path="/etc")

        # The scan must NOT have run — the boundary check rejects first.
        mock_build.assert_not_called()

        # And the function must return a JSON error, not a codebase map.
        parsed = json.loads(result)
        assert parsed["status"] == "error"

    def test_current_directory_works_normally(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The current directory ('.') is allowed and produces a real map.

        Uses a clean ``tmp_path`` as the working directory so the test does
        not depend on the repository's own contents. Magika is forced off so
        the suffix fallback runs (no external binary required).
        """
        monkeypatch.chdir(tmp_path)
        (tmp_path / "app.py").write_text("x = 1\n")

        with patch(
            "omrg.integrations.magika._is_magika_available",
            return_value=False,
        ):
            result = get_codebase_map_text(path=".")

        # A successful map is markdown, not an error dict.
        assert "## File Types" in result
        assert "code/python" in result

    def test_rejects_dotdot_escape(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A relative '../' path escaping to an existing dir is rejected.

        Uses ``tmp_path`` to build a deterministic scenario: a ``project``
        directory with a ``secret`` sibling that exists on disk. From inside
        ``project``, the path ``../secret`` resolves to the sibling — it
        EXISTS (so it passes the existing ``exists()`` check) but lies
        OUTSIDE the project root, so only a boundary check can reject it.

        The literal ``../../../etc`` from the request was adapted because,
        from this repository's root, it resolves to a non-existent path and
        would be rejected by ``exists()`` — a false positive that does not
        exercise the boundary control.
        """
        project = tmp_path / "project"
        project.mkdir()
        (project / "app.py").write_text("x = 1\n")
        sibling = tmp_path / "secret"
        sibling.mkdir()
        (sibling / "passwords.txt").write_text("hunter2\n")

        monkeypatch.chdir(project)

        sentinel = CodebaseMap(commit_hash="SENTINEL")
        with patch(
            "omrg.core.codebase.codebase_map.build_codebase_map",
            return_value=sentinel,
        ) as mock_build:
            result = get_codebase_map_text(path="../secret")

        mock_build.assert_not_called()

        parsed = json.loads(result)
        assert parsed["status"] == "error"
