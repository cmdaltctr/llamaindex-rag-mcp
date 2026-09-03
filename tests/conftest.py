"""Shared test fixtures for the RAG MCP server test suite.

Provides:
- Deterministic tmp-path LanceDB default store (task 5.3) plus matching
  effective settings, so every test runs on the backend that ships in the
  base install without depending on fixture-order accidents
- EphemeralClient monkeypatch (no disk I/O for ChromaDB) — active only when
  the optional ``chroma`` extra is installed
- Mock embedding model (no Ollama server required)
- FastMCP server instance fixture
- Helper context manager for in-memory MCP client sessions
"""

from __future__ import annotations

import math
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

# ── IMPORTANT: EMBED_MODEL for test execution ─────────────────────────
# Runtime-startup tests need a complete local provider configuration. Imports
# and collection do not initialise this runtime.
# LOCAL_BACKEND is set to ollama (core deps) so tests don't require
# the llamacpp optional dependency group.
os.environ.setdefault("EMBED_PROVIDER", "local")
os.environ.setdefault("LOCAL_BACKEND", "ollama")
os.environ.setdefault("EMBED_MODEL", "nomic-embed-text")
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("METADATA_LLM_PROVIDER", "local")
# ────────────────────────────────────────────────────────────────────────

import pytest
from llama_index.core import Settings
from llama_index.core.embeddings import MockEmbedding
from mcp.client import Client

# ── Constants ──────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class _UnitNormMockEmbedding(MockEmbedding):
    """MockEmbedding normalised to emit unit-norm vectors.

    The embedding norm guard (guard-embedding-normalisation) enforces the
    unit-norm contract production providers honour; the stock mock's
    constant ``[0.5] * dim`` vector (norm ~9.8 at dim=384) would fail the
    guard on every ingest. Normalising preserves the constant-vector
    property, so pairwise distances, scores, and rankings are unchanged.
    """

    def _get_vector(self) -> list[float]:
        vector = super()._get_vector()
        norm = math.sqrt(math.fsum(x * x for x in vector))
        return [x / norm for x in vector] if norm else list(vector)


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
def _reset_default_store() -> None:
    """Reset the process-wide default store before each test.

    Every test must compose or explicitly install its own store; a leaked
    instance from a previous test would share generation counters and
    cached tables across test boundaries. The composition-root setup
    flag is reset with it so a CLI/server entry point that calls
    ``ensure_runtime_setup`` recomposes against this test's pinned
    environment instead of skipping setup with a cleared store.
    """
    from rag_mcp.compose import reset_runtime_setup
    from rag_mcp.core.vectordb import reset_default_store

    reset_runtime_setup()
    reset_default_store()


@pytest.fixture(autouse=True)
def _patch_chromadb(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace PersistentClient with a singleton EphemeralClient globally.

    Active only when the optional ``chroma`` extra is installed (task 5.1:
    the shared conftest must not import chromadb at module level). In the
    base install this fixture is a no-op — the default test store is the
    tmp-path LanceDB database installed by ``_isolate_env``.

    This ensures no ``chroma_db/`` directory is created on disk and each
    test gets a fresh in-memory vector store that is shared across all
    calls within the same test (so ingest and search use the same store).

    A wrapper function is used because PersistentClient accepts a ``path``
    kwarg that EphemeralClient does not.

    NOTE: ChromaDB's EphemeralClient shares in-memory state across
    instances (same default tenant/database).  We delete all existing
    collections so each test starts with a truly empty store.
    """
    try:
        import chromadb
    except ImportError:
        return  # base install: no chromadb, nothing to patch

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
    from rag_mcp.core.ingestion.backends import registry as _docbackend
    from rag_mcp.core.metadata import registry as _metadata
    from rag_mcp.core.providers.embeddings import registry as _embed
    from rag_mcp.core.providers.llm import registry as _llm
    from rag_mcp.core.retrieval import registry as _retrieval
    from rag_mcp.core.vectordb import registry as _vectordb
    from rag_mcp.integrations.pdf import registry as _pdf

    for reg in (
        _chunking,
        _metadata,
        _retrieval,
        _embed,
        _llm,
        _community,
        _pdf,
        _vectordb,
        _docbackend,
    ):
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
        EmbeddingBlock,
        IngestionBlock,
        MetadataBlock,
        RetrievalBlock,
    )

    blocks = {
        "chunking": ChunkingBlock,
        "ingestion": IngestionBlock,
        "embedding": EmbeddingBlock,
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
def _install_default_effective_settings(_isolate_env, _reset_default_store, tmp_path: Path):
    """Install a composition-root default EffectiveSettings for every test.

    Production installs this in ``compose.ensure_runtime_setup()``. Tests that
    call a core entry point without passing ``effective_settings`` need the
    same default present, and each test gets a fresh instance so no state
    leaks between them.

    Task 5.3: the deterministic test store is embedded LanceDB under the
    per-test ``tmp_path``, matching the ``LANCEDB_URI`` exported by
    ``_isolate_env``. Both fixtures derive the path from ``tmp_path``
    directly, so agreement does not depend on fixture ordering. The
    explicit dependency on ``_reset_default_store`` pins reset-then-install
    (pytest orders dependency-free autouse fixtures alphabetically, which
    would otherwise reset the store AFTER this fixture installs it).
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
    effective = EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        pdf_reader="pypdf",
        collection_name=_TEST_COLLECTION,
        chroma_persist_dir=_TEST_PERSIST_DIR,
        vector_store="lancedb",
        lancedb_uri=str(tmp_path / "lancedb"),
    )
    set_default_effective_settings(effective)
    # Task 2.3: get_default_store() is injected-only now, so the test
    # harness composes explicitly through the production registry path —
    # the same construction compose.ensure_runtime_setup performs. The
    # store is built directly from the EffectiveSettings above (the
    # factories read only attribute names both models expose) so this
    # fixture never resolves — and therefore never caches — the flat
    # Settings singleton: a test that overrides provider env vars inside
    # a CliRunner.invoke() must still hit fresh validation.
    from rag_mcp.core.vectordb import registry as vectordb_registry
    from rag_mcp.core.vectordb import set_default_store

    backend = os.environ.get("VECTOR_STORE", "lancedb")
    set_default_store(vectordb_registry.get(backend)(effective))
    yield
    reset_default_effective_settings()


@pytest.fixture(autouse=True)
def _patch_embed_model(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Replace OllamaEmbedding with MockEmbedding for tests that use runtime setup.

    The shared LlamaIndex global remains mocked for the whole suite. CLI
    tests additionally exercise the real composition-root startup path, so
    their selected ``ollama`` registry factory is redirected to this mock.
    Provider/settings validation still runs unchanged; only the networked
    concrete embedding construction is replaced.

    The mock emits UNIT-NORM vectors: the embedding norm guard
    (guard-embedding-normalisation) fails closed on non-unit storage
    vectors, and the stock MockEmbedding's constant ``[0.5] * dim``
    vector has norm ~9.8 for dim=384. Normalising keeps the vector
    constant, so every pairwise distance — and therefore every score and
    ranking asserted elsewhere in the suite — is unchanged.
    """
    _patch_embed_model._mock = _UnitNormMockEmbedding(embed_dim=384)
    Settings.embed_model = _patch_embed_model._mock

    if request.node.path.name in ("test_cli.py", "test_answer_transport_cli.py"):
        from rag_mcp.core.providers.embeddings import registry as embed_registry

        real_get = embed_registry.get

        def _get_for_test(name: str):
            if name == "ollama":
                return lambda _settings: _patch_embed_model._mock
            return real_get(name)

        monkeypatch.setattr(embed_registry, "get", _get_for_test)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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

    Task 5.3: every test runs on an explicit tmp-path LanceDB store so
    the base install (no chroma extra) exercises the full pipeline.
    """
    import sys

    monkeypatch.setenv("VECTOR_STORE", "lancedb")
    monkeypatch.setenv("LANCEDB_URI", str(tmp_path / "lancedb"))
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
    # Deterministic PDF reader (gotcha #6) — also keeps the compose
    # resolver's "PDF_READER=auto resolved to ..." INFO line out of
    # captured CLI output, which the --json parsers must own entirely.
    monkeypatch.setenv("PDF_READER", "pypdf")

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

    The LanceDB store and embedding patches are applied via autouse
    fixtures above, so the server uses a tmp-path store and mock
    embeddings.

    The test fixture supplies a mock embedding model for tool handlers.
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
