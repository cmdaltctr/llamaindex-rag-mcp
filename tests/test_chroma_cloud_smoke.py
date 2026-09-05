"""Regression tests: the Chroma Cloud smoke script must redact secrets in logs.

Regression coverage for the former smoke-script error leak.

The operation and cleanup handlers must redact a cloud error that echoes
an API key, including a truncated six-plus-character prefix. This keeps
the script's guarantee that the key is never printed or logged.

These regression tests pin the redaction contract:

- operation-path failures log a redacted message
- cleanup-path failures log a redacted message
- both the full key and any >=6-character prefix are removed
"""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

import pytest
from llama_index.core.embeddings import MockEmbedding

from test_chroma_cloud import _CLOUD_KEY, _assert_no_key_material, _cloud_settings

_SMOKE_PATH = Path(__file__).resolve().parent.parent / "scripts" / "chroma_cloud_smoke.py"

_SMOKE_MODULE = None


def _load_smoke_module():
    """Import ``scripts/chroma_cloud_smoke.py`` as a module (not on sys.path).

    The script calls ``logging.basicConfig(level=INFO)`` at import time,
    which would raise the root logger level for the rest of the test
    session — the original level is restored afterwards.
    """
    global _SMOKE_MODULE
    if _SMOKE_MODULE is None:
        root = logging.getLogger()
        level_before = root.level
        try:
            spec = importlib.util.spec_from_file_location(
                "chroma_cloud_smoke_under_test", _SMOKE_PATH
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _SMOKE_MODULE = module
        finally:
            root.setLevel(level_before)
    return _SMOKE_MODULE


class _OperationFailureStore:
    """Cloud store double whose first operation fails with a key-bearing error."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def collection_exists(self, name: str) -> bool:
        # False during the leftover pre-check and in the finally cleanup,
        # so only the operation handler's error log fires.
        return False

    def create_collection(self, name: str) -> None:
        raise self._error


class _CleanupFailureStore:
    """Cloud store double that succeeds operations but fails cleanup."""

    def __init__(self, error: Exception) -> None:
        self._error = error
        self._created = False

    def collection_exists(self, name: str) -> bool:
        # False at the leftover pre-check, True by the finally cleanup.
        return self._created

    def create_collection(self, name: str) -> None:
        self._created = True

    def write_nodes(self, nodes, name: str) -> None:
        return None

    def count(self, name: str) -> int:
        return 2

    def query_dense(self, name: str, embedding, n_results: int) -> list[dict]:
        return [{"id": "row-1", "distance": 0.1, "document": "probe", "metadata": {}}]

    def delete_collection(self, name: str) -> None:
        raise self._error


class _SuccessStore:
    """Cloud store double where every step succeeds."""

    def collection_exists(self, name: str) -> bool:
        return False  # no leftover, nothing to clean up

    def create_collection(self, name: str) -> None:
        return None

    def write_nodes(self, nodes, name: str) -> None:
        return None

    def count(self, name: str) -> int:
        return 2

    def query_dense(self, name: str, embedding, n_results: int) -> list[dict]:
        return [{"id": "row-1", "distance": 0.1, "document": "probe", "metadata": {}}]


def _run_smoke_with_store(
    monkeypatch: pytest.MonkeyPatch,
    caplog,
    store,
    *,
    settings_overrides: dict | None = None,
    embed_builder=None,
    level: int = logging.WARNING,
) -> int:
    """Run the smoke script against ``store`` with a cloud-mode Settings stub.

    The lazy imports inside ``run_smoke()`` resolve the module attributes
    at call time, so monkeypatching the source modules is sufficient.
    ``load_dotenv`` is neutralised: the real one would copy every unset
    ``.env`` entry into ``os.environ`` for the rest of the test session.
    """
    smoke = _load_smoke_module()

    overrides = {
        "chroma_cloud_tenant": "tenant-smoke",
        "chroma_cloud_database": "db-smoke",
    }
    if settings_overrides:
        overrides.update(settings_overrides)
    settings = _cloud_settings(**overrides)

    import omrg.compose as compose_mod
    import omrg.config as config_mod
    import omrg.core.vectordb.chroma as chroma_mod

    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr(config_mod, "Settings", lambda: settings)
    monkeypatch.setattr(
        compose_mod,
        "build_embed_model",
        embed_builder
        if embed_builder is not None
        else (lambda _settings: MockEmbedding(embed_dim=384)),
    )
    monkeypatch.setattr(
        chroma_mod,
        "build_chroma_vector_store",
        lambda **_kwargs: store,
    )

    with caplog.at_level(level, logger="chroma_cloud_smoke"):
        # run_smoke assigns the LlamaIndex global embed model; restore it
        # afterwards so a MockEmbedding never leaks into later tests.
        from llama_index.core import Settings as LlamaIndexSettings

        embed_model_before = LlamaIndexSettings.embed_model
        try:
            return smoke.run_smoke()
        finally:
            LlamaIndexSettings.embed_model = embed_model_before


@pytest.mark.parametrize("form", ["full", "prefix"], ids=["full", "prefix"])
def test_operation_failure_log_redacts_key(
    monkeypatch: pytest.MonkeyPatch,
    caplog,
    form: str,
) -> None:
    """Operation-path failures never log full or truncated key material."""
    leaked = _CLOUD_KEY if form == "full" else _CLOUD_KEY[:12]
    store = _OperationFailureStore(RuntimeError(f"401 Unauthorized: api_key={leaked} rejected"))

    exit_code = _run_smoke_with_store(monkeypatch, caplog, store)

    assert exit_code == 1
    assert "Smoke operation failed" in caplog.text
    _assert_no_key_material(caplog.text, _CLOUD_KEY)


@pytest.mark.parametrize("form", ["full", "prefix"], ids=["full", "prefix"])
def test_cleanup_failure_log_redacts_key(
    monkeypatch: pytest.MonkeyPatch,
    caplog,
    form: str,
) -> None:
    """Cleanup-path failures never log full or truncated key material."""
    leaked = _CLOUD_KEY if form == "full" else _CLOUD_KEY[:12]
    store = _CleanupFailureStore(RuntimeError(f"403 Forbidden: api_key={leaked} lacks permission"))

    _run_smoke_with_store(monkeypatch, caplog, store)

    assert "Cleanup failed (collection may remain)" in caplog.text
    _assert_no_key_material(caplog.text, _CLOUD_KEY)


# Digit-led so no >=6-char prefix collides with words such as "tenant"
# that legitimately appear in log text.
_SMOKE_TENANT = "7" * 8 + "-tenant"
_SMOKE_DATABASE = "6" * 8 + "-database"
_OPENROUTER_KEY = "sk-or-" + "5" * 12


def test_operation_failure_log_redacts_tenant_and_database(
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    """Operation-path failures never log configured tenant/database values."""
    store = _OperationFailureStore(
        RuntimeError(
            f"ChromaAuthError: unauthorized for tenant={_SMOKE_TENANT} database={_SMOKE_DATABASE}"
        )
    )
    exit_code = _run_smoke_with_store(
        monkeypatch,
        caplog,
        store,
        settings_overrides={
            "chroma_cloud_tenant": _SMOKE_TENANT,
            "chroma_cloud_database": _SMOKE_DATABASE,
        },
    )

    assert exit_code == 1
    assert "Smoke operation failed" in caplog.text
    _assert_no_key_material(caplog.text, _SMOKE_TENANT)
    _assert_no_key_material(caplog.text, _SMOKE_DATABASE)


@pytest.mark.parametrize("form", ["full", "prefix"], ids=["full", "prefix"])
def test_operation_failure_log_redacts_openrouter_key(
    monkeypatch: pytest.MonkeyPatch,
    caplog,
    form: str,
) -> None:
    """Operation-path failures never log the OpenRouter embedding key."""
    leaked = _OPENROUTER_KEY if form == "full" else _OPENROUTER_KEY[:12]
    store = _OperationFailureStore(RuntimeError(f"401 Unauthorized: key={leaked} rejected"))
    exit_code = _run_smoke_with_store(
        monkeypatch,
        caplog,
        store,
        settings_overrides={"openrouter_api_key": _OPENROUTER_KEY},
    )

    assert exit_code == 1
    assert "Smoke operation failed" in caplog.text
    _assert_no_key_material(caplog.text, _OPENROUTER_KEY)


def test_embed_construction_failure_redacts_openrouter_key(
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    """Embedding-client construction failures never log the OpenRouter key."""

    def _boom(_settings):
        raise RuntimeError(f"OpenAI error: invalid api_key={_OPENROUTER_KEY}")

    exit_code = _run_smoke_with_store(
        monkeypatch,
        caplog,
        _SuccessStore(),
        settings_overrides={"openrouter_api_key": _OPENROUTER_KEY},
        embed_builder=_boom,
    )

    assert exit_code == 1
    assert "Embedding client construction failed" in caplog.text
    _assert_no_key_material(caplog.text, _OPENROUTER_KEY)


def test_success_log_masks_tenant_and_database(
    monkeypatch: pytest.MonkeyPatch,
    caplog,
) -> None:
    """The success path never prints configured tenant/database values."""
    exit_code = _run_smoke_with_store(
        monkeypatch,
        caplog,
        _SuccessStore(),
        settings_overrides={
            "chroma_cloud_tenant": _SMOKE_TENANT,
            "chroma_cloud_database": _SMOKE_DATABASE,
        },
        level=logging.INFO,
    )

    assert exit_code == 0
    assert "Smoke check passed" in caplog.text
    assert "Storage mode: cloud" in caplog.text
    assert "tenant=set" in caplog.text
    assert "database=set" in caplog.text
    _assert_no_key_material(caplog.text, _SMOKE_TENANT)
    _assert_no_key_material(caplog.text, _SMOKE_DATABASE)
