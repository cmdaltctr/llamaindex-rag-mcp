"""Pydantic settings sources for YAML defaults and profile bundles.

Split out of ``config/__init__.py`` (task 8.7) to bring it under the
500-line ceiling and toward the ~150-line target in PROPOSAL §4.2.

Both sources read the v2.0.0 nested schema: subpackage settings live under
their block with lowercase leaves, cross-cutting settings stay flat.
"""

from __future__ import annotations

import logging
import os
from importlib.resources import files
from typing import Annotated, Any

import yaml
from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

logger = logging.getLogger(__name__)


# ── Legacy bool parser ──────────────────────────────────────────────
# Pre-refactor code used ``.lower() == "true"`` for boolean env vars.
# Pydantic's native bool parser accepts "1"/"yes"/"on" as True, which
# would be a silent semantic change.  This validator constrains parsing
# to the legacy contract.


def _parse_legacy_bool(value: object) -> object:
    """Parse booleans with legacy ``.lower() == "true"`` semantics."""
    if isinstance(value, str):
        return value.lower() == "true"
    return value


LegacyBool = Annotated[bool, BeforeValidator(_parse_legacy_bool)]


# ── YAML defaults source ────────────────────────────────────────────


class _YamlDefaultsSource(PydanticBaseSettingsSource):
    """Settings source reading ``config/defaults.yaml`` via importlib.resources.

    YAML uses the nested schema (PROPOSAL §4.3/§6.2): ``chunking:``,
    ``ingestion:``, ``retrieval:`` and ``metadata:`` blocks with lowercase
    leaf keys, plus flat cross-cutting keys at the top level. Values from
    this source sit between field defaults (lower) and env/.env (higher).
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._data: dict[str, Any] = self._load_yaml()

    def _load_yaml(self) -> dict[str, Any]:
        """Load defaults.yaml from the package, tolerating missing file."""
        try:
            yaml_path = files("omrg.config") / "defaults.yaml"
            with yaml_path.open("r") as fh:
                data = yaml.safe_load(fh)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, ModuleNotFoundError):
            return {}

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return self._data.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field_name in self.settings_cls.model_fields:
            if field_name in self._data:
                result[field_name] = self._data[field_name]
        return result


# ── Profile YAML source (Phase 4) ───────────────────────────────────


def _load_profile_bundle(profile_name: str) -> dict[str, Any]:
    """Load a profile bundle from ``config/profiles/<name>.yaml``.

    Operational profiles (``documents``, ``codebase``) return their Tier 2
    lever overrides as a flat dict keyed by SCREAMING_SNAKE_CASE env names.

    The ``hybrid`` profile is a mode selector: it declares only a
    ``default_profile`` key.  This function resolves hybrid to the named
    default profile's bundle so the startup Settings carries concrete
    retrieval levers.

    Args:
        profile_name: One of ``documents``, ``codebase``, ``hybrid``.

    Returns:
        Flat dict of profile overrides, or an empty dict if the bundle
        cannot be loaded (graceful degradation).
    """
    try:
        yaml_path = files("omrg.config") / "profiles" / f"{profile_name}.yaml"
        with yaml_path.open("r") as fh:
            data = yaml.safe_load(fh)
    except (FileNotFoundError, ModuleNotFoundError):
        return {}
    except yaml.YAMLError as exc:
        logger.error("Profile bundle %r has invalid YAML: %s — ignoring", profile_name, exc)
        return {}

    if not isinstance(data, dict):
        return {}

    _LEVER_BLOCKS = ("retrieval", "chunking", "ingestion", "metadata")

    # Reject the pre-v2 flat schema loudly rather than silently ignoring it.
    flat_keys = [k for k in data if k.isupper()]
    if flat_keys:
        raise ValueError(
            f"Profile bundle {profile_name!r} uses the pre-v2.0.0 flat schema. "
            f"Offending key(s): {', '.join(sorted(flat_keys))}. Nest them under "
            f"a {', '.join(_LEVER_BLOCKS)} block — e.g. 'TOP_K: 10' becomes "
            f"'retrieval:\n  top_k: 10'."
        )

    # Hybrid is a mode selector — it must carry no operational levers.
    if profile_name == "hybrid":
        lever_blocks = [b for b in _LEVER_BLOCKS if b in data]
        if lever_blocks:
            raise ValueError(
                f"hybrid.yaml declares lever block(s) {', '.join(lever_blocks)}, "
                f"but hybrid is a mode selector, not an operational profile. "
                f"Move those levers into documents.yaml or codebase.yaml."
            )
        default_profile = data.get("default_profile", "documents")
        if default_profile not in ("documents", "codebase"):
            default_profile = "documents"
        return _load_profile_bundle(default_profile)

    return data


class _ProfileYamlSettingsSource(PydanticBaseSettingsSource):
    """Settings source reading the selected profile bundle.

    Sits between ``_YamlDefaultsSource`` (defaults.yaml, lower) and the
    environment sources (higher) in the precedence chain.  The profile
    bundle supplies Tier 2 lever overrides for the server-wide default
    profile selected by ``RAG_PROFILE``.

    Per-collection profile resolution at operation time is handled by
    :class:`omrg.core.profiles.resolver.ProfileResolver`, not by this
    source.  This source only affects the startup ``Settings`` singleton.
    """

    def __init__(self, settings_cls: type[BaseSettings]) -> None:
        super().__init__(settings_cls)
        self._data: dict[str, Any] = self._load_profile()

    def _load_profile(self) -> dict[str, Any]:
        """Load the profile bundle selected by ``RAG_PROFILE``."""
        profile = os.environ.get("RAG_PROFILE", "documents")
        return _load_profile_bundle(profile)

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:
        return self._data.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for field_name in self.settings_cls.model_fields:
            if field_name in self._data:
                result[field_name] = self._data[field_name]
        return result
