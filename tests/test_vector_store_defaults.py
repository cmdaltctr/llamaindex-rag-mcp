"""TDD RED tests: vector-store default, provenance, and Chroma validation order.

Spec source: openspec/changes/make-lancedb-default-and-isolate-chromadb

- specs/config-composition-root/spec.md — default resolution with source
  provenance, agreeing default surfaces, Chroma compatibility validated
  before credentials.
- specs/chroma-cloud-backend/spec.md — Chroma settings must never alter an
  unselected LanceDB route; credential completeness still enforced when the
  backend matches.

Written test-first against unimplemented behaviour: every test here is
expected to FAIL (RED) until the change lands. Do not weaken the
assertions to make them pass against the current ``chroma`` default.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from rag_mcp.config import Settings, get_settings

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Env vars that can explicitly supply a backend or Chroma-mode value.
_BACKEND_ENV_VARS = (
    "VECTOR_STORE",
    "CHROMA_MODE",
    "CHROMA_CLOUD_API_KEY",
    "CHROMA_CLOUD_TENANT",
    "CHROMA_CLOUD_DATABASE",
)


def _clear_backend_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove backend and Chroma env vars so shipped defaults can resolve."""
    for var in _BACKEND_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _fresh_get_settings(monkeypatch: pytest.MonkeyPatch):
    """Resolve ``get_settings()`` against the CURRENT test environment.

    Copies the conftest ``_isolate_env`` cache-reset idiom: the resolved
    singleton lives in the module global ``rag_mcp.config._settings``.
    """
    import rag_mcp.config as config_mod

    monkeypatch.setattr(config_mod, "_settings", None, raising=False)
    return get_settings()


def test_default_resolution_is_lancedb(monkeypatch: pytest.MonkeyPatch) -> None:
    """No explicit backend resolves to lancedb with 'default' provenance.

    Spec: config-composition-root, scenario 'Default resolution'.
    """
    _clear_backend_env(monkeypatch)
    settings = _fresh_get_settings(monkeypatch)
    assert settings.vector_store == "lancedb"
    assert settings.vector_store_provenance == "default"


def test_explicit_env_selection_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit env VECTOR_STORE=chroma keeps 'chroma' and records 'explicit'.

    Spec: config-composition-root, scenario 'Explicit selection is preserved'.
    """
    monkeypatch.setenv("VECTOR_STORE", "chroma")
    settings = _fresh_get_settings(monkeypatch)
    assert settings.vector_store == "chroma"
    assert settings.vector_store_provenance == "explicit"


def test_explicit_constructor_selection() -> None:
    """A constructor-supplied backend is recorded as an explicit selection."""
    assert Settings(vector_store="chroma").vector_store_provenance == "explicit"


def test_yaml_defaults_surface_agrees() -> None:
    """defaults.yaml ships lancedb as the vector-store default.

    Spec: config-composition-root, scenario 'Default surfaces agree'.
    """
    data = yaml.safe_load((_REPO_ROOT / "src" / "rag_mcp" / "config" / "defaults.yaml").read_text())
    # The YAML file uses env-style (upper-case) keys, matching the env source.
    assert data["VECTOR_STORE"] == "lancedb"


def test_env_example_surface_agrees() -> None:
    """The single uncommented .env.example VECTOR_STORE line ships lancedb."""
    text = (_REPO_ROOT / ".env.example").read_text()
    values = [
        line.split("=", 1)[1].strip()
        for line in text.splitlines()
        if line.startswith("VECTOR_STORE=")
    ]
    assert values == ["lancedb"]


def test_effective_settings_surface_agrees() -> None:
    """EffectiveSettings declares lancedb as the vector_store field default."""
    from rag_mcp.core.settings import EffectiveSettings

    default = EffectiveSettings.model_fields["vector_store"].default
    assert default == "lancedb"


def test_chroma_settings_with_lancedb_backend_rejected_before_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CHROMA_MODE=cloud under lancedb reports backend mismatch, never the key.

    Spec: config-composition-root, scenario 'Cloud mode and LanceDB with
    missing API key'; chroma-cloud-backend, scenario 'Chroma settings with
    LanceDB selected'.
    """
    monkeypatch.setenv("VECTOR_STORE", "lancedb")
    monkeypatch.setenv("CHROMA_MODE", "cloud")
    monkeypatch.delenv("CHROMA_CLOUD_API_KEY", raising=False)
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    message = str(excinfo.value)
    assert "VECTOR_STORE=chroma" in message
    assert "CHROMA_MODE" in message
    assert "api key" not in message.lower()


def test_partial_and_whitespace_chroma_credentials_with_lancedb_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Any non-empty-after-trim Chroma setting under lancedb names the setting.

    Spec: config-composition-root, scenario 'Partial or whitespace
    credentials with LanceDB' — the mismatch is reported without exposing
    the submitted value.
    """
    # Whitespace-only API key in cloud mode still reports the mode clash.
    monkeypatch.setenv("VECTOR_STORE", "lancedb")
    monkeypatch.setenv("CHROMA_MODE", "cloud")
    monkeypatch.setenv("CHROMA_CLOUD_API_KEY", "   ")
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert "CHROMA_MODE" in str(excinfo.value)

    # Local mode with a stray cloud credential must name that credential.
    monkeypatch.setenv("CHROMA_MODE", "local")
    monkeypatch.setenv("CHROMA_CLOUD_TENANT", "t")
    monkeypatch.delenv("CHROMA_CLOUD_API_KEY", raising=False)
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert "CHROMA_CLOUD_TENANT" in str(excinfo.value)


def test_chroma_cloud_with_chroma_backend_still_validates_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backend matches → the existing credential completeness check still fires."""
    monkeypatch.setenv("VECTOR_STORE", "chroma")
    monkeypatch.setenv("CHROMA_MODE", "cloud")
    monkeypatch.delenv("CHROMA_CLOUD_API_KEY", raising=False)
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    lowered = str(excinfo.value).lower()
    # The credential is named either in prose ("API key") or by its env
    # var — both count as mentioning the missing credential.
    assert ("api key" in lowered) or ("chroma_cloud_api_key" in lowered)


def test_valid_lancedb_settings_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """Plain lancedb selection with local Chroma mode and empty creds resolves."""
    monkeypatch.setenv("VECTOR_STORE", "lancedb")
    monkeypatch.setenv("CHROMA_MODE", "local")
    monkeypatch.delenv("CHROMA_CLOUD_API_KEY", raising=False)
    monkeypatch.delenv("CHROMA_CLOUD_TENANT", raising=False)
    monkeypatch.delenv("CHROMA_CLOUD_DATABASE", raising=False)
    assert Settings().vector_store == "lancedb"
