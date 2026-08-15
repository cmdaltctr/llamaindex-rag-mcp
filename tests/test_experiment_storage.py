"""Tests for experiment storage configuration (add-chroma-cloud-backend).

Covers the deterministic immutable-index collection naming helper
(``core/vectordb/naming.py``), the shared experiment storage helper
(``experiments/_lib/storage.py``), and the calibration-runner migration
guard:

- deterministic naming derived from experiment/corpus/provider/model/
  parser/chunking identity that satisfies Chroma collection-name rules
- checkpoint metadata that is JSON-safe and never carries the API key
- local/cloud store construction through the production factory path
- storage mode resolved independently of the embedding provider
- the six calibration runners contain no direct ``chromadb`` usage or
  ``CHROMA_PERSIST_DIR`` patching once migrated

``experiments._lib.storage`` is imported through ``pytest.importorskip``
so collection does not explode before the implementer adds the module.
The naming module is a production module and is imported lazily inside
tests, so its absence surfaces as a per-test red failure.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import chromadb
import pytest

from rag_mcp.config import Settings
from rag_mcp.core.vectordb.chroma import ChromaVectorStore

_CLOUD_KEY = "0" * 8 + "-chroma-exp-key"

_EXPERIMENT_DIRS = (
    "10b-reranker-pool-size-corrected-2026-06-29",
    "10.1-doc-similarity-threshold-calibration-2026-06-29",
    "12-hybrid-default-promotion-2026-06-29",
    "9a-rerun-post-adr021-reranker-2026-06-29",
    "13-hard-technical-threshold-calibration-2026-06-29",
    "14-liteparse-qasper-promotion-2026-06-29",
)

_NAMING_KWARGS = dict(
    experiment_id="exp14",
    corpus="qasper",
    provider="openrouter",
    model="qwen3-8b",
    parser="liteparse",
    chunk_size=512,
    chunk_overlap=100,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _naming():
    """Import the naming module lazily (red per-test before implementation)."""
    from rag_mcp.core.vectordb import naming

    return naming


def _storage():
    """Import the shared experiment storage helper, skipping until it exists."""
    return pytest.importorskip("experiments._lib.storage")


def _settings(**overrides) -> Settings:
    """Build a fresh Settings without ``.env`` and deterministic defaults."""
    overrides.setdefault("embed_provider", "local")
    overrides.setdefault("local_backend", "ollama")
    overrides.setdefault("embed_model", "nomic-embed-text")
    return Settings(_env_file=None, **overrides)


def _clear_chroma_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove ambient Chroma cloud env entries so defaults are observable."""
    for name in (
        "CHROMA_MODE",
        "CHROMA_CLOUD_API_KEY",
        "CHROMA_CLOUD_TENANT",
        "CHROMA_CLOUD_DATABASE",
    ):
        monkeypatch.delenv(name, raising=False)


def _install_persistent_spy(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Wrap the conftest-patched PersistentClient with a kwargs recorder."""
    inner = chromadb.PersistentClient
    calls: list[dict] = []

    def _spy(**kwargs):
        calls.append(kwargs)
        return inner(**kwargs)

    monkeypatch.setattr(chromadb, "PersistentClient", _spy)
    return calls


def _install_fake_cloud_client(monkeypatch: pytest.MonkeyPatch, backing=None):
    """Patch ``chromadb.CloudClient`` to a recording fake with a heartbeat."""
    state = type("_CloudSpy", (), {})()
    state.construct_calls: list[dict] = []
    state.heartbeat_calls = 0

    class _FakeCloudClient:
        def __init__(self, **kwargs) -> None:
            state.construct_calls.append(kwargs)
            self._backing = backing

        def heartbeat(self) -> None:
            state.heartbeat_calls += 1

        def __getattr__(self, name: str):
            if self._backing is None:
                raise AttributeError(name)
            return getattr(self._backing, name)

    monkeypatch.setattr(chromadb, "CloudClient", _FakeCloudClient, raising=False)
    return state


def _shared_client():
    """Return the shared in-memory Chroma client installed by conftest."""
    return chromadb.EphemeralClient()


# ── Naming helper ────────────────────────────────────────────────────


class TestSanitizeCollectionComponent:
    """Component sanitisation for Chroma collection-name rules."""

    def test_lowercases_and_collapses_separator_runs(self) -> None:
        assert _naming().sanitize_collection_component("My Model!!Name") == "my-model-name"

    def test_strips_leading_and_trailing_separators(self) -> None:
        assert _naming().sanitize_collection_component("  --x__y..  ") == "x-y"

    def test_empty_component_stays_empty(self) -> None:
        assert _naming().sanitize_collection_component("") == ""


class TestExperimentCollectionNaming:
    """Deterministic immutable-index names per the spec scenario."""

    def test_same_inputs_produce_identical_names(self) -> None:
        naming = _naming()
        first = naming.experiment_collection_name(**_NAMING_KWARGS)
        second = naming.experiment_collection_name(**_NAMING_KWARGS)
        assert first == second

    def test_proposal_example_format(self) -> None:
        """The proposal's example derives exactly as documented."""
        assert _naming().experiment_collection_name(**_NAMING_KWARGS) == (
            "exp14-qasper-openrouter-qwen3-8b-liteparse-cs512-co100"
        )

    def test_optional_components_are_omitted(self) -> None:
        name = _naming().experiment_collection_name(
            experiment_id="exp9",
            corpus="qasper",
            provider="openrouter",
            model="qwen3-8b",
        )
        assert name == "exp9-qasper-openrouter-qwen3-8b"

    @pytest.mark.parametrize(
        "field,value",
        [
            ("corpus", "hotpotqa"),
            ("model", "qwen3-14b"),
            ("parser", "pypdf"),
            ("chunk_size", 1024),
            ("chunk_overlap", 200),
        ],
    )
    def test_each_identity_component_changes_the_name(self, field: str, value: object) -> None:
        """A differing identity component must yield a different collection."""
        naming = _naming()
        variant = {**_NAMING_KWARGS, field: value}
        assert naming.experiment_collection_name(**variant) != naming.experiment_collection_name(
            **_NAMING_KWARGS
        )

    @pytest.mark.parametrize(
        "kwargs",
        [
            _NAMING_KWARGS,
            {k: v for k, v in _NAMING_KWARGS.items() if k != "parser"},
            {
                "experiment_id": "Exp 13",
                "corpus": "Hard Technical!!",
                "provider": "OpenRouter",
                "model": "Qwen3 8B",
            },
        ],
    )
    def test_generated_names_satisfy_chroma_rules(self, kwargs: dict) -> None:
        """Every generated name passes the Chroma collection-name rules."""
        name = _naming().experiment_collection_name(**kwargs)
        assert len(name) >= 3
        assert name[0].isalnum() and name[-1].isalnum()
        assert re.fullmatch(r"[a-zA-Z0-9._-]+", name)
        _naming().validate_collection_name(name)

    def test_signature_has_no_cell_or_repetition_parameters(self) -> None:
        """Cell and repetition IDs live in checkpoints, never in the name."""
        import inspect

        parameters = inspect.signature(_naming().experiment_collection_name).parameters
        assert not any("cell" in name or "repet" in name for name in parameters), (
            f"cell/repetition leaked into the naming signature: {list(parameters)}"
        )

    def test_overlong_names_truncate_deterministically_with_hash_suffix(self) -> None:
        """Names beyond 512 characters truncate to a stable hash-suffixed form."""
        naming = _naming()
        kwargs = dict(experiment_id="exp", corpus="c" * 600, provider="p", model="m")
        first = naming.experiment_collection_name(**kwargs)
        second = naming.experiment_collection_name(**kwargs)
        assert first == second
        assert len(first) <= 512
        assert re.search(r"-[0-9a-f]{8}$", first)
        naming.validate_collection_name(first)

    @pytest.mark.parametrize("bad", ["", "ab", "-abc", "abc-", "ab!c", "a" * 513])
    def test_validate_rejects_rule_violations(self, bad: str) -> None:
        with pytest.raises(ValueError):
            _naming().validate_collection_name(bad)

    @pytest.mark.parametrize("good", ["abc", "a.b_c-d", "a" * 512])
    def test_validate_accepts_compliant_names(self, good: str) -> None:
        _naming().validate_collection_name(good)

    def test_all_empty_components_yield_hash_only_name(self) -> None:
        """Degenerate all-empty input still produces a valid name."""
        name = _naming().experiment_collection_name(
            experiment_id="", corpus="", provider="", model=""
        )
        assert re.fullmatch(r"[0-9a-f]+", name)
        _naming().validate_collection_name(name)

    def test_separator_only_slug_collapses_to_hash_name(self) -> None:
        """A slug that strips to under three characters gains a hash."""
        name = _naming().experiment_collection_name(
            experiment_id="x", corpus="..", provider=".", model=""
        )
        _naming().validate_collection_name(name)
        assert re.search(r"[0-9a-f]{8}", name)


# ── Experiment storage configuration ────────────────────────────────


class TestExperimentStorageConfig:
    """The shared helper used by all six calibration harnesses."""

    def test_collection_name_matches_naming_helper(self) -> None:
        """The config delegates naming to the deterministic helper."""
        config = _storage().experiment_storage_config(**_NAMING_KWARGS)
        assert config.collection_name == _naming().experiment_collection_name(**_NAMING_KWARGS)

    def test_checkpoint_metadata_is_json_safe_and_secret_free(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Checkpoints serialise without the API key even when it is in the env."""
        _clear_chroma_env(monkeypatch)
        monkeypatch.setenv("CHROMA_MODE", "cloud")
        monkeypatch.setenv("CHROMA_CLOUD_API_KEY", _CLOUD_KEY)
        monkeypatch.setenv("CHROMA_CLOUD_TENANT", "tenant-ck")
        monkeypatch.setenv("CHROMA_CLOUD_DATABASE", "db-ck")
        config = _storage().experiment_storage_config(
            experiment_id="exp1",
            corpus="qasper",
            provider="openrouter",
            model="qwen3-8b",
        )
        dumped = json.dumps(config.checkpoint_metadata)
        assert _CLOUD_KEY not in dumped
        for value in ("exp1", "qasper", "openrouter", "qwen3-8b", "cloud", "tenant-ck", "db-ck"):
            assert value in dumped
        assert config.collection_name in dumped

    def test_build_store_local_uses_persist_dir(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """Local mode builds the store over the configured persist directory."""
        calls = _install_persistent_spy(monkeypatch)
        persist_dir = str(tmp_path / "exp_index")
        settings = _settings(chroma_mode="local", chroma_persist_dir=persist_dir)
        config = _storage().experiment_storage_config(
            experiment_id="expL",
            corpus="qasper",
            provider="llamacpp",
            model="m-gguf",
            settings=settings,
        )
        assert config.mode == "local"
        assert config.persist_dir == persist_dir
        store = config.build_store(settings)
        assert isinstance(store, ChromaVectorStore)
        store.create_collection("exp_local_probe")
        assert calls and all(call.get("path") == persist_dir for call in calls)
        assert "exp_local_probe" in store.list_collections()

    def test_build_store_cloud_constructs_validated_cloud_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Cloud mode goes through the CloudClient path with exact credentials."""
        state = _install_fake_cloud_client(monkeypatch, backing=_shared_client())
        settings = _settings(
            chroma_mode="cloud",
            chroma_cloud_api_key=_CLOUD_KEY,
            chroma_cloud_tenant="tenant-e",
            chroma_cloud_database="db-e",
        )
        config = _storage().experiment_storage_config(
            experiment_id="expC",
            corpus="qasper",
            provider="openrouter",
            model="qwen3-8b",
            settings=settings,
        )
        assert config.mode == "cloud"
        store = config.build_store(settings)
        assert state.construct_calls == [
            {"api_key": _CLOUD_KEY, "tenant": "tenant-e", "database": "db-e"}
        ]
        assert state.heartbeat_calls >= 1
        store.create_collection("exp_cloud_probe")
        assert "exp_cloud_probe" in store.list_collections()

    @pytest.mark.parametrize("embed_provider", ["local", "cloud"])
    @pytest.mark.parametrize("chroma_mode", ["local", "cloud"])
    def test_mode_independent_of_embed_provider_and_all_four_construct(
        self,
        monkeypatch: pytest.MonkeyPatch,
        embed_provider: str,
        chroma_mode: str,
    ) -> None:
        """All four compute/storage combinations configure and construct a store."""
        _clear_chroma_env(monkeypatch)
        _install_persistent_spy(monkeypatch)
        _install_fake_cloud_client(monkeypatch, backing=_shared_client())
        kwargs: dict = {"embed_provider": embed_provider, "chroma_mode": chroma_mode}
        if chroma_mode == "cloud":
            kwargs["chroma_cloud_api_key"] = _CLOUD_KEY
        settings = _settings(**kwargs)
        config = _storage().experiment_storage_config(
            experiment_id="exp4",
            corpus="qasper",
            provider="openrouter",
            model="qwen3-8b",
            settings=settings,
        )
        assert config.mode == chroma_mode
        store = config.build_store(settings)
        store.create_collection("four_mode_probe")
        assert store.collection_exists("four_mode_probe")

    def test_mode_defaults_to_local_without_cloud_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With no CHROMA_MODE anywhere, the helper stays local."""
        _clear_chroma_env(monkeypatch)
        config = _storage().experiment_storage_config(
            experiment_id="expD",
            corpus="qasper",
            provider="llamacpp",
            model="m-gguf",
            settings=_settings(),
        )
        assert config.mode == "local"


# ── Calibration runner migration guard ──────────────────────────────


class TestCalibrationRunnerMigration:
    """The six calibration harnesses must use the production store path."""

    def test_runners_have_no_raw_chromadb_or_persist_dir_patching(self) -> None:
        """Direct chromadb usage and CHROMA_PERSIST_DIR patching are banned.

        These patterns all move to the shared storage helper / the
        production composition path (design decision 7). This test is
        expected to FAIL until the runner migration lands.
        """
        experiments_root = Path(__file__).resolve().parent.parent / "experiments"
        banned_literals = ("import chromadb", "from chromadb", "PersistentClient")
        assignment_patterns = (
            re.compile(r"\b(?:mod|config)\s*\.\s*CHROMA_PERSIST_DIR\s*="),
            re.compile(r"os\.environ\s*\[\s*['\"]CHROMA_PERSIST_DIR['\"]\s*\]\s*="),
        )
        offenders: list[str] = []
        checked = 0
        for directory in _EXPERIMENT_DIRS:
            for path in sorted((experiments_root / directory).rglob("*.py")):
                checked += 1
                source = path.read_text(encoding="utf-8")
                try:
                    ast.parse(source)
                except SyntaxError as exc:
                    offenders.append(
                        f"{path.relative_to(experiments_root)}: does not parse ({exc})"
                    )
                    continue
                relative = path.relative_to(experiments_root)
                for literal in banned_literals:
                    if literal in source:
                        offenders.append(f"{relative}: contains {literal!r}")
                for pattern in assignment_patterns:
                    if pattern.search(source):
                        offenders.append(f"{relative}: patches CHROMA_PERSIST_DIR")
        assert checked > 0, "the six calibration directories must contain Python files"
        assert not offenders, (
            "calibration runners must obtain storage through the shared helper "
            "(experiments/_lib/storage.py) and the production composition path:\n  "
            + "\n  ".join(offenders)
        )
