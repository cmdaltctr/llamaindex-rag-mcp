"""Profile-scoped ingestible extensions (fix-embedding-and-structure-fidelity-1).

Spec: openspec/changes/fix-embedding-and-structure-fidelity-1/specs/
type-aware-ingestion/spec.md — "The ingestible extension set is
profile-scoped".

The set of file extensions ingestion collects resolves from the active
profile rather than one global constant, so ``codebase.yaml``'s
``chunking.strategy_fallback: code`` becomes reachable for real source
files while the documents profile keeps collecting only the seven
document extensions. Coverage drives the REAL extension gate — nothing
patches ``gather_supported_files`` (spec scenario "Coverage exercises
the real gate").
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

_DOCUMENT_EXTENSIONS = (".pdf", ".docx", ".pptx", ".txt", ".md", ".html", ".csv")


def _profile_settings(effective_settings, profile: str):
    """Resolve a real profile bundle onto a test-safe base.

    Uses the production :class:`ProfileResolver` and the real
    ``config/profiles/<name>.yaml`` bundle — the same path production
    takes — with a base that pins ``extraction_mode="disabled"`` so no
    test performs real LLM calls (conftest docstring).
    """
    from rag_mcp.core.profiles.resolver import ProfileResolver

    base = effective_settings(extraction_mode="disabled")
    return ProfileResolver(server_profile="documents", base=base)._load_effective(profile)


def _source_dir(tmp_path: Path) -> Path:
    """Create a directory holding the spec's `.py`, `.ts`, `.go` trio plus a doc."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(
        "def greet(name: str) -> str:\n"
        "    '''Return a greeting.'''\n"
        "    return f'hello {name}'\n"
        "\n"
        "\n"
        "def depart(name: str) -> str:\n"
        "    '''Return a farewell.'''\n"
        "    return f'bye {name}'\n",
        encoding="utf-8",
    )
    (src / "service.ts").write_text(
        "export function greet(name: string): string {\n"
        "  return `hello ${name}`;\n"
        "}\n"
        "\n"
        "export function depart(name: string): string {\n"
        "  return `bye ${name}`;\n"
        "}\n",
        encoding="utf-8",
    )
    (src / "main.go").write_text(
        'package main\n\nimport "fmt"\n\nfunc main() {\n\tfmt.Println("hello")\n}\n',
        encoding="utf-8",
    )
    (src / "notes.md").write_text("# Notes\n\nA markdown document.\n", encoding="utf-8")
    return src


# ── Task 1.5 / 7.5: the codebase profile admits source files ──────────


class TestCodebaseProfileAdmitsSourceFiles:
    """Source files reach the AST-aware code strategy through the real gate."""

    async def test_real_py_file_reaches_code_strategy(
        self, effective_settings, tmp_path: Path
    ) -> None:
        """Task 1.5 — a real .py through ingest_path_async, no gate patching.

        Spec scenario "Coverage exercises the real gate": drive a real
        source file through the real extension gate and assert
        ``effective_strategy == "code"``.
        """
        from rag_mcp.core.ingestion import ingest_path_async

        src = _source_dir(tmp_path)
        settings = _profile_settings(effective_settings, "codebase")

        result = await ingest_path_async(
            str(src / "app.py"),
            collection_name="codebase_gate_py",
            effective_settings=settings,
        )

        assert result["status"] == "ok", result
        indexed = [d for d in result["file_details"] if d.get("status") == "indexed"]
        assert len(indexed) == 1, result["file_details"]
        assert indexed[0]["file"] == "app.py"
        assert indexed[0].get("effective_strategy") == "code", indexed[0]

    async def test_directory_sources_collected_and_code_chunked(
        self, effective_settings, tmp_path: Path
    ) -> None:
        """Spec scenario "The codebase profile admits source files".

        GIVEN a directory containing .py, .ts and .go files, ingesting
        under the codebase profile collects them, and files with a
        tree-sitter mapping are chunked by the AST-aware code strategy.
        """
        from rag_mcp.core.ingestion import ingest_path_async

        src = _source_dir(tmp_path)
        settings = _profile_settings(effective_settings, "codebase")

        result = await ingest_path_async(
            str(src), collection_name="codebase_gate_dir", effective_settings=settings
        )

        assert result["status"] == "ok", result
        indexed = {d["file"]: d for d in result["file_details"] if d.get("status") == "indexed"}
        assert {"app.py", "service.ts", "main.go", "notes.md"} <= set(indexed), result[
            "file_details"
        ]
        for name in ("app.py", "service.ts", "main.go"):
            assert indexed[name].get("effective_strategy") == "code", indexed[name]

    async def test_stored_chunks_carry_code_content_type(
        self, effective_settings, tmp_path: Path
    ) -> None:
        """The typed metadata parity holds on the code path too."""
        from rag_mcp.core.ingestion import ingest_path_async
        from rag_mcp.core.vectordb import get_default_store

        src = _source_dir(tmp_path)
        settings = _profile_settings(effective_settings, "codebase")

        result = await ingest_path_async(
            str(src), collection_name="codebase_gate_meta", effective_settings=settings
        )
        assert result["status"] == "ok", result

        payload = get_default_store().fetch_all("codebase_gate_meta", ["metadatas"])
        assert payload
        types = {m.get("content_type") for m in payload["metadatas"]}
        assert "code/python" in types, types


# ── Task 7.5: the documents profile is unchanged ───────────────────────


class TestDocumentsProfileUnchanged:
    """Only the seven document extensions are collected under documents."""

    async def test_source_files_skipped_with_explicit_reason(
        self, effective_settings, tmp_path: Path
    ) -> None:
        """Spec scenario "The documents profile is unchanged".

        The source files are reported ``status: "skipped"`` with an
        explicit reason, exactly as before this change.
        """
        from rag_mcp.core.ingestion import ingest_path_async

        src = _source_dir(tmp_path)
        settings = _profile_settings(effective_settings, "documents")

        result = await ingest_path_async(
            str(src), collection_name="documents_gate", effective_settings=settings
        )

        assert result["status"] == "ok", result
        skipped = {d["file"]: d for d in result["file_details"] if d.get("status") == "skipped"}
        for name in ("app.py", "service.ts", "main.go"):
            assert name in skipped, result["file_details"]
            reason = skipped[name].get("error", "")
            assert reason, f"{name} skipped without an explicit reason"
            assert "extension" in reason.lower()

    async def test_single_source_file_rejected_with_extension_error(
        self, effective_settings, tmp_path: Path
    ) -> None:
        """A single .py handed to a documents-profile ingest fails loudly."""
        from rag_mcp.core.ingestion import ingest_path_async

        src = _source_dir(tmp_path)
        settings = _profile_settings(effective_settings, "documents")

        result = await ingest_path_async(
            str(src / "app.py"),
            collection_name="documents_gate_single",
            effective_settings=settings,
        )

        assert result["status"] == "error", result
        assert "Unsupported file extension" in result["message"]


# ── Binary exclusion under every profile ───────────────────────────────


class TestBinaryExcludedUnderEveryProfile:
    """Binary files are skipped regardless of the profile's extension set."""

    @staticmethod
    def _binary_inventory(entries: list[tuple[str, str, str, str]]):
        """A detect_file_types inventory from ``(name, group, label, suffix)`` rows.

        Exactly one row must be binary; the pipeline's binary skip keys on
        the ``binary/`` group prefix of the emitted content type.
        """
        from rag_mcp.core.codebase.codebase_map import FileEntry, FileInventory

        file_entries = [
            FileEntry(name, group, label, not group.startswith("binary"), suffix)
            for name, group, label, suffix in entries
        ]
        return FileInventory(
            entries=file_entries,
            type_counts={f"{e[1]}/{e[2]}": 1 for e in entries},
            binary_files=[e[0] for e in entries if e[1].startswith("binary")],
        )

    async def test_binary_skipped_under_codebase_profile(
        self, effective_settings, tmp_path: Path
    ) -> None:
        """Admitted by the extension set, rejected by content-type detection."""
        from rag_mcp.core.ingestion import ingest_path_async

        src = _source_dir(tmp_path)
        (src / "blob.py").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        settings = _profile_settings(effective_settings, "codebase")

        with (
            patch("rag_mcp.integrations.magika._is_magika_available", return_value=False),
            patch(
                "rag_mcp.core.codebase.codebase_map.detect_file_types",
                return_value=self._binary_inventory(
                    [
                        ("app.py", "code", "python", ".py"),
                        ("blob.py", "binary", "png", ".py"),
                    ]
                ),
            ),
        ):
            result = await ingest_path_async(
                str(src), collection_name="codebase_binary", effective_settings=settings
            )

        skipped = [d for d in result["file_details"] if d.get("status") == "skipped"]
        assert any(d["file"] == "blob.py" for d in skipped), result["file_details"]
        indexed = {d["file"] for d in result["file_details"] if d.get("status") == "indexed"}
        assert "app.py" in indexed
        assert "blob.py" not in indexed

    async def test_binary_skipped_under_documents_profile(
        self, effective_settings, tmp_path: Path
    ) -> None:
        """The default seven stay binary-guarded too (a renamed blob)."""
        from rag_mcp.core.ingestion import ingest_path_async

        src = _source_dir(tmp_path)
        (src / "photo.txt").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
        settings = _profile_settings(effective_settings, "documents")

        with (
            patch("rag_mcp.integrations.magika._is_magika_available", return_value=False),
            patch(
                "rag_mcp.core.codebase.codebase_map.detect_file_types",
                return_value=self._binary_inventory(
                    [
                        ("notes.md", "document", "markdown", ".md"),
                        ("photo.txt", "binary", "png", ".txt"),
                    ]
                ),
            ),
        ):
            result = await ingest_path_async(
                str(src), collection_name="documents_binary", effective_settings=settings
            )

        skipped = {d["file"] for d in result["file_details"] if d.get("status") == "skipped"}
        assert "photo.txt" in skipped, result["file_details"]
        indexed = {d["file"] for d in result["file_details"] if d.get("status") == "indexed"}
        assert "notes.md" in indexed
        assert "photo.txt" not in indexed


# ── Extension-set change detection ────────────────────────────────────


class TestExtensionSetChangeDetection:
    """The set admits files; it must not reprocess the already-indexed."""

    def test_identity_ignores_the_extension_set(self, effective_settings) -> None:
        """Spec scenario "The extension set participates in change detection".

        Changing only the set must not change ``source_index_identity`` —
        otherwise every still-admitted file would be reprocessed solely
        because the set changed.
        """
        from rag_mcp.core.ingestion.source_state import build_index_identity

        narrow = effective_settings(ingest_extensions=(".md",))
        wide = effective_settings(ingest_extensions=(".md", ".py", ".ts", ".go"))

        identity_narrow = build_index_identity(
            narrow, content_type=None, chunk_size=512, chunk_overlap=100
        )
        identity_wide = build_index_identity(
            wide, content_type=None, chunk_size=512, chunk_overlap=100
        )

        assert identity_narrow == identity_wide

    async def test_newly_admitted_ingested_and_still_admitted_not_reprocessed(
        self, effective_settings, tmp_path: Path
    ) -> None:
        """Widening the set ingests only the newly admitted files.

        Two settings objects differing ONLY in ``ingest_extensions``:
        the second run must index the newly admitted ``.py`` and skip the
        already-indexed ``.md`` as unchanged — never reprocess it.
        """
        from rag_mcp.core.ingestion import ingest_path_async

        src = tmp_path / "mixed"
        src.mkdir()
        (src / "notes.md").write_text("# Notes\n\nStable document body.\n", encoding="utf-8")
        (src / "app.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")

        narrow = effective_settings(extraction_mode="disabled", ingest_extensions=(".md",))
        wide = effective_settings(extraction_mode="disabled", ingest_extensions=(".md", ".py"))

        first = await ingest_path_async(
            str(src), collection_name="change_detect", effective_settings=narrow
        )
        assert first["status"] == "ok", first
        assert {d["file"] for d in first["file_details"] if d.get("status") == "indexed"} == {
            "notes.md"
        }
        assert any(
            d["file"] == "app.py" and d.get("status") == "skipped" for d in first["file_details"]
        )

        second = await ingest_path_async(
            str(src), collection_name="change_detect", effective_settings=wide
        )
        assert second["status"] == "ok", second
        details = {d["file"]: d for d in second["file_details"]}
        # Newly admitted: ingested.
        assert details["app.py"]["status"] == "indexed", details["app.py"]
        # Already indexed and still admitted: NOT reprocessed solely
        # because the set changed.
        assert details["notes.md"]["status"] == "skipped_unchanged", details["notes.md"]
        assert second["files_indexed"] == 1


# ── Loader threading (task 7.3) ────────────────────────────────────────


class TestLoaderExtensionSet:
    """gather_supported_files reads the resolved set, not a module constant."""

    def test_explicit_set_admits_source_files(self, tmp_path: Path) -> None:
        """A source extension set collects .py files and reports the rest."""
        from rag_mcp.core.ingestion.loader import gather_supported_files

        src = _source_dir(tmp_path)
        files, skipped = gather_supported_files(src, extensions=(".py",))

        assert [f.name for f in files] == ["app.py"]
        assert {s["file"] for s in skipped} == {"service.ts", "main.go", "notes.md"}
        assert all("extension" in s.get("error", "").lower() for s in skipped)

    def test_default_set_is_the_document_seven(self, tmp_path: Path) -> None:
        """Without an explicit set the historical seven remain the default."""
        from rag_mcp.core.ingestion.loader import SUPPORTED_EXTENSIONS, gather_supported_files

        assert SUPPORTED_EXTENSIONS == set(_DOCUMENT_EXTENSIONS)

        src = _source_dir(tmp_path)
        files, skipped = gather_supported_files(src)

        assert [f.name for f in files] == ["notes.md"]
        assert len(skipped) == 3

    def test_single_file_gate_honours_the_set(self, tmp_path: Path) -> None:
        """The single-file branch checks the provided set too."""
        from rag_mcp.core.ingestion.loader import gather_supported_files

        py = tmp_path / "app.py"
        py.write_text("x = 1\n", encoding="utf-8")

        files, _ = gather_supported_files(py, extensions=(".py",))
        assert files == [py]

        files, _ = gather_supported_files(py, extensions=(".md",))
        assert files == []


# ── Settings plumbing (task 7.1) ──────────────────────────────────────


class TestIngestExtensionsSettings:
    """The field exists in both twins with the seven as the default."""

    def test_settings_model_default(self) -> None:
        """IngestionSettings defaults to the historical seven."""
        from rag_mcp.core.ingestion.settings import IngestionSettings

        assert IngestionSettings().ingest_extensions == _DOCUMENT_EXTENSIONS

    def test_effective_block_default(self) -> None:
        """IngestionBlock defaults to the same seven (models stay in sync)."""
        from rag_mcp.core.settings import IngestionBlock

        assert IngestionBlock().ingest_extensions == _DOCUMENT_EXTENSIONS

    def test_env_override_comma_separated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """INGESTION__INGEST_EXTENSIONS accepts a plain comma-separated list."""
        from rag_mcp.config import Settings

        monkeypatch.setenv("INGESTION__INGEST_EXTENSIONS", ".py, .ts,.go")
        settings = Settings(_env_file=None)
        assert settings.ingestion.ingest_extensions == (".py", ".ts", ".go")

    def test_env_override_json_array(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A JSON array string also parses (the KEYWORD_RULES precedent)."""
        from rag_mcp.config import Settings

        monkeypatch.setenv("INGESTION__INGEST_EXTENSIONS", '[".pdf", ".txt"]')
        settings = Settings(_env_file=None)
        assert settings.ingestion.ingest_extensions == (".pdf", ".txt")

    def test_normalisation_adds_dots_and_lowercases(self) -> None:
        """Bare extensions and upper case are normalised, never silently kept."""
        from rag_mcp.core.ingestion.settings import IngestionSettings

        parsed = IngestionSettings(ingest_extensions=["py", ".TS", ".Go"])
        assert parsed.ingest_extensions == (".py", ".ts", ".go")


# ── Profile overlay (tasks 7.1/7.2) ───────────────────────────────────


class TestProfileOverlay:
    """The resolver overlays the profile bundle's extension set, env wins."""

    def test_codebase_profile_adds_source_extensions(self, effective_settings) -> None:
        """codebase.yaml's set includes the document seven plus sources."""
        settings = _profile_settings(effective_settings, "codebase")

        assert set(_DOCUMENT_EXTENSIONS) <= set(settings.ingestion.ingest_extensions)
        for ext in (".py", ".ts", ".go"):
            assert ext in settings.ingestion.ingest_extensions, ext

    def test_documents_profile_inherits_the_base(self, effective_settings) -> None:
        """documents.yaml declares no set, so the base default applies."""
        settings = _profile_settings(effective_settings, "documents")

        assert settings.ingestion.ingest_extensions == _DOCUMENT_EXTENSIONS

    def test_env_override_wins_over_the_bundle(self, effective_settings, monkeypatch) -> None:
        """INGESTION__INGEST_EXTENSIONS beats the profile bundle (env-wins)."""
        monkeypatch.setenv("INGESTION__INGEST_EXTENSIONS", ".rs")
        settings = _profile_settings(effective_settings, "codebase")

        assert settings.ingestion.ingest_extensions == (".rs",)

    def test_base_default_flows_through_when_bundle_silent(self, effective_settings) -> None:
        """A custom base default survives profiles that declare no set."""
        base = effective_settings(extraction_mode="disabled", ingest_extensions=(".rst",))
        from rag_mcp.core.profiles.resolver import ProfileResolver

        settings = ProfileResolver(server_profile="documents", base=base)._load_effective(
            "documents"
        )
        assert settings.ingestion.ingest_extensions == (".rst",)


# ── Watcher patterns (task 7.4) ───────────────────────────────────────


class TestWatcherPatterns:
    """Watch patterns build from the resolved set, not a module constant."""

    def test_handler_patterns_from_explicit_set(self) -> None:
        """An explicit extension set drives the watchdog patterns."""
        from rag_mcp.daemon.watcher import DocumentIngestHandler

        handler = DocumentIngestHandler(extensions=(".py", ".go"))

        assert set(handler._patterns) == {"*.py", "*.go"}

    def test_handler_defaults_to_the_constant_set(self) -> None:
        """Without an explicit set the default constant applies."""
        from rag_mcp.daemon.watcher import SUPPORTED_EXTENSIONS, DocumentIngestHandler

        handler = DocumentIngestHandler()

        assert set(handler._patterns) == {f"*{ext}" for ext in SUPPORTED_EXTENSIONS}

    def test_resolve_watch_extensions_uses_the_collection_profile(self, monkeypatch) -> None:
        """The resolver helper reads the collection's profile set."""
        from types import SimpleNamespace

        import rag_mcp.compose as compose_mod
        from rag_mcp.daemon import watcher as watcher_mod

        def _fake_builder():
            def _resolve(collection_name: str):
                return SimpleNamespace(ingestion=SimpleNamespace(ingest_extensions=(".py", ".ts")))

            return SimpleNamespace(resolve=_resolve)

        monkeypatch.setattr(compose_mod, "build_profile_resolver", _fake_builder)

        resolved = watcher_mod.resolve_watch_extensions("code_collection")

        assert resolved == {".py", ".ts"}

    def test_resolve_watch_extensions_falls_back_on_resolver_error(self, monkeypatch) -> None:
        """A failing profile resolution falls back to the default constant."""
        import rag_mcp.compose as compose_mod
        from rag_mcp.daemon import watcher as watcher_mod

        def _boom():
            raise ValueError("bad profile tag")

        monkeypatch.setattr(compose_mod, "build_profile_resolver", _boom)

        resolved = watcher_mod.resolve_watch_extensions("broken")

        assert resolved == set(watcher_mod.SUPPORTED_EXTENSIONS)
