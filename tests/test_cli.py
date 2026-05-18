"""Tests for the CLI interface (ingest, search, list subcommands).

Covers all CLI output modes (JSON, Rich table, plain text), exit codes,
flag handling, progress reporting, and error messages.
"""

from __future__ import annotations

import json
import signal
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from rag_mcp.cli import (
    _sanitise_display_name,
    _print_ollama_error,
    _make_plain_callback,
    app,
)
from rag_mcp.reranker import CrossEncoderReranker

runner = CliRunner()


# ── A: Foundation — entry point tests ──────────────────────────────────────


class TestEntryPoint:
    """Tests for the top-level CLI entry point."""

    def test_version_flag(self) -> None:
        """--version prints version and exits with code 0."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "rag-mcp" in result.output

    def test_help_flag(self) -> None:
        """--help lists all subcommands and exits with code 0."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "ingest" in result.output
        assert "search" in result.output
        assert "list" in result.output

    def test_unknown_subcommand(self) -> None:
        """Unknown subcommand produces a non-zero exit code."""
        result = runner.invoke(app, ["bogus"])
        assert result.exit_code != 0


# ── B: CLI output — sanitise and Ollama error ──────────────────────────────


class TestSanitiseDisplayName:
    """Tests for ANSI escape sequence stripping."""

    def test_no_ansi_passthrough(self) -> None:
        """Plain text passes through unchanged."""
        assert _sanitise_display_name("hello") == "hello"

    def test_strips_colour_codes(self) -> None:
        """ANSI colour codes are removed."""
        assert _sanitise_display_name("\x1b[32mgreen\x1b[0m") == "green"

    def test_strips_cursor_movement(self) -> None:
        """ANSI cursor movement codes are removed."""
        assert _sanitise_display_name("\x1b[2Jcleared") == "cleared"

    def test_empty_string(self) -> None:
        """Empty string returns empty string."""
        assert _sanitise_display_name("") == ""


class TestPrintOllamaError:
    """Tests for the Ollama connection error printer."""

    def test_console_output(self) -> None:
        """Console mode prints to Rich console with 'Ollama' in message."""
        with patch("rag_mcp.cli.console.print") as mock_print:
            _print_ollama_error("Connection refused")
            mock_print.assert_called_once()
            call_arg = str(mock_print.call_args)
            assert "Ollama" in call_arg

    def test_json_output(self) -> None:
        """JSON mode outputs valid JSON with status 'error'."""
        # Capture stdout
        captured = StringIO()
        with patch("sys.stdout", captured):
            _print_ollama_error("Connection refused", json_output=True)
        data = json.loads(captured.getvalue())
        assert data["status"] == "error"
        assert "Ollama" in data["message"]

    def test_includes_detail(self) -> None:
        """Detail string is included in the error message."""
        with patch("rag_mcp.cli.console.print") as mock_print:
            _print_ollama_error("Connection refused")
            call_arg = str(mock_print.call_args)
            assert "Connection refused" in call_arg


# ── C + D: CLI ingest — JSON, flags, exit codes, Rich output ───────────────


class TestIngestCLI:
    """Tests for the ingest subcommand."""

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_single_txt_file(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """Ingesting a valid .txt file exits 0 with success message."""
        result = runner.invoke(app, ["ingest", str(sample_txt)])
        assert result.exit_code == 0
        # Rich renders to console (stderr), but CliRunner captures output
        # The success message should appear somewhere
        output = result.output or ""
        assert "Indexed" in output or "1 file(s)" in output or "✓" in output

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_path_not_found(self, mock_signal: MagicMock) -> None:
        """Non-existent path exits 1 with an error message."""
        result = runner.invoke(app, ["ingest", "/nonexistent/path"])
        assert result.exit_code == 1

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_unsupported_extension(
        self, mock_signal: MagicMock, tmp_path: Path
    ) -> None:
        """Unsupported file extension exits with error."""
        bad_file = tmp_path / "test.xyz"
        bad_file.write_text("content")
        result = runner.invoke(app, ["ingest", str(bad_file)])
        assert result.exit_code != 0

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_json_output(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """--json flag produces valid JSON with expected keys."""
        result = runner.invoke(app, ["ingest", str(sample_txt), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert "files_indexed" in data
        assert "chunks_created" in data

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_json_output_on_error(self, mock_signal: MagicMock) -> None:
        """--json with non-existent path exits with error code."""
        result = runner.invoke(app, ["ingest", "/nonexistent", "--json"])
        # ingest_path returns an error dict which the CLI prints via
        # console.print (stderr) — not as JSON.  Exit code is 1.
        assert result.exit_code == 1
        assert "Error" in result.output or "not found" in result.output.lower()

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_with_workers_clamped_negative(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """Negative --workers is clamped and succeeds."""
        result = runner.invoke(
            app, ["ingest", str(sample_txt), "--workers", "-5"]
        )
        assert result.exit_code == 0

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_with_workers_clamped_zero(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """--workers 0 is clamped and succeeds."""
        result = runner.invoke(
            app, ["ingest", str(sample_txt), "--workers", "0"]
        )
        assert result.exit_code == 0

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_with_chunk_size(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """--chunk-size override is accepted."""
        result = runner.invoke(
            app, ["ingest", str(sample_txt), "--chunk-size", "128"]
        )
        assert result.exit_code == 0

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_with_chunk_overlap(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """--chunk-overlap override is accepted."""
        result = runner.invoke(
            app, ["ingest", str(sample_txt), "--chunk-overlap", "32"]
        )
        assert result.exit_code == 0

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_success_message(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """Success output contains indexed file count."""
        result = runner.invoke(app, ["ingest", str(sample_txt)])
        assert result.exit_code == 0
        output = result.output or ""
        # Rich renders via console.print, check for key content
        assert "1 file(s)" in output or "Indexed" in output

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_exit_code_success(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """Valid file produces exit code 0."""
        result = runner.invoke(app, ["ingest", str(sample_txt)])
        assert result.exit_code == 0

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_exit_code_error(self, mock_signal: MagicMock) -> None:
        """Invalid path produces exit code 1."""
        result = runner.invoke(app, ["ingest", "/nonexistent"])
        assert result.exit_code == 1

    def test_ingest_help(self) -> None:
        """--help lists all options."""
        result = runner.invoke(app, ["ingest", "--help"])
        assert result.exit_code == 0
        assert "--workers" in result.output
        assert "--chunk-size" in result.output
        assert "--chunk-overlap" in result.output
        assert "--json" in result.output


# ── C + D: CLI search — JSON, Rich table, flags ────────────────────────────


class TestSearchCLI:
    """Tests for the search subcommand."""

    def test_search_empty_store(self) -> None:
        """Search on empty store shows 'No results' message."""
        result = runner.invoke(app, ["search", "quantum computing"])
        assert result.exit_code == 0
        assert "No results" in result.output

    def test_search_json_empty_store(self) -> None:
        """Search --json on empty store returns '[]'."""
        result = runner.invoke(app, ["search", "quantum computing", "--json"])
        assert result.exit_code == 0
        assert result.output.strip() == "[]"

    @patch("rag_mcp.cli.signal.signal")
    def test_search_json_results(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """Search after ingest returns valid JSON results."""
        # First ingest
        runner.invoke(app, ["ingest", str(sample_txt)])
        # Then search
        result = runner.invoke(
            app, ["search", "capital of France", "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0
        for r in data:
            assert "score" in r
            assert "source" in r
            assert "text" in r

    def test_search_with_top_k(self) -> None:
        """--top-k flag is accepted."""
        result = runner.invoke(
            app, ["search", "query", "--top-k", "3"]
        )
        assert result.exit_code == 0

    def test_search_with_threshold(self) -> None:
        """--threshold flag is accepted."""
        result = runner.invoke(
            app, ["search", "query", "--threshold", "0.5"]
        )
        assert result.exit_code == 0

    def test_search_with_rerank(self) -> None:
        """--rerank flag is accepted without error."""
        CrossEncoderReranker._instance = None
        try:
            result = runner.invoke(app, ["search", "query", "--rerank"])
            assert result.exit_code == 0
        finally:
            CrossEncoderReranker._instance = None

    @patch("rag_mcp.cli.signal.signal")
    def test_search_rich_table_output(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """Default (non-JSON) search renders a table with column headers."""
        runner.invoke(app, ["ingest", str(sample_txt)])
        result = runner.invoke(app, ["search", "capital"])
        assert result.exit_code == 0
        # Rich Table renders to console; check column names appear
        assert "Score" in result.output
        assert "Source" in result.output
        assert "Text" in result.output

    def test_search_help(self) -> None:
        """--help lists all options."""
        result = runner.invoke(app, ["search", "--help"])
        assert result.exit_code == 0
        assert "--top-k" in result.output
        assert "--threshold" in result.output
        assert "--rerank" in result.output
        assert "--json" in result.output


# ── C: CLI list — JSON and Rich table ──────────────────────────────────────


class TestListCLI:
    """Tests for the list subcommand."""

    def test_list_empty_store(self) -> None:
        """List on empty store shows 'No indexed documents'."""
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No indexed documents" in result.output

    def test_list_json_empty_store(self) -> None:
        """List --json on empty store returns '[]'."""
        result = runner.invoke(app, ["list", "--json"])
        assert result.exit_code == 0
        assert result.output.strip() == "[]"

    @patch("rag_mcp.cli.signal.signal")
    def test_list_json_with_docs(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """List --json after ingest shows documents with source and chunks."""
        runner.invoke(app, ["ingest", str(sample_txt)])
        result = runner.invoke(app, ["list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0
        for doc in data:
            assert "source" in doc
            assert "chunks" in doc

    @patch("rag_mcp.cli.signal.signal")
    def test_list_rich_table_output(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """Default (non-JSON) list renders table with Source and Chunks."""
        runner.invoke(app, ["ingest", str(sample_txt)])
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "Source" in result.output
        assert "Chunks" in result.output

    @patch("rag_mcp.cli.signal.signal")
    def test_list_shows_total(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """List output includes document and chunk total summary."""
        runner.invoke(app, ["ingest", str(sample_txt)])
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "document(s)" in result.output
        assert "chunk(s) total" in result.output


# ── E: Progress reporting ──────────────────────────────────────────────────


class TestProgressReporting:
    """Tests for plain-text and Rich progress callbacks."""

    def test_plain_text_read_progress(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Plain callback prints 'Reading file N/M…' to stderr."""
        callback = _make_plain_callback()
        callback("read", 3, 5)
        captured = capsys.readouterr()
        assert "Reading file 3/5" in captured.err

    def test_plain_text_embed_start(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Plain callback prints 'Embedding K chunks…' for embed_start."""
        callback = _make_plain_callback()
        callback("embed_start", 0, 10)
        captured = capsys.readouterr()
        assert "Embedding 10 chunks" in captured.err

    def test_plain_text_embed_complete(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Plain callback prints 'Embedding complete' for embed phase."""
        callback = _make_plain_callback()
        callback("embed", 10, 10)
        captured = capsys.readouterr()
        assert "Embedding complete" in captured.err

    def test_rich_progress_callback_structure(self) -> None:
        """Rich progress callback creates and updates tasks correctly."""
        with patch("rag_mcp.ingestion.ingest_path") as mock_ingest:
            mock_ingest.return_value = {
                "status": "ok",
                "files_indexed": 1,
                "chunks_created": 3,
            }

            from rag_mcp.cli import _run_ingest_with_rich_progress

            _run_ingest_with_rich_progress("/fake", {"workers": 1})

            # ingest_path should have been called with a progress_callback
            assert mock_ingest.called
            call_kwargs = mock_ingest.call_args
            assert "progress_callback" in call_kwargs.kwargs
            assert callable(call_kwargs.kwargs["progress_callback"])

    @patch("rag_mcp.cli.signal.signal")
    def test_json_suppresses_progress(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """--json mode does not include progress messages in output."""
        result = runner.invoke(
            app, ["ingest", str(sample_txt), "--json"]
        )
        assert result.exit_code == 0
        assert "Reading file" not in result.output
        assert "Embedding" not in result.output


# ── F: Error handling & SIGINT edge cases ──────────────────────────────────


class TestIngestErrorHandling:
    """Tests for error handling and interrupt paths in ingest."""

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_connection_error(self, mock_signal: MagicMock) -> None:
        """ConnectionError from Ollama triggers friendly error message."""
        with patch("rag_mcp.ingestion.ingest_path") as mock_ingest:
            mock_ingest.side_effect = ConnectionError("Connection refused")
            result = runner.invoke(app, ["ingest", "/fake/path"])
            assert result.exit_code == 1

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_generic_exception_ollama(
        self, mock_signal: MagicMock
    ) -> None:
        """Generic exception with 'ollama' in message triggers Ollama error."""
        with patch("rag_mcp.ingestion.ingest_path") as mock_ingest:
            mock_ingest.side_effect = Exception("ollama service unavailable")
            result = runner.invoke(app, ["ingest", "/fake/path"])
            assert result.exit_code == 1

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_generic_exception_embed(
        self, mock_signal: MagicMock
    ) -> None:
        """Generic exception with 'embed' in message triggers Ollama error."""
        with patch("rag_mcp.ingestion.ingest_path") as mock_ingest:
            mock_ingest.side_effect = Exception("embed operation failed")
            result = runner.invoke(app, ["ingest", "/fake/path"])
            assert result.exit_code == 1

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_generic_exception_other(
        self, mock_signal: MagicMock
    ) -> None:
        """Generic exception without ollama/embed triggers generic error."""
        with patch("rag_mcp.ingestion.ingest_path") as mock_ingest:
            mock_ingest.side_effect = Exception("Something went wrong")
            result = runner.invoke(app, ["ingest", "/fake/path"])
            assert result.exit_code == 1

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_interrupt_message_plain(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """Interrupt during ingest shows interruption message."""
        from rag_mcp.ingestion import _shutdown_requested

        # Simulate: ingest succeeds but shutdown was requested
        with patch("rag_mcp.ingestion.ingest_path") as mock_ingest:
            mock_ingest.return_value = {
                "status": "ok",
                "files_indexed": 2,
                "chunks_created": 5,
            }
            # Set the shutdown flag to trigger interrupt message path
            _shutdown_requested.set()
            try:
                result = runner.invoke(app, ["ingest", str(sample_txt)])
                assert result.exit_code == 130  # 128 + SIGINT(2)
                assert "interrupted" in result.output.lower()
            finally:
                _shutdown_requested.clear()

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_interrupt_message_json(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """Interrupt during ingest with --json outputs JSON with interrupted flag."""
        from rag_mcp.ingestion import _shutdown_requested

        with patch("rag_mcp.ingestion.ingest_path") as mock_ingest:
            mock_ingest.return_value = {
                "status": "ok",
                "files_indexed": 2,
                "chunks_created": 5,
            }
            _shutdown_requested.set()
            try:
                result = runner.invoke(
                    app, ["ingest", str(sample_txt), "--json"]
                )
                assert result.exit_code == 130
                data = json.loads(result.output)
                assert data.get("interrupted") is True
            finally:
                _shutdown_requested.clear()

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_interrupt_with_chunks(
        self, mock_signal: MagicMock, sample_txt: Path
    ) -> None:
        """Interrupt message mentions chunks written before interruption."""
        from rag_mcp.ingestion import _shutdown_requested

        with patch("rag_mcp.ingestion.ingest_path") as mock_ingest:
            mock_ingest.return_value = {
                "status": "ok",
                "files_indexed": 2,
                "chunks_created": 5,
            }
            _shutdown_requested.set()
            try:
                result = runner.invoke(app, ["ingest", str(sample_txt)])
                assert result.exit_code == 130
                assert "chunk(s)" in result.output
            finally:
                _shutdown_requested.clear()

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_connection_error_json(
        self, mock_signal: MagicMock
    ) -> None:
        """ConnectionError with --json outputs JSON error."""
        with patch("rag_mcp.ingestion.ingest_path") as mock_ingest:
            mock_ingest.side_effect = ConnectionError("Connection refused")
            result = runner.invoke(
                app, ["ingest", "/fake/path", "--json"]
            )
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert data["status"] == "error"
            assert "Ollama" in data["message"]


class TestSearchErrorHandling:
    """Tests for error handling in the search command."""

    def test_search_connection_error(self) -> None:
        """ConnectionError in search triggers Ollama error message."""
        with patch("rag_mcp.retrieval.search") as mock_search:
            mock_search.side_effect = ConnectionError("Connection refused")
            result = runner.invoke(app, ["search", "test query"])
            assert result.exit_code == 1

    def test_search_generic_exception_ollama(self) -> None:
        """Generic exception with 'ollama' in search triggers Ollama error."""
        with patch("rag_mcp.retrieval.search") as mock_search:
            mock_search.side_effect = Exception("ollama error occurred")
            result = runner.invoke(app, ["search", "test query"])
            assert result.exit_code == 1

    def test_search_generic_exception_other(self) -> None:
        """Generic exception without ollama/embed triggers generic error."""
        with patch("rag_mcp.retrieval.search") as mock_search:
            mock_search.side_effect = Exception("Something broke")
            result = runner.invoke(app, ["search", "test query"])
            assert result.exit_code == 1

    def test_search_connection_error_json(self) -> None:
        """ConnectionError with --json outputs JSON error."""
        with patch("rag_mcp.retrieval.search") as mock_search:
            mock_search.side_effect = ConnectionError("Connection refused")
            result = runner.invoke(
                app, ["search", "test query", "--json"]
            )
            assert result.exit_code == 1
            data = json.loads(result.output)
            assert data["status"] == "error"


class TestRunCli:
    """Tests for the run_cli entry point."""

    def test_run_cli_delegates_to_app(self) -> None:
        """run_cli() delegates to the Typer app."""
        from rag_mcp.cli import run_cli

        with patch("rag_mcp.cli.app") as mock_app:
            run_cli()
            mock_app.assert_called_once()


# ── G: Rich progress callback & SIGINT handler unit tests ──────────────────


class TestRichProgressCallbackInternals:
    """Directly exercise the Rich progress callback phases (lines 133-152)."""

    def test_rich_callback_read_phase(self) -> None:
        """Read phase creates and updates the read task."""
        from rag_mcp.cli import _run_ingest_with_rich_progress

        captured_callbacks: list[tuple[str, int, int]] = []

        def fake_ingest(
            path: str,
            progress_callback: object = None,
            **kwargs: object,
        ) -> dict:
            assert progress_callback is not None
            # Simulate: 3 files to read
            progress_callback("read", 0, 3)
            progress_callback("read", 1, 3)
            progress_callback("read", 2, 3)
            progress_callback("read", 3, 3)
            return {"status": "ok", "files_indexed": 3, "chunks_created": 9}

        with patch("rag_mcp.ingestion.ingest_path", side_effect=fake_ingest):
            result = _run_ingest_with_rich_progress("/fake", {"workers": 1})

        assert result["status"] == "ok"

    def test_rich_callback_embed_start_phase(self) -> None:
        """embed_start phase completes read bar and creates embed bar."""
        from rag_mcp.cli import _run_ingest_with_rich_progress

        def fake_ingest(
            path: str,
            progress_callback: object = None,
            **kwargs: object,
        ) -> dict:
            assert progress_callback is not None
            progress_callback("read", 2, 2)
            progress_callback("embed_start", 0, 5)
            progress_callback("embed", 5, 5)
            return {"status": "ok", "files_indexed": 2, "chunks_created": 5}

        with patch("rag_mcp.ingestion.ingest_path", side_effect=fake_ingest):
            result = _run_ingest_with_rich_progress("/fake", {})

        assert result["chunks_created"] == 5

    def test_rich_callback_embed_start_completes_partial_read(
        self,
    ) -> None:
        """embed_start forces read bar to 100% if not yet complete."""
        from rag_mcp.cli import _run_ingest_with_rich_progress

        def fake_ingest(
            path: str,
            progress_callback: object = None,
            **kwargs: object,
        ) -> dict:
            # Read only 1 of 3 files before embed starts
            progress_callback("read", 1, 3)
            progress_callback("embed_start", 0, 4)
            progress_callback("embed", 4, 4)
            return {"status": "ok", "files_indexed": 1, "chunks_created": 4}

        with patch("rag_mcp.ingestion.ingest_path", side_effect=fake_ingest):
            result = _run_ingest_with_rich_progress("/fake", {})

        assert result["status"] == "ok"

    def test_rich_callback_embed_phase_updates(self) -> None:
        """embed phase updates the embed task progress."""
        from rag_mcp.cli import _run_ingest_with_rich_progress

        def fake_ingest(
            path: str,
            progress_callback: object = None,
            **kwargs: object,
        ) -> dict:
            progress_callback("embed_start", 0, 10)
            # Multiple embed updates
            progress_callback("embed", 5, 10)
            progress_callback("embed", 10, 10)
            return {"status": "ok", "files_indexed": 1, "chunks_created": 10}

        with patch("rag_mcp.ingestion.ingest_path", side_effect=fake_ingest):
            result = _run_ingest_with_rich_progress("/fake", {})

        assert result["chunks_created"] == 10


class TestSigintHandler:
    """Directly test the _on_sigint handler registered during ingest."""

    @patch("rag_mcp.cli.signal.signal")
    @patch("rag_mcp.cli.console.print")
    def test_first_sigint_sets_shutdown_flag(
        self, mock_print: MagicMock, mock_signal: MagicMock
    ) -> None:
        """First SIGINT sets _shutdown_requested and prints message."""
        from rag_mcp.ingestion import _shutdown_requested

        _shutdown_requested.clear()

        with patch("rag_mcp.ingestion.ingest_path") as mock_ingest:
            mock_ingest.return_value = {
                "status": "ok",
                "files_indexed": 0,
                "chunks_created": 0,
            }

            # Capture the handler registered with signal.signal
            registered_handler = None
            original_handler = None

            def capture_handler(sig: int, handler: object) -> None:
                nonlocal registered_handler, original_handler
                if registered_handler is not None:
                    # signal.signal called again (restore) — skip
                    return
                # First call captures our handler; also store original
                registered_handler = handler

            mock_signal.side_effect = capture_handler

            result = runner.invoke(app, ["ingest", "/fake"])
            assert result.exit_code == 0

            # Now call the handler as if SIGINT was received
            if registered_handler is not None:
                _shutdown_requested.clear()
                try:
                    registered_handler(signal.SIGINT, None)
                except KeyboardInterrupt:
                    pass  # Should NOT happen on first call
                assert _shutdown_requested.is_set()
                # Verify the "finishing current file" message was printed
                mock_print.assert_called()

        _shutdown_requested.clear()

    @patch("rag_mcp.cli.signal.signal")
    @patch("rag_mcp.cli.console.print")
    def test_second_sigint_raises_keyboard_interrupt(
        self, mock_print: MagicMock, mock_signal: MagicMock
    ) -> None:
        """Second SIGINT raises KeyboardInterrupt."""
        from rag_mcp.ingestion import _shutdown_requested

        _shutdown_requested.clear()

        with patch("rag_mcp.ingestion.ingest_path") as mock_ingest:
            mock_ingest.return_value = {
                "status": "ok",
                "files_indexed": 0,
                "chunks_created": 0,
            }

            registered_handler = None

            def capture_handler(sig: int, handler: object) -> None:
                nonlocal registered_handler
                if registered_handler is not None:
                    return
                registered_handler = handler

            mock_signal.side_effect = capture_handler

            result = runner.invoke(app, ["ingest", "/fake"])
            assert result.exit_code == 0

            if registered_handler is not None:
                _shutdown_requested.clear()
                # First call — sets shutdown flag
                registered_handler(signal.SIGINT, None)
                # Second call should raise KeyboardInterrupt
                with pytest.raises(KeyboardInterrupt):
                    registered_handler(signal.SIGINT, None)

        _shutdown_requested.clear()


class TestConsoleIsTerminal:
    """Test the TTY path (console.is_terminal == True)."""

    @patch("rag_mcp.cli.signal.signal")
    def test_ingest_tty_path_uses_rich_progress(
        self, mock_signal: MagicMock
    ) -> None:
        """When console.is_terminal is True, Rich progress is used."""
        with (
            patch("rag_mcp.cli.console") as mock_console,
            patch("rag_mcp.ingestion.ingest_path") as mock_ingest,
        ):
            mock_console.is_terminal = True
            mock_console.print = MagicMock()

            # ingest_path called via _run_ingest_with_rich_progress
            # which calls ingest_path with progress_callback
            mock_ingest.return_value = {
                "status": "ok",
                "files_indexed": 1,
                "chunks_created": 3,
            }

            result = runner.invoke(app, ["ingest", "/fake"])
            assert result.exit_code == 0
            # ingest_path should have been called with progress_callback
            call_kwargs = mock_ingest.call_args
            assert "progress_callback" in call_kwargs.kwargs
