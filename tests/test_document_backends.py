"""Document-backend strategy tests (register-document-backend-strategies).

Encodes ``openspec/changes/register-document-backend-strategies/specs/
document-backend-strategies/spec.md`` plus tasks 1.1-1.3:

* Task 1.1 — metadata-parity fixtures pinning CURRENT behaviour: supported
  local file types, the ``file_path``/``content_type`` ingestion fields on
  documents from BOTH backends, and Azure table row-group splitting.
* Task 1.2 — retry budget, missing-credential degradation, missing-SDK
  degradation, and runtime-fallback ownership in the orchestrator.
* Task 1.3 — async responsiveness for both backends (sync work must run
  off the event loop).
* Registry-contract specifics and composition-startup validation gates.

Test-state convention: every NEW-surface import (the
``core.ingestion.backends`` package, ``rag_mcp.capabilities``, the
``read_documents`` adapters) lives INSIDE a test body so this module still
collects before implementation lands. Those tests fail (red) until the
implementation merges; the parity classes pass both before and after.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag_mcp.config import Settings
from rag_mcp.core.ingestion.chunker import read_and_chunk_file_async

# The orchestrator logs under its own module name; diagnostics from the
# config and capabilities layers are captured per-logger below.
_ORCH_LOGGER = "rag_mcp.core.ingestion.backends.orchestrator"
_CONFIG_LOGGER = "rag_mcp.config"
_CAPABILITIES_LOGGER = "rag_mcp.capabilities"


def _azure_sdk_present() -> bool:
    """Whether the optional azure extra is importable in this venv.

    ``find_spec`` raises ModuleNotFoundError when even the parent ``azure``
    namespace package is missing, so the probe is guarded.
    """
    try:
        return importlib.util.find_spec("azure.ai.documentintelligence") is not None
    except (ImportError, ValueError):
        return False


_AZURE_SDK_PRESENT = _azure_sdk_present()


def _write_pdf(tmp_path: Path) -> Path:
    """Create a stub PDF file in *tmp_path* (content is never parsed)."""
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")
    return pdf


def _local_md(tmp_path: Path, word_count: int = 60) -> Path:
    """Write a small markdown document with repeated prose."""
    md = tmp_path / "notes.md"
    md.write_text("# Heading\n\n" + ("prose " * word_count))
    return md


# ── Task 1.1 — metadata parity (pins current behaviour; green today) ────


class TestLocalMetadataParity:
    """The local reading chain exposes the fields ingestion depends on.

    Spec scenario "Local backend is selected": supported documents read
    without cloud credentials. These pins run through today's chunker
    surface so they hold both before and after the orchestrator migration.
    """

    async def test_supported_types_txt_and_md(self, tmp_path: Path, effective_settings) -> None:
        """Plain text and markdown files are readable by the local chain."""
        for name in ("a.txt", "b.md"):
            target = tmp_path / name
            target.write_text("# H\n\n" + ("shared prose. " * 40))
            nodes = await read_and_chunk_file_async(
                target,
                settings=effective_settings(pdf_reader="pypdf", document_backend="local"),
            )
            assert nodes, f"local chain produced no chunks for {name}"

    async def test_local_documents_carry_required_metadata(
        self, tmp_path: Path, effective_settings
    ) -> None:
        """Local-chain documents carry file_path; nodes carry content_type."""
        from llama_index.core import SimpleDirectoryReader

        md = _local_md(tmp_path)
        reader = SimpleDirectoryReader(input_files=[str(md)], filename_as_id=True)
        documents = reader.load_data()
        assert documents
        assert all(str(md) == d.metadata["file_path"] for d in documents)
        assert all(d.get_content().strip() for d in documents)

        settings = effective_settings(
            pdf_reader="pypdf",
            document_backend="local",
            **{"metadata.extraction_mode": "disabled"},
        )
        nodes = await read_and_chunk_file_async(md, content_type="document", settings=settings)
        assert nodes
        assert all(n.metadata.get("content_type") == "document" for n in nodes)


class TestAzureMetadataParity:
    """Azure parsing yields pipeline-compatible metadata (task 1.1)."""

    @staticmethod
    def _mock_result(paragraphs=(), tables=(), content="") -> MagicMock:
        result = MagicMock()
        result.paragraphs = list(paragraphs)
        result.tables = list(tables)
        result.content = content
        return result

    def test_azure_documents_carry_file_path_and_content_type(self, tmp_path: Path) -> None:
        """Spec scenario "Azure backend is selected": metadata stays compatible."""
        from rag_mcp.integrations.azure import parse_azure_response

        paras = [MagicMock(content="Hello world", role="paragraph")]
        documents = parse_azure_response(self._mock_result(paragraphs=paras), tmp_path / "test.pdf")
        assert len(documents) == 1
        assert documents[0].metadata["file_path"] == str(tmp_path / "test.pdf")
        assert "content_type" in documents[0].metadata
        assert documents[0].get_content().strip()

    def test_table_docs_carry_table_index(self, tmp_path: Path) -> None:
        """Table documents expose table_index on top of the required fields."""
        from rag_mcp.integrations.azure import parse_azure_response

        cells = [
            MagicMock(content="A", row_index=0, column_index=0),
            MagicMock(content="B", row_index=0, column_index=1),
        ]
        table = MagicMock(cells=cells, row_count=1, column_count=2)
        documents = parse_azure_response(self._mock_result(tables=[table]), tmp_path / "t.pdf")
        assert len(documents) == 1
        meta = documents[0].metadata
        assert meta["table_index"] == 0
        assert meta["content_type"] == "table"
        assert "row_group" not in meta  # small tables stay whole

    def test_large_tables_split_with_row_group(self, tmp_path: Path) -> None:
        """A >50-row table splits into row groups carrying row_group ids."""
        from rag_mcp.integrations.azure import _split_table_rows, parse_azure_response

        cells = [
            MagicMock(content=f"R{r}C{c}", row_index=r, column_index=c)
            for r in range(120)
            for c in range(2)
        ]
        table = MagicMock(cells=cells, row_count=120, column_count=2)
        documents = parse_azure_response(self._mock_result(tables=[table]), tmp_path / "t.pdf")
        groups = _split_table_rows(table, group_size=50)
        assert len(groups) == 3
        split_meta = [d.metadata for d in documents if d.metadata.get("content_type") == "table"]
        assert sorted(m["row_group"] for m in split_meta) == [0, 1, 2]
        assert all(m["file_path"] == str(tmp_path / "t.pdf") for m in split_meta)

    def test_both_backends_expose_required_ingestion_fields(self, tmp_path: Path) -> None:
        """Parity: azure and local documents both carry file_path and text."""
        from llama_index.core import Document, SimpleDirectoryReader

        from rag_mcp.integrations.azure import parse_azure_response

        md = _local_md(tmp_path)
        local_docs = SimpleDirectoryReader(input_files=[str(md)], filename_as_id=True).load_data()
        azure_docs = parse_azure_response(
            self._mock_result(paragraphs=[MagicMock(content="cloud prose", role="paragraph")]),
            tmp_path / "t.pdf",
        )
        fallback_doc = Document(text="local text", metadata={"file_path": str(md)})
        backends = {
            "local": local_docs,
            "azure": azure_docs,
            "fallback": [fallback_doc],
        }
        for backend_name, docs in backends.items():
            assert docs, f"{backend_name} produced nothing"
            assert all("file_path" in d.metadata for d in docs), backend_name
            assert all(d.get_content().strip() for d in docs), backend_name


# ── Registry contract specifics (new surface; red until task 2.1) ───────


class TestDocumentBackendRegistry:
    """The lazy document-backend registry mirrors the shared contract.

    New surface (task 2.1): every test in this class imports
    ``rag_mcp.core.ingestion.backends`` inside the body, so the module
    still collects before the package exists.
    """

    def _registry(self):
        from rag_mcp.core.ingestion.backends import registry

        return registry

    @staticmethod
    def _drop_temp_entries(registry, name: str) -> None:
        """Remove temporary registrations regardless of internal dict names."""
        for attr in ("_registry", "_cache", "_availability", "_metadata"):
            mapping = getattr(registry, attr, None)
            if isinstance(mapping, dict):
                mapping.pop(name, None)

    def test_available_is_sorted_azure_local(self) -> None:
        """Base registration ships exactly ['azure', 'local'], sorted."""
        assert self._registry().available() == ["azure", "local"]

    def test_describe_azure_metadata(self) -> None:
        """Azure declares its probe, fallback, suffixes, and structured flag."""
        meta = self._registry().describe("azure")
        assert set(meta) == {
            "availability_path",
            "fallback",
            "document_suffixes",
            "structured_output",
        }
        assert meta["availability_path"] == ("rag_mcp.integrations.azure:require_azure_installed")
        assert meta["fallback"] == "local"
        assert meta["document_suffixes"] == frozenset({".pdf", ".docx", ".doc"})
        assert meta["structured_output"] is True

    def test_describe_local_metadata(self) -> None:
        """Local declares no probe, no fallback, no suffix gate, unstructured."""
        meta = self._registry().describe("local")
        assert meta["availability_path"] is None
        assert meta["fallback"] is None
        assert meta["document_suffixes"] is None
        assert meta["structured_output"] is False

    def test_describe_unknown_lists_names(self) -> None:
        """An unknown name raises KeyError listing every registered name."""
        with pytest.raises(KeyError) as excinfo:
            self._registry().describe("nope")
        message = str(excinfo.value)
        assert "Available" in message
        assert "local" in message and "azure" in message

    def test_get_unknown_lists_names(self) -> None:
        """get() on an unknown name raises KeyError listing names."""
        with pytest.raises(KeyError) as excinfo:
            self._registry().get("nope")
        message = str(excinfo.value)
        assert "Available" in message
        assert "local" in message and "azure" in message

    def test_get_import_error_names_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A broken strategy module raises ImportError naming the backend."""
        registry = self._registry()
        registry._cache.pop("local", None)
        monkeypatch.setitem(sys.modules, "rag_mcp.core.ingestion.backends.local", None)
        with pytest.raises(ImportError) as excinfo:
            registry.get("local")
        assert "local" in str(excinfo.value)

    def test_verify_available_local_is_noop(self) -> None:
        """Base-install local has no probe, so verification always passes."""
        assert self._registry().verify_available("local") is None

    def test_verify_available_azure_uses_registered_probe(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """verify_available resolves availability_path and raises its error.

        The probe is stubbed at the integrations module so this holds
        regardless of whether the azure extra is installed in the dev venv.
        """
        import rag_mcp.integrations.azure as azure_mod

        def _missing() -> None:
            raise ImportError(
                "azure-ai-documentintelligence is not installed. "
                "Install with: uv sync --extra azure"
            )

        monkeypatch.setattr(azure_mod, "require_azure_installed", _missing)
        with pytest.raises(ImportError, match="uv sync --extra azure"):
            self._registry().verify_available("azure")

    @pytest.mark.skipif(_AZURE_SDK_PRESENT, reason="azure extra installed")
    def test_require_azure_installed_raises_without_sdk(self) -> None:
        """Without the SDK the real probe names the package and instruction."""
        import rag_mcp.integrations.azure as azure_mod

        with pytest.raises(ImportError) as excinfo:
            azure_mod.require_azure_installed()
        message = str(excinfo.value)
        assert "azure-ai-documentintelligence" in message
        assert "uv sync --extra azure" in message


# ── Task 1.2 — orchestrator retry / fallback matrix (new surface; red) ──


def _azure_settings(effective_settings, **overrides):
    """EffectiveSettings selecting azure with dummy credentials."""
    return effective_settings(
        document_backend="azure",
        azure_doc_intelligence_endpoint="https://example.azure.com/",
        azure_doc_intelligence_key="dummy-key",
        pdf_reader="pypdf",
        **overrides,
    )


class TestRuntimeFallback:
    """Retry budget, ImportError fast-fallback, and single-flight local read.

    Spec requirement "Cloud selection remains local-first on failure".
    All patch targets are the new-surface adapters:
    ``rag_mcp.integrations.azure.read_documents`` and
    ``rag_mcp.core.ingestion.backends.local.read_documents``.
    """

    async def test_runtime_failure_retries_then_single_local_fallback(
        self, tmp_path: Path, effective_settings, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Azure gets MAX_RETRIES+1 attempts, local exactly one, structured=True."""
        from rag_mcp.core.ingestion.backends import BackendRead
        from rag_mcp.core.ingestion.backends import orchestrator as orch

        docs = [MagicMock(name="local-doc")]
        azure_read = AsyncMock(side_effect=RuntimeError("azure down"))
        local_read = AsyncMock(return_value=docs)
        with (
            patch("rag_mcp.integrations.azure.read_documents", azure_read),
            patch("rag_mcp.core.ingestion.backends.local.read_documents", local_read),
            patch("asyncio.sleep", new_callable=AsyncMock),
            caplog.at_level(logging.WARNING, logger=_ORCH_LOGGER),
        ):
            result = await orch.read_document(
                _write_pdf(tmp_path), settings=_azure_settings(effective_settings)
            )

        assert isinstance(result, BackendRead)
        assert azure_read.await_count == orch.MAX_RETRIES + 1
        assert azure_read.await_count == 2
        assert local_read.await_count == 1
        assert result.documents is docs
        # Runtime-fallback keeps the SELECTED entry's structured_output.
        assert result.structured is True
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert warnings, "fallback must emit a visible diagnostic"

    async def test_sdk_missing_at_read_time_skips_retries(
        self, tmp_path: Path, effective_settings, caplog: pytest.LogCaptureFixture
    ) -> None:
        """ImportError goes straight to local: one azure call, structured=False."""
        from rag_mcp.core.ingestion.backends import orchestrator as orch

        docs = [MagicMock(name="local-doc")]
        azure_read = AsyncMock(side_effect=ImportError("azure-ai-documentintelligence missing"))
        local_read = AsyncMock(return_value=docs)
        with (
            patch("rag_mcp.integrations.azure.read_documents", azure_read),
            patch("rag_mcp.core.ingestion.backends.local.read_documents", local_read),
            patch("asyncio.sleep", new_callable=AsyncMock) as sleep_mock,
            caplog.at_level(logging.WARNING, logger=_ORCH_LOGGER),
        ):
            result = await orch.read_document(
                _write_pdf(tmp_path), settings=_azure_settings(effective_settings)
            )

        assert azure_read.await_count == 1
        assert local_read.await_count == 1
        sleep_mock.assert_not_awaited()
        # The backend was unavailable: wholesale local semantics.
        assert result.documents is docs
        assert result.structured is False
        warning_text = " ".join(
            r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
        )
        assert "azure-ai-documentintelligence" in warning_text

    async def test_both_failures_propagate_after_one_fallback_attempt(
        self, tmp_path: Path, effective_settings
    ) -> None:
        """When the local fallback also fails, its error propagates (no retry)."""
        from rag_mcp.core.ingestion.backends import orchestrator as orch

        azure_read = AsyncMock(side_effect=RuntimeError("azure down"))
        local_read = AsyncMock(side_effect=RuntimeError("local exploded"))
        with (
            patch("rag_mcp.integrations.azure.read_documents", azure_read),
            patch("rag_mcp.core.ingestion.backends.local.read_documents", local_read),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(RuntimeError, match="local exploded"):
                await orch.read_document(
                    _write_pdf(tmp_path), settings=_azure_settings(effective_settings)
                )
        assert local_read.await_count == 1, "exactly one fallback attempt, never double-read"

    async def test_unknown_backend_name_propagates_keyerror(
        self, tmp_path: Path, effective_settings
    ) -> None:
        """An unconfigured backend name surfaces the registry's listing error."""
        from rag_mcp.core.ingestion.backends import orchestrator as orch

        settings = effective_settings(document_backend="no-such-backend")
        with pytest.raises(KeyError) as excinfo:
            await orch.read_document(_write_pdf(tmp_path), settings=settings)
        message = str(excinfo.value)
        assert "local" in message and "azure" in message

    def test_retry_policy_is_orchestrator_owned(self) -> None:
        """The retry budget lives on the orchestrator, not the caller."""
        from rag_mcp.core.ingestion.backends import orchestrator as orch

        assert orch.MAX_RETRIES == 1
        assert orch.RETRY_DELAY_S == 5.0


# ── Startup validation gates (task 2.4 surface; red until implemented) ──


class TestStartupValidation:
    """Config keeps the strip/reset idiom; unknown names fail at the gate."""

    def test_bogus_backend_constructs_but_fails_validation(self) -> None:
        """Settings accepts 'totally-bogus'; capabilities.validate rejects it.

        Spec scenario "Unknown backend is configured": startup SHALL fail
        and list the available backend names.
        """
        from rag_mcp.capabilities import validate_document_backend

        settings = Settings(_env_file=None, document_backend="totally-bogus")
        with pytest.raises(ValueError) as excinfo:
            validate_document_backend(settings)
        message = str(excinfo.value)
        assert "DOCUMENT_BACKEND" in message
        assert "totally-bogus" in message
        assert "local" in message and "azure" in message

    def test_resolve_active_strategies_lists_registered_names(self) -> None:
        """The composition-root strategy gate carries the same listing."""
        from rag_mcp.compose import _resolve_active_strategies
        from rag_mcp.core.chunking import registry as chunking_reg
        from rag_mcp.core.metadata import registry as metadata_reg
        from rag_mcp.core.providers.embeddings import registry as embed_reg
        from rag_mcp.core.providers.llm import registry as llm_reg

        settings = Settings(_env_file=None, document_backend="totally-bogus")
        with (
            patch.object(chunking_reg, "get"),
            patch.object(metadata_reg, "get"),
            patch.object(embed_reg, "get"),
            patch.object(llm_reg, "get"),
        ):
            with pytest.raises(ValueError, match=r"DOCUMENT_BACKEND.*totally-bogus"):
                _resolve_active_strategies(settings)

    def test_validate_known_name_is_silent(self) -> None:
        """A registered name passes the gate without diagnostics."""
        from rag_mcp.capabilities import validate_document_backend

        assert validate_document_backend(Settings(_env_file=None)) is None

    def test_resolve_document_backend_normalises_and_defaults(self) -> None:
        """Whitespace is stripped; an empty value resets to local."""
        from rag_mcp.capabilities import resolve_document_backend

        assert resolve_document_backend(Settings(_env_file=None, document_backend="  ")) == "local"
        # A name outside the config tuple passes through unchanged:
        # reject-before-validate is the gate's job, not the resolver's.
        bogus = Settings(_env_file=None)
        object.__setattr__(bogus, "document_backend", "totally-bogus")
        assert resolve_document_backend(bogus) == "totally-bogus"

    @pytest.mark.skipif(not _AZURE_SDK_PRESENT, reason="azure extra not installed")
    def test_resolve_document_backend_keeps_azure_with_sdk(self) -> None:
        """With the SDK importable, an explicit azure selection survives."""
        from rag_mcp.capabilities import resolve_document_backend

        configured = Settings(
            _env_file=None,
            document_backend="  azure  ",
            azure_doc_intelligence_endpoint="https://x",
            azure_doc_intelligence_key="k",
        )
        assert resolve_document_backend(configured) == "azure"

    def test_sdk_missing_degrades_resolution_to_local(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Without the SDK module, azure selection degrades to local + warning.

        Spec scenario "Azure SDK dependency is missing". The SDK module is
        poisoned in ``sys.modules`` so the test is deterministic whether or
        not the azure extra is installed (both ``__import__`` and
        ``find_spec`` probes fail loudly on a ``None`` entry).
        """
        import logging

        from rag_mcp.capabilities import resolve_document_backend
        from rag_mcp.compose import settings_to_effective

        monkeypatch.setitem(sys.modules, "azure.ai.documentintelligence", None)
        settings = Settings(
            _env_file=None,
            document_backend="azure",
            azure_doc_intelligence_endpoint="https://x",
            azure_doc_intelligence_key="k",
        )
        with caplog.at_level(logging.WARNING, logger=_CAPABILITIES_LOGGER):
            assert resolve_document_backend(settings) == "local"

        # settings_to_effective bakes the RESOLVED backend into EffectiveSettings.
        effective = settings_to_effective(settings)
        assert effective.document_backend == "local"
        warning_text = " ".join(
            r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
        )
        assert "azure-ai-documentintelligence" in warning_text


# ── Missing-credential degradation at the Settings layer (green today) ──


class TestMissingCredentialDegradation:
    """Spec scenario "Credentials are missing": azure degrades to local.

    The degradation and the naming diagnostic belong to ``config/``
    before and after this change, so these tests stay green throughout.
    """

    def _settings(self, monkeypatch: pytest.MonkeyPatch) -> object:
        from rag_mcp.config import Settings as S

        monkeypatch.setenv("DOCUMENT_BACKEND", "azure")
        monkeypatch.delenv("AZURE_DOC_INTELLIGENCE_ENDPOINT", raising=False)
        monkeypatch.delenv("AZURE_DOC_INTELLIGENCE_KEY", raising=False)
        return S(_env_file=None)

    def test_both_credentials_missing_falls_back_to_local(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No endpoint and no key resolves to local with a warning."""
        import logging

        settings = self._settings(monkeypatch)
        with caplog.at_level(logging.WARNING, logger=_CONFIG_LOGGER):
            assert settings.document_backend == "local"
        warning_text = " ".join(
            r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
        )
        assert "AZURE_DOC_INTELLIGENCE_ENDPOINT" in warning_text
        assert "AZURE_DOC_INTELLIGENCE_KEY" in warning_text

    def test_only_endpoint_missing_names_the_missing_credential(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Key present but endpoint absent: local fallback still fires."""
        import logging

        monkeypatch.setenv("DOCUMENT_BACKEND", "azure")
        monkeypatch.delenv("AZURE_DOC_INTELLIGENCE_ENDPOINT", raising=False)
        monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_KEY", "dummy-key")
        settings = Settings(_env_file=None)

        with caplog.at_level(logging.WARNING, logger=_CONFIG_LOGGER):
            assert settings.document_backend == "local"
        warning_text = " ".join(
            r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
        )
        # The diagnostic must name the missing credential; the supplied
        # key's presence is never flagged as a defect.
        assert "AZURE_DOC_INTELLIGENCE_ENDPOINT" in warning_text

    def test_with_full_credentials_azure_survives_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Complete credentials keep azure selected at the config layer."""
        monkeypatch.setenv("DOCUMENT_BACKEND", "azure")
        monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_ENDPOINT", "https://x")
        monkeypatch.setenv("AZURE_DOC_INTELLIGENCE_KEY", "k")
        assert Settings(_env_file=None).document_backend == "azure"


# ── Task 1.3 — async responsiveness (both backends) ─────────────────────


async def _run_with_ticker(coro_factory, min_ticks: int = 3):
    """Await a read while counting event-loop ticks during the work.

    The loop stays free only when the blocking work runs in an executor
    thread; a synchronous call inside the coroutine stalls the ticker and
    collapses the tick count, which is exactly the failure this pin hunts.
    """
    task = asyncio.create_task(coro_factory())
    ticks = 0
    while not task.done() and ticks < 200:
        await asyncio.sleep(0.05)
        ticks += 1
    assert task.done(), "read never completed"
    result = task.result()
    assert ticks >= min_ticks, (
        f"event loop yielded only {ticks} times during the read; "
        "blocking work ran on the loop instead of a thread"
    )
    return result


class TestAsyncResponsiveness:
    """Task 1.3 — sync heavy lifting runs off the loop for both backends."""

    async def test_local_read_offloads_to_thread(self, tmp_path: Path, effective_settings) -> None:
        """A slow SimpleDirectoryReader.load_data keeps the loop responsive."""
        from llama_index.core import Document, SimpleDirectoryReader

        from rag_mcp.core.ingestion.backends import orchestrator as orch

        def slow_load_data(self, *args, **kwargs):
            time.sleep(0.3)
            return [Document(text="slow but local")]

        with patch.object(SimpleDirectoryReader, "load_data", slow_load_data):
            result = await _run_with_ticker(
                lambda: orch.read_document(
                    _write_pdf(tmp_path),
                    settings=effective_settings(pdf_reader="pypdf", document_backend="local"),
                )
            )
        assert len(result.documents) == 1
        assert result.structured is False

    async def test_azure_read_offloads_sdk_call_to_thread(
        self, tmp_path: Path, effective_settings
    ) -> None:
        """A slow AzureDocReader.read runs in a thread, not the event loop."""
        from llama_index.core import Document

        from rag_mcp.integrations.azure import AzureDocReader
        from rag_mcp.integrations.azure import read_documents as azure_read

        def slow_read(self, file_path):
            time.sleep(0.3)
            return [Document(text="azure parsed prose", metadata={"file_path": str(file_path)})]

        with patch.object(AzureDocReader, "read", slow_read):
            documents = await _run_with_ticker(
                lambda: azure_read(
                    _write_pdf(tmp_path), settings=_azure_settings(effective_settings)
                )
            )
        assert len(documents) == 1


# ── Chunker dispatch (task 3.1 surface; red until implemented) ──────────


class TestChunkerDispatchViaOrchestrator:
    """The chunker routes reads through the registry-backed orchestrator."""

    async def test_pdf_with_azure_goes_through_new_adapter(
        self, tmp_path: Path, effective_settings
    ) -> None:
        """content_type post-processing runs on orchestrator-returned docs."""
        from llama_index.core import Document

        pdf = _write_pdf(tmp_path)
        docs = [Document(text="Azure extracted prose. " * 40)]
        with patch(
            "rag_mcp.integrations.azure.read_documents",
            AsyncMock(return_value=docs),
        ):
            nodes = await read_and_chunk_file_async(
                pdf,
                content_type="document",
                settings=_azure_settings(effective_settings),
            )
        assert nodes
        assert all(n.metadata.get("content_type") == "document" for n in nodes)

    async def test_markdown_under_azure_hits_suffix_gate(
        self, tmp_path: Path, effective_settings
    ) -> None:
        """.md under azure never calls azure: the gate picks the local backend.

        Metadata parity note: the structured flag carried through the
        suffix-gate path is deliberately NOT pinned — the spec does not
        state whether the selected entry's or the fallback entry's flag
        applies when the file was never attempted (see handover notes).
        """
        md = _local_md(tmp_path, word_count=40)
        azure_read = AsyncMock(return_value=[MagicMock(name="never-used")])
        settings = _azure_settings(effective_settings, **{"metadata.extraction_mode": "disabled"})
        with patch("rag_mcp.integrations.azure.read_documents", azure_read):
            nodes = await read_and_chunk_file_async(md, content_type="document", settings=settings)
        assert azure_read.await_count == 0, "suffix gate must bypass the cloud backend"
        assert nodes, "local reading must still produce chunks"
        assert all(n.metadata.get("content_type") == "document" for n in nodes)

    async def test_total_failure_propagates_out_of_chunker(
        self, tmp_path: Path, effective_settings
    ) -> None:
        """Azure and local both failing raises; no silent empty result."""
        pdf = _write_pdf(tmp_path)
        with (
            patch(
                "rag_mcp.integrations.azure.read_documents",
                AsyncMock(side_effect=RuntimeError("azure down")),
            ),
            patch(
                "rag_mcp.core.ingestion.backends.local.read_documents",
                AsyncMock(side_effect=RuntimeError("local exploded")),
            ),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(RuntimeError, match="local exploded"):
                await read_and_chunk_file_async(pdf, settings=_azure_settings(effective_settings))


# ── Package-import laziness for the new backends package ────────────────


def test_backends_package_import_is_lazy() -> None:
    """Importing the package must not load local.py or the Azure integration.

    Spec requirement "Backend dispatch is lazy and extensible". Runs in a
    subprocess: in-process sys.modules checks are unfalsifiable because
    pytest itself has already imported these modules (mirrors
    test_registry_contract.test_registry_package_import_is_lazy).
    """
    import os
    import subprocess

    env = dict(os.environ)
    env.update(
        {
            "EMBED_PROVIDER": "local",
            "LOCAL_BACKEND": "ollama",
            "EMBED_MODEL": "nomic-embed-text",
        }
    )
    program = (
        "import sys\n"
        "import rag_mcp.core.ingestion.backends\n"
        "eager = [m for m in (\n"
        "    'rag_mcp.core.ingestion.backends.local',\n"
        "    'rag_mcp.integrations.azure',\n"
        ") if m in sys.modules]\n"
        "if eager:\n"
        "    print(','.join(eager))\n"
        "    sys.exit(1)\n"
        "sys.exit(0)\n"
    )
    proc = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, env=env)
    assert proc.returncode == 0, (
        f"backends package eagerly imported strategy modules: {proc.stdout.strip()}"
    )
