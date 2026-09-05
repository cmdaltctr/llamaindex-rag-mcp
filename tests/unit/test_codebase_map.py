"""Unit tests for codebase_map.py — Magika parsing, suffix fallback, mismatch detection, binary flagging."""  # noqa: E501

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from omrg.core.codebase.codebase_map import (
    CodebaseMap,
    FileEntry,
    FileInventory,
    build_codebase_map,
    detect_file_types,
    format_codebase_map,
    format_inventory,
    scan_with_suffix,
)

# ── Suffix fallback tests ────────────────────────────────────────────────


class TestScanWithSuffix:
    """Tests for suffix-based file detection fallback."""

    def test_python_file_detected(self, tmp_path: Path) -> None:
        """Python files are detected as code/python."""
        (tmp_path / "app.py").write_text("print('hello')")
        entries = scan_with_suffix(str(tmp_path))
        assert len(entries) == 1
        assert entries[0].group == "code"
        assert entries[0].label == "python"
        assert entries[0].is_text is True

    def test_single_file_path_returns_one_entry(self, tmp_path: Path) -> None:
        """A file (not directory) path yields a single entry keyed ``"."``.

        ``ingest_path_async`` may be handed one file directly; it computes
        that file's path relative to itself as ``"."`` and looks the type
        up by that key. The suffix scanner must therefore classify a file
        argument rather than silently returning nothing (its directory
        walk fails with NotADirectoryError, an OSError it swallows).
        """
        f = tmp_path / "app.py"
        f.write_text("print('hello')")
        entries = scan_with_suffix(str(f))
        assert [(e.path, e.group, e.label) for e in entries] == [(".", "code", "python")]

    def test_single_config_file_path_returns_one_entry(self, tmp_path: Path) -> None:
        """A single config file is classified config/<label> with key ``"."``."""
        f = tmp_path / "settings.yaml"
        f.write_text("key: value\n")
        entries = scan_with_suffix(str(f))
        assert len(entries) == 1
        assert entries[0].path == "."
        assert entries[0].group == "config"

    def test_typescript_file_detected(self, tmp_path: Path) -> None:
        """TypeScript files are detected as code/typescript."""
        (tmp_path / "app.ts").write_text("const x = 1;")
        entries = scan_with_suffix(str(tmp_path))
        assert len(entries) == 1
        assert entries[0].group == "code"
        assert entries[0].label == "typescript"

    def test_markdown_file_detected(self, tmp_path: Path) -> None:
        """Markdown files are detected as document/markdown."""
        (tmp_path / "README.md").write_text("# Hello")
        entries = scan_with_suffix(str(tmp_path))
        assert len(entries) == 1
        assert entries[0].group == "document"
        assert entries[0].label == "markdown"

    def test_yaml_config_detected(self, tmp_path: Path) -> None:
        """YAML files are detected as config/yaml."""
        (tmp_path / "config.yaml").write_text("key: value")
        entries = scan_with_suffix(str(tmp_path))
        assert len(entries) == 1
        assert entries[0].group == "config"
        assert entries[0].label == "yaml"

    def test_binary_file_detected(self, tmp_path: Path) -> None:
        """Binary files are flagged as non-text."""
        (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        entries = scan_with_suffix(str(tmp_path))
        assert len(entries) == 1
        assert entries[0].group == "binary"
        assert entries[0].is_text is False

    def test_unknown_extension(self, tmp_path: Path) -> None:
        """Unknown extensions are classified as unknown/text."""
        (tmp_path / "data.xyz").write_text("some content")
        entries = scan_with_suffix(str(tmp_path))
        assert len(entries) == 1
        assert entries[0].group == "unknown"
        assert entries[0].is_text is True

    def test_skips_hidden_directories(self, tmp_path: Path) -> None:
        """Files in .git, __pycache__, node_modules are skipped."""
        (tmp_path / "app.py").write_text("print('hi')")
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "config").write_text("test")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "app.cpython-311.pyc").write_bytes(b"\x00")
        entries = scan_with_suffix(str(tmp_path))
        paths = [e.path for e in entries]
        assert "app.py" in paths
        assert not any(".git" in p for p in paths)
        assert not any("__pycache__" in p for p in paths)

    def test_nested_directories(self, tmp_path: Path) -> None:
        """Files in nested directories are detected with relative paths."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "utils.py").write_text("x = 1")
        entries = scan_with_suffix(str(tmp_path))
        assert len(entries) == 1
        assert entries[0].path == "src/utils.py"


# ── detect_file_types tests ──────────────────────────────────────────────


class TestDetectFileTypes:
    """Tests for the unified detect_file_types function."""

    def test_suffix_fallback_when_magika_unavailable(self, tmp_path: Path) -> None:
        """When Magika is not installed, suffix detection is used."""
        (tmp_path / "app.py").write_text("print('hi')")
        (tmp_path / "README.md").write_text("# Test")
        with patch("omrg.integrations.magika._is_magika_available", return_value=False):
            inventory = detect_file_types(str(tmp_path))
        assert len(inventory.entries) == 2
        assert "code/python" in inventory.type_counts
        assert "document/markdown" in inventory.type_counts

    def test_binary_files_collected(self, tmp_path: Path) -> None:
        """Binary files are collected in the binary_files list."""
        (tmp_path / "app.py").write_text("x = 1")
        (tmp_path / "photo.png").write_bytes(b"\x89PNG")
        with patch("omrg.integrations.magika._is_magika_available", return_value=False):
            inventory = detect_file_types(str(tmp_path))
        assert "photo.png" in inventory.binary_files
        assert "app.py" not in inventory.binary_files

    def test_type_counts_aggregated(self, tmp_path: Path) -> None:
        """Type counts are correctly aggregated."""
        (tmp_path / "a.py").write_text("x = 1")
        (tmp_path / "b.py").write_text("y = 2")
        (tmp_path / "c.ts").write_text("const z = 3;")
        with patch("omrg.integrations.magika._is_magika_available", return_value=False):
            inventory = detect_file_types(str(tmp_path))
        assert inventory.type_counts["code/python"] == 2
        assert inventory.type_counts["code/typescript"] == 1


# ── format_inventory tests ───────────────────────────────────────────────


class TestFormatInventory:
    """Tests for inventory formatting."""

    def test_basic_formatting(self) -> None:
        """Basic inventory formatting includes type counts."""
        inventory = FileInventory(
            entries=[
                FileEntry("app.py", "code", "python", True, ".py"),
                FileEntry("README.md", "document", "markdown", True, ".md"),
            ],
            type_counts={"code/python": 1, "document/markdown": 1},
        )
        text = format_inventory(inventory)
        assert "## File Types" in text
        assert "code/python" in text
        assert "document/markdown" in text

    def test_binary_warning(self) -> None:
        """Binary files produce warning lines."""
        inventory = FileInventory(
            entries=[
                FileEntry("app.py", "code", "python", True, ".py"),
                FileEntry("image.png", "binary", "png", False, ".png"),
            ],
            type_counts={"code/python": 1, "binary/png": 1},
            binary_files=["image.png"],
        )
        text = format_inventory(inventory)
        assert "⚠ BINARY" in text
        assert "image.png" in text

    def test_mismatch_warning(self) -> None:
        """Type mismatches produce warning lines."""
        inventory = FileInventory(
            entries=[
                FileEntry("utils.txt", "code", "javascript", True, ".txt"),
            ],
            type_counts={"code/javascript": 1},
            mismatches=[("utils.txt", "text", "javascript")],
        )
        text = format_inventory(inventory)
        assert "⚠ MISMATCH" in text
        assert "utils.txt" in text
        assert "javascript" in text

    def test_empty_inventory(self) -> None:
        """Empty inventory still produces the header."""
        inventory = FileInventory()
        text = format_inventory(inventory)
        assert "## File Types" in text


# ── format_codebase_map tests ────────────────────────────────────────────


class TestFormatCodebaseMap:
    """Tests for the full codebase map formatting."""

    def test_code_only_map(self) -> None:
        """Map with only code communities omits document sections."""
        m = CodebaseMap(
            inventory=FileInventory(type_counts={"code/python": 3}),
            code_communities=[
                {
                    "label": "Core",
                    "files": ["a.py", "b.py", "c.py"],
                    "file_count": 3,
                    "edge_count": 5,
                },
            ],
        )
        text = format_codebase_map(m)
        assert "## Code Communities" in text
        assert "Core" in text
        assert "## Document Communities" not in text

    def test_community_truncation(self) -> None:
        """Communities with >4 files are truncated."""
        files = [f"file_{i}.py" for i in range(20)]
        m = CodebaseMap(
            inventory=FileInventory(type_counts={"code/python": 20}),
            code_communities=[
                {"label": "Big", "files": files, "file_count": 20, "edge_count": 50},
            ],
        )
        text = format_codebase_map(m)
        assert "... and 16 more" in text

    def test_hubs_section(self) -> None:
        """Hubs section appears when hubs are present."""
        m = CodebaseMap(
            inventory=FileInventory(type_counts={"code/python": 5}),
            hubs=[{"file": "config.py", "in_degree": 14}],
        )
        text = format_codebase_map(m)
        assert "## Architectural Hubs" in text
        assert "config.py" in text
        assert "14" in text

    def test_empty_map(self) -> None:
        """Empty map still produces file types header."""
        m = CodebaseMap()
        text = format_codebase_map(m)
        assert "## File Types" in text


# ── Magika parsing tests (mocked) ────────────────────────────────────────


class TestMagikaParsing:
    """Tests for Magika JSONL output parsing (mocked subprocess)."""

    def test_magika_jsonl_parsing(self, tmp_path: Path) -> None:
        """Magika JSONL output is correctly parsed."""
        (tmp_path / "app.py").write_text("x = 1")
        (tmp_path / "README.md").write_text("# Test")

        mock_output = (
            json.dumps(
                {
                    "path": str(tmp_path / "app.py"),
                    "output": {"group": "code", "label": "python", "is_text": True},
                }
            )
            + "\n"
            + json.dumps(
                {
                    "path": str(tmp_path / "README.md"),
                    "output": {"group": "document", "label": "markdown", "is_text": True},
                }
            )
            + "\n"
        )

        with (
            patch("omrg.integrations.magika._is_magika_available", return_value=True),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
            from omrg.core.codebase.codebase_map import scan_with_magika

            entries = scan_with_magika(str(tmp_path))

        assert len(entries) == 2
        assert entries[0].group == "code"
        assert entries[0].label == "python"
        assert entries[1].group == "document"

    def test_magika_binary_detection(self, tmp_path: Path) -> None:
        """Magika correctly flags binary files."""
        (tmp_path / "app.bin").write_bytes(b"\x00\x01\x02")

        mock_output = (
            json.dumps(
                {
                    "path": str(tmp_path / "app.bin"),
                    "output": {"group": "executable", "label": "elf", "is_text": False},
                }
            )
            + "\n"
        )

        with (
            patch("omrg.integrations.magika._is_magika_available", return_value=True),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(stdout=mock_output, returncode=0)
            from omrg.core.codebase.codebase_map import scan_with_magika

            entries = scan_with_magika(str(tmp_path))

        assert len(entries) == 1
        assert entries[0].is_text is False


# ── build_codebase_map integration tests ─────────────────────────────────


class TestBuildCodebaseMap:
    """Tests for the full build_codebase_map orchestrator."""

    def test_document_graph_receives_collection(self, tmp_path: Path) -> None:
        """build_codebase_map passes a store-backed view to build_document_graph.

        Regression 1: ``build_document_graph(None)`` was once hardcoded, so
        document communities were always empty.
        Regression 2 (ADR-034): the collection used to be opened by
        constructing ``chromadb.PersistentClient`` directly. It now goes
        through the VectorStore ABC, so this asserts on the store — patching
        ``chromadb.PersistentClient`` here would no longer prove anything.
        """
        (tmp_path / "app.py").write_text("x = 1\n")
        (tmp_path / "README.md").write_text("# Test\n")

        mock_store = MagicMock()
        mock_store.count.return_value = 2
        mock_store.fetch_all.return_value = {"ids": [], "embeddings": [], "metadatas": []}

        with (
            patch("omrg.integrations.magika._is_magika_available", return_value=False),
            patch("omrg.core.vectordb.get_default_store", return_value=mock_store),
            patch("omrg.core.documents.doc_graph.build_document_graph") as mock_build_doc,
        ):
            mock_build_doc.return_value = MagicMock()

            build_codebase_map(str(tmp_path))

            mock_build_doc.assert_called()
            view = mock_build_doc.call_args.args[0]
            assert view is not None, "document graph must receive a collection view"
            # The view must read through the store, not a ChromaDB client.
            view.get(include=["metadatas"])
            mock_store.fetch_all.assert_called_with("documents", ["metadatas"])

    def test_no_collection_graceful_degradation(self, tmp_path: Path) -> None:
        """When the vector-store collection is unavailable, code graph still works.

        Task 5.1 rewrite: patches the process-wide store accessor with a
        failing stub instead of ``chromadb.PersistentClient`` so the
        degradation contract is store-agnostic and runs in the base
        install without the chroma extra.
        """

        class _NoCollectionStore:
            def get_collection(self, name: str) -> object:
                raise Exception("no collection")

        (tmp_path / "app.py").write_text("x = 1\n")

        with (
            patch("omrg.integrations.magika._is_magika_available", return_value=False),
            patch(
                "omrg.core.vectordb.get_default_store",
                return_value=_NoCollectionStore(),
            ),
        ):
            result = build_codebase_map(str(tmp_path))

            assert result.inventory is not None
            assert result.doc_communities == []
