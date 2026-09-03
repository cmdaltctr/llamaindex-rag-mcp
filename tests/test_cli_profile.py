"""Tests for the ``rag-mcp set-profile`` CLI command.

Task 12.2. This command sat at 17% coverage: the preview/confirm safety
contract (§6.4 M6) was exercised through the MCP transport but never through
the CLI, so the CLI's own confirmation flow was unverified.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from rag_mcp.transports.cli import app

runner = CliRunner()

_CONTRACT = {
    "collection": "docs",
    "chunk_count": 12,
    "old_profile": "documents",
    "new_profile": "codebase",
    "lever_impacts": [
        {"lever": "top_k", "timing": "query-time", "change": "10 → 20"},
        {"lever": "chunk strategy", "timing": "ingest-time", "change": "markdown → code"},
    ],
    "reingest_pointer": "Run `rag-mcp ingest --force` to re-chunk.",
}


def _patched(apply_result: dict | None = None):
    """Patch the two core entry points the command delegates to."""
    return (
        patch(
            "rag_mcp.core.profiles.generate_safety_contract",
            return_value=_CONTRACT,
        ),
        patch(
            "rag_mcp.core.profiles.apply_profile_change",
            return_value=apply_result
            or {"status": "ok", "profile": "codebase", "chunk_count_unchanged": 12},
        ),
        patch("rag_mcp.compose.build_profile_resolver", return_value=MagicMock()),
    )


class TestValidation:
    """An unknown profile is rejected before anything is read."""

    @pytest.mark.parametrize("bad", ["hybrid", "nonsense", ""])
    def test_invalid_profile_exits_nonzero(self, bad: str) -> None:
        result = runner.invoke(app, ["set-profile", "-c", "docs", "-p", bad])
        assert result.exit_code == 1

    def test_hybrid_is_rejected_as_operational_profile(self) -> None:
        """hybrid is a mode selector, not something a collection can be set to."""
        result = runner.invoke(app, ["set-profile", "-c", "docs", "-p", "hybrid"])
        assert result.exit_code == 1


class TestPreviewAndConfirm:
    """The safety contract must be shown before any change is applied."""

    def test_json_without_yes_prints_the_contract_only(self) -> None:
        """--json alone previews: it must NOT apply the change."""
        c, a, r = _patched()
        with c, a as apply_mock, r:
            result = runner.invoke(app, ["set-profile", "-c", "docs", "-p", "codebase", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.stderr)
        assert result.stdout.strip() == "", "--json output must not write to stdout"
        assert payload["new_profile"] == "codebase"
        apply_mock.assert_not_called()

    def test_json_with_yes_applies_the_change(self) -> None:
        """--json --yes skips the prompt and applies."""
        c, a, r = _patched()
        with c, a as apply_mock, r:
            result = runner.invoke(
                app, ["set-profile", "-c", "docs", "-p", "codebase", "--json", "--yes"]
            )
        assert result.exit_code == 0
        apply_mock.assert_called_once_with("docs", "codebase")

    def test_declining_the_prompt_makes_no_change(self) -> None:
        """Answering 'n' must leave the collection untouched."""
        c, a, r = _patched()
        with c, a as apply_mock, r:
            result = runner.invoke(
                app, ["set-profile", "-c", "docs", "-p", "codebase"], input="n\n"
            )
        assert apply_mock.assert_not_called() is None
        assert result.exit_code in (0, 1)

    def test_accepting_the_prompt_applies_the_change(self) -> None:
        """Answering 'y' applies it."""
        c, a, r = _patched()
        with c, a as apply_mock, r:
            runner.invoke(app, ["set-profile", "-c", "docs", "-p", "codebase"], input="y\n")
        apply_mock.assert_called_once_with("docs", "codebase")

    def test_yes_flag_bypasses_the_prompt(self) -> None:
        """--yes applies without reading stdin."""
        c, a, r = _patched()
        with c, a as apply_mock, r:
            runner.invoke(app, ["set-profile", "-c", "docs", "-p", "codebase", "--yes"])
        apply_mock.assert_called_once_with("docs", "codebase")

    def test_preview_reports_the_lever_impacts(self) -> None:
        """The human-readable preview must surface what actually changes."""
        c, a, r = _patched()
        with c, a, r:
            result = runner.invoke(
                app, ["set-profile", "-c", "docs", "-p", "codebase"], input="n\n"
            )
        assert "top_k" in result.stdout or "top_k" in (result.stderr or "")
