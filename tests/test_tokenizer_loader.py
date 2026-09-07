"""OpenSpec: improve-rag-input-quality-5, tasks 3.3 and 3.3a."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest


@dataclass
class _FakeTokenizer:
    """A tokenizer whose configured truncation caps encoded token counts."""

    truncation_limit: int = 4
    truncation_enabled: bool = True
    no_truncation_calls: int = 0

    def no_truncation(self) -> None:
        self.no_truncation_calls += 1
        self.truncation_enabled = False

    def encode(self, text: str) -> SimpleNamespace:
        token_count = len(text)
        if self.truncation_enabled:
            token_count = min(token_count, self.truncation_limit)
        return SimpleNamespace(ids=list(range(token_count)))


@dataclass
class _LoaderState:
    """Local Hugging Face cache and loader observations for one test."""

    cache_files: dict[tuple[str, str], Path] = field(default_factory=dict)
    tokenizers: dict[Path, _FakeTokenizer] = field(default_factory=dict)
    lookup_calls: list[tuple[str, str, str | None]] = field(default_factory=list)
    from_file_calls: list[Path] = field(default_factory=list)


def _argument(
    args: tuple[object, ...],
    kwargs: dict[str, object],
    name: str,
    position: int,
) -> object | None:
    """Read a supported cache-lookup argument in either call style."""
    if name in kwargs:
        return kwargs[name]
    return args[position] if len(args) > position else None


def _install_fake_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    state: _LoaderState,
) -> tuple[ModuleType, Mock]:
    """Install fake local-only Hub and Tokenizers modules."""
    hub = ModuleType("huggingface_hub")
    download = Mock(name="hf_hub_download")

    def try_to_load_from_cache(*args: object, **kwargs: object) -> str | None:
        model = _argument(args, kwargs, "repo_id", 0)
        filename = _argument(args, kwargs, "filename", 1)
        revision = _argument(args, kwargs, "revision", 2)
        state.lookup_calls.append(
            (str(model), str(filename), revision if isinstance(revision, str) else None)
        )
        path = state.cache_files.get((str(model), str(revision)))
        return str(path) if path else None

    hub.try_to_load_from_cache = try_to_load_from_cache
    hub.hf_hub_download = download

    tokenizers = ModuleType("tokenizers")
    pretrained = Mock(name="Tokenizer.from_pretrained")

    def from_file(path: str) -> _FakeTokenizer:
        resolved_path = Path(path)
        state.from_file_calls.append(resolved_path)
        return state.tokenizers[resolved_path]

    tokenizers.Tokenizer = SimpleNamespace(
        from_file=from_file,
        from_pretrained=pretrained,
    )
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    monkeypatch.setitem(sys.modules, "tokenizers", tokenizers)
    return hub, pretrained


def _load_tokenizer_module(
    monkeypatch: pytest.MonkeyPatch,
    state: _LoaderState,
):
    """Import the loader after replacing its external dependencies."""
    hub, pretrained = _install_fake_dependencies(monkeypatch, state)
    monkeypatch.delitem(sys.modules, "omrg.integrations.tokenizer", raising=False)
    module = importlib.import_module("omrg.integrations.tokenizer")
    module.load_tokenizer.cache_clear()
    return module, hub, pretrained


def _add_cached_tokenizer(
    tmp_path: Path,
    state: _LoaderState,
    model: str,
    revision: str,
    name: str,
) -> _FakeTokenizer:
    """Write one local tokenizer artefact and register its fake instance."""
    path = tmp_path / name
    path.write_text("{}", encoding="utf-8")
    tokenizer = _FakeTokenizer()
    state.cache_files[(model, revision)] = path
    state.tokenizers[path] = tokenizer
    return tokenizer


def test_loader_resolves_tokenizer_json_from_local_cache_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Task 3.3a: resolve the pinned tokenizer artefact without Hub access."""
    model = "Qwen/Qwen3-Embedding-4B"
    revision = "test-revision"
    state = _LoaderState()
    expected = _add_cached_tokenizer(tmp_path, state, model, revision, "tokenizer.json")
    module, hub, pretrained = _load_tokenizer_module(monkeypatch, state)

    resolved = module.load_tokenizer(model, revision)

    assert resolved is expected
    assert state.lookup_calls == [(model, "tokenizer.json", revision)]
    assert state.from_file_calls == [tmp_path / "tokenizer.json"]
    hub.hf_hub_download.assert_not_called()
    pretrained.assert_not_called()


def test_loader_cache_identity_includes_model_and_revision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Task 3.3: cache entries must not cross tokenizer identities."""
    state = _LoaderState()
    first = _add_cached_tokenizer(
        tmp_path, state, "org/model-a", "revision-a", "model-a-revision-a.json"
    )
    different_revision = _add_cached_tokenizer(
        tmp_path, state, "org/model-a", "revision-b", "model-a-revision-b.json"
    )
    different_model = _add_cached_tokenizer(
        tmp_path, state, "org/model-b", "revision-a", "model-b-revision-a.json"
    )
    module, _, _ = _load_tokenizer_module(monkeypatch, state)

    same_identity = module.load_tokenizer("org/model-a", "revision-a")
    assert module.load_tokenizer("org/model-a", "revision-a") is same_identity
    assert module.load_tokenizer("org/model-a", "revision-b") is different_revision
    assert module.load_tokenizer("org/model-b", "revision-a") is different_model

    assert same_identity is first
    assert state.from_file_calls == [
        tmp_path / "model-a-revision-a.json",
        tmp_path / "model-a-revision-b.json",
        tmp_path / "model-b-revision-a.json",
    ]


def test_loader_disables_truncation_before_returning_tokenizer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Task 3.3: a loaded tokenizer is made safe for size calculations."""
    state = _LoaderState()
    expected = _add_cached_tokenizer(tmp_path, state, "org/model", "revision", "tokenizer.json")
    module, _, _ = _load_tokenizer_module(monkeypatch, state)

    resolved = module.load_tokenizer("org/model", "revision")

    assert resolved is expected
    assert resolved.no_truncation_calls == 1
    assert not resolved.truncation_enabled


def test_loader_reports_full_count_after_disabling_truncation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Task 3.3: a long input must not be capped by loaded truncation."""
    state = _LoaderState()
    expected = _add_cached_tokenizer(tmp_path, state, "org/model", "revision", "tokenizer.json")
    expected.truncation_limit = 4
    module, _, _ = _load_tokenizer_module(monkeypatch, state)

    tokenizer = module.load_tokenizer("org/model", "revision")
    assert len(tokenizer.encode("x" * 32).ids) == 32


def test_loader_fails_actionably_when_tokenizer_is_not_in_local_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 3.3a: a cache miss must fail locally instead of downloading."""
    model = "Qwen/Qwen3-Embedding-4B"
    revision = "missing-revision"
    state = _LoaderState()
    module, hub, pretrained = _load_tokenizer_module(monkeypatch, state)

    with pytest.raises(module.TokenizerUnavailableError) as error:
        module.load_tokenizer(model, revision)

    message = str(error.value).lower()
    assert model.lower() in message
    assert revision in message
    assert "tokenizer.json" in message
    assert "local" in message
    assert "cache" in message
    assert state.lookup_calls == [(model, "tokenizer.json", revision)]
    assert state.from_file_calls == []
    hub.hf_hub_download.assert_not_called()
    pretrained.assert_not_called()
