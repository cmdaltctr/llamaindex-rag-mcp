"""Shared test fixtures for the RAG MCP server test suite.

Provides:
- EphemeralClient monkeypatch (no disk I/O for ChromaDB)
- Mock embedding model (no Ollama server required)
- FastMCP server instance fixture
- Helper context manager for in-memory MCP client sessions
"""

from __future__ import annotations

import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

# ── IMPORTANT: EMBED_MODEL for test collection ─────────────────────────
# config.py now requires EMBED_MODEL when LOCAL_BACKEND=ollama, and test
# files import rag_mcp modules at module level (before fixtures run).
# This setdefault ensures tests can be collected without a .env file.
# LOCAL_BACKEND is set to ollama (core deps) so tests don't require
# the llamacpp optional dependency group.
os.environ.setdefault("EMBED_PROVIDER", "local")
os.environ.setdefault("LOCAL_BACKEND", "ollama")
os.environ.setdefault("EMBED_MODEL", "nomic-embed-text")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("METADATA_LLM_PROVIDER", "local")
# ────────────────────────────────────────────────────────────────────────

import chromadb
import pytest
from llama_index.core import Settings
from llama_index.core.embeddings import MockEmbedding
from mcp.client import Client

# ── Constants ──────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# ── Session-scoped patches ─────────────────────────────────────────────────


# Shared by `_isolate_env` (which exports them as env vars) and
# `_install_default_effective_settings` (which puts them in the injected
# settings). Defined once so the two fixtures cannot drift apart.
_TEST_PERSIST_DIR = os.path.join(
    tempfile.gettempdir(),
    f"test_chroma_rag_mcp_{os.getpid()}",
)
_TEST_COLLECTION = "test_documents"


@pytest.fixture(autouse=True)
def _patch_chromadb(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace PersistentClient with a singleton EphemeralClient globally.

    This ensures no ``chroma_db/`` directory is created on disk and each
    test gets a fresh in-memory vector store that is shared across all
    calls within the same test (so ingest and search use the same store).

    A wrapper function is used because PersistentClient accepts a ``path``
    kwarg that EphemeralClient does not.

    NOTE: ChromaDB's EphemeralClient shares in-memory state across
    instances (same default tenant/database).  We delete all existing
    collections so each test starts with a truly empty store.
    """
    _original_ephemeral = chromadb.EphemeralClient
    _shared_client = _original_ephemeral()

    # Clear any leftover data from previous tests.  EphemeralClient
    # instances share the same in-memory backend, so a new instance
    # still sees collections created by earlier tests.
    for coll in _shared_client.list_collections():
        _shared_client.delete_collection(coll.name)

    def _ephemeral_singleton(**kwargs):
        """Return a shared EphemeralClient, ignoring the ``path`` argument."""
        return _shared_client

    monkeypatch.setattr(chromadb, "PersistentClient", _ephemeral_singleton)
    monkeypatch.setattr(chromadb, "EphemeralClient", _ephemeral_singleton)

    # Reset the default vector store so each test picks up the current
    # monkeypatch when it lazily constructs a fresh store.
    from rag_mcp.core.vectordb import reset_default_store

    reset_default_store()


@pytest.fixture(autouse=True)
def _clear_registry_caches() -> None:
    """Clear all strategy registry caches before each test.

    The chunking, metadata, retrieval, embeddings, and LLM registries
    cache resolved strategy callables.  When a test patches a strategy
    function at its source module, the cached reference would still point
    at the original.  Clearing the caches ensures each test sees the
    patched function (task 3.7/3.9).
    """
    from rag_mcp.core.chunking import registry as _chunking
    from rag_mcp.core.community import registry as _community
    from rag_mcp.core.metadata import registry as _metadata
    from rag_mcp.core.providers.embeddings import registry as _embed
    from rag_mcp.core.providers.llm import registry as _llm
    from rag_mcp.core.retrieval import registry as _retrieval

    for reg in (_chunking, _metadata, _retrieval, _embed, _llm, _community):
        reg._cache.clear()


# ── EffectiveSettings factory fixture (task 4.1) ─────────────────────


@pytest.fixture
def effective_settings():
    """Return a factory that builds a valid ``EffectiveSettings`` with overrides.

    Usage::

        def test_something(effective_settings):
            settings = effective_settings(top_k=20)
            assert settings.retrieval.top_k == 20

    Builds a frozen :class:`EffectiveSettings` with sensible defaults so
    later test migrations are one-line changes (task 4.1).
    """
    from rag_mcp.core.settings import (
        ChunkingBlock,
        EffectiveSettings,
        IngestionBlock,
        MetadataBlock,
        RetrievalBlock,
    )

    blocks = {
        "chunking": ChunkingBlock,
        "ingestion": IngestionBlock,
        "retrieval": RetrievalBlock,
        "metadata": MetadataBlock,
    }
    # Reverse index: leaf field name → owning block, so flat overrides like
    # ``top_k=20`` route to ``retrieval.top_k`` instead of being silently
    # swallowed by EffectiveSettings (which has no extra="forbid" and whose
    # ``top_k`` is a read-only property, not a field).
    field_owner: dict[str, str] = {}
    for block_name, block_cls in blocks.items():
        for field in block_cls.model_fields:
            field_owner.setdefault(field, block_name)

    def _factory(**overrides) -> EffectiveSettings:
        kwargs: dict = {}
        nested: dict[str, dict] = {}

        for key, value in overrides.items():
            if "." in key:
                # Dotted notation: "retrieval.top_k" → nested override.
                block, field = key.split(".", 1)
                if block not in blocks:
                    raise TypeError(
                        f"effective_settings: unknown block {block!r} in "
                        f"{key!r}. Valid blocks: {sorted(blocks)}"
                    )
                nested.setdefault(block, {})[field] = value
            elif key in EffectiveSettings.model_fields:
                kwargs[key] = value
            elif key in field_owner:
                # Flat leaf name → route into its owning block.
                nested.setdefault(field_owner[key], {})[key] = value
            else:
                # Never silently discard an override — that is the exact
                # failure mode this change exists to eliminate (design D9).
                raise TypeError(
                    f"effective_settings: unknown override {key!r}. It is "
                    f"neither an EffectiveSettings field nor a field of any "
                    f"block ({', '.join(sorted(blocks))}). Note that "
                    f"convenience properties such as 'top_k' on the root "
                    f"model are read-only — use the block field instead."
                )

        for block_name, block_cls in blocks.items():
            if block_name in nested:
                kwargs[block_name] = block_cls(**nested[block_name])

        return EffectiveSettings(**kwargs)

    return _factory


@pytest.fixture(autouse=True)
def _install_default_effective_settings():
    """Install a composition-root default EffectiveSettings for every test.

    Production installs this in ``compose.ensure_runtime_setup()``. Tests that
    call a core entry point without passing ``effective_settings`` need the
    same default present, and each test gets a fresh instance so no state
    leaks between them.
    """
    from rag_mcp.core.settings import (
        EffectiveSettings,
        MetadataBlock,
        reset_default_effective_settings,
        set_default_effective_settings,
    )

    # This must mirror the deterministic environment `_isolate_env` sets, not
    # the class defaults. In particular metadata extraction MUST be disabled:
    # the class default is "llamaindex", which would make every ingestion test
    # perform real LLM calls and hang on network timeouts.
    #   - extraction_mode="disabled" -> no auto-categorisation (was patched
    #     onto the settings singleton before v2.0.0)
    #   - pdf_reader="pypdf"         -> deterministic PDF path (gotcha #6)
    set_default_effective_settings(
        EffectiveSettings(
            metadata=MetadataBlock(extraction_mode="disabled"),
            pdf_reader="pypdf",
            collection_name=_TEST_COLLECTION,
            chroma_persist_dir=_TEST_PERSIST_DIR,
        )
    )
    yield
    reset_default_effective_settings()


@pytest.fixture(autouse=True)
def _patch_embed_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace OllamaEmbedding with MockEmbedding globally.

    Tests should run without a running Ollama server. MockEmbedding
    produces deterministic embeddings based on text hashing.

    Note: The mock must be applied AFTER module imports because
    ``config.py`` sets ``Settings.embed_model`` at import time.
    The ``mcp_server`` fixture re-applies this mock after importing
    those modules.
    """
    _patch_embed_model._mock = MockEmbedding(embed_dim=384)
    Settings.embed_model = _patch_embed_model._mock


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set deterministic environment variables for every test.

    Monkeypatches the shared ``config`` module's constants so that
    both ``ingestion.py`` and ``retrieval.py`` (which import from
    config) always agree on the same collection name and persist
    directory.

    We only patch modules that are *already* loaded (via ``sys.modules``)
    to avoid triggering side-effectful module-level code (e.g.
    ``Settings.embed_model = OllamaEmbedding(...)``) during fixture
    setup.  Modules not yet loaded will pick up the env vars at their
    first import.
    """
    import sys

    monkeypatch.setenv("CHROMA_PERSIST_DIR", _TEST_PERSIST_DIR)
    monkeypatch.setenv("COLLECTION_NAME", _TEST_COLLECTION)
    monkeypatch.setenv("EMBED_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setenv("METADATA_LLM_PROVIDER", "local")
    monkeypatch.setenv("METADATA__EXTRACTION_MODE", "disabled")  # no auto-categorisation in tests
    monkeypatch.setenv("METADATA__KEYWORD_RULES", "")
    monkeypatch.setenv("METADATA__OLLAMA_CLASSIFY_MODEL", "qwen3:0.6b")
    # Keep retry behaviour out of the default test path so existing
    # tests don't pay 1+2+...=O(2^n) seconds of backoff.  Retry-specific
    # tests opt back in by setting this to 2+.
    monkeypatch.setenv("METADATA__CLASSIFY_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("METADATA__CLASSIFY_TIMEOUT", "5.0")

    # NOTE: this fixture used to also monkeypatch legacy module constants
    # (config.CHROMA_PERSIST_DIR …) and then the resolved Settings singleton,
    # because consumers read one or the other depending on how far migration
    # had got. Both are gone in v2.0.0: the constants with the PEP 562 shim
    # (task 9.1) and the singleton with task 5.7. Setting the environment is
    # now sufficient — get_settings() resolves from it, and compose derives
    # the EffectiveSettings every layer receives.
    #
    # Clear any cached Settings so the env above is picked up per test.
    config_mod = sys.modules.get("rag_mcp.config")
    if config_mod is not None:
        monkeypatch.setattr(config_mod, "_settings", None, raising=False)


# ── FastMCP server fixture ─────────────────────────────────────────────────


@pytest.fixture
def mcp_server():
    """Return the real FastMCP server instance from rag_mcp.transports.mcp.

    The ChromaDB and embedding patches are applied via autouse fixtures
    above, so the server uses in-memory ChromaDB and mock embeddings.

    Re-applies MockEmbedding after import because ``config.py``
    sets ``Settings.embed_model = OllamaEmbedding(...)`` at import time.
    """
    from rag_mcp.transports.mcp import mcp

    # Importing server.py triggers config.py which sets
    # Settings.embed_model = OllamaEmbedding(...).  Re-apply mock.
    Settings.embed_model = _patch_embed_model._mock

    return mcp


@asynccontextmanager
async def connected_client(mcp_server):
    """Create an in-memory MCP Client connected to the server.

    This is an async context manager, not a fixture, to avoid teardown
    issues with pytest-asyncio and anyio task groups.

    Uses the v2 ``mcp.client.Client`` (replaces the v1
    ``create_connected_server_and_client_session`` helper).
    """
    async with Client(mcp_server) as client:
        yield client


# ── Fixture file paths ─────────────────────────────────────────────────────


@pytest.fixture
def fixtures_dir() -> Path:
    """Return the path to the test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def sample_txt(fixtures_dir: Path) -> Path:
    """Return path to the sample text fixture."""
    return fixtures_dir / "sample.txt"


@pytest.fixture
def sample_md(fixtures_dir: Path) -> Path:
    """Return path to the sample markdown fixture."""
    return fixtures_dir / "sample.md"


@pytest.fixture
def empty_txt(fixtures_dir: Path) -> Path:
    """Return path to the empty text fixture."""
    return fixtures_dir / "empty.txt"


@pytest.fixture
def dir_with_docs(fixtures_dir: Path) -> Path:
    """Return path to the directory containing multiple documents."""
    return fixtures_dir / "dir_with_docs"


@pytest.fixture
def pdf_dir(fixtures_dir: Path) -> Path:
    """Return path to the directory containing 5 PDF fixtures."""
    return fixtures_dir / "pdf_dir"


@pytest.fixture
def corrupt_dir(fixtures_dir: Path) -> Path:
    """Return path to the directory with a corrupt PDF and a good TXT."""
    return fixtures_dir / "corrupt_dir"
