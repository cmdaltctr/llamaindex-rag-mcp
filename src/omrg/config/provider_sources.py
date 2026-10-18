"""Which editable provider values an operator set explicitly (design D2).

The web workspace may save an address, a key or the Chat model. A value that
the process environment or ``.env`` sets wins and locks its field, so this
module records those fields at resolution time, the way ``storage`` records
``vector_store_provenance``. YAML and ``defaults.yaml`` count as defaults.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, model_validator
from pydantic_settings import PydanticBaseSettingsSource

from ..core.settings import PROVIDER_ADDRESS_FIELDS, PROVIDER_SECRET_FIELDS
from .user_config import load_user_config, user_config_dir

if TYPE_CHECKING:
    from . import Settings

#: Editable provider fields, as ``Settings`` paths. ``answer.*`` live in the
#: nested answer block.
PROVIDER_FIELDS: tuple[str, ...] = (
    *PROVIDER_ADDRESS_FIELDS,
    *PROVIDER_SECRET_FIELDS,
    "answer.provider",
    "answer.model",
)


def _present(values: dict[str, Any], path: str) -> bool:
    """Return whether *values* holds a non-blank value at the dotted *path*."""
    node: Any = values
    for part in path.split("."):
        if not isinstance(node, dict):
            return False
        node = {str(k).lower(): v for k, v in node.items()}.get(part)
    return node is not None and str(node).strip() != ""


def _safe_values(source: PydanticBaseSettingsSource) -> dict[str, Any]:
    """Return what *source* would resolve; a source that raises gives ``{}``."""
    try:
        return source() or {}
    except Exception:  # noqa: BLE001 - a broken source must not break config
        return {}


def explicit_provider_fields(*sources: PydanticBaseSettingsSource) -> frozenset[str]:
    """Return the editable provider fields that any of *sources* would set.

    A source that raises contributes nothing, as in ``storage.source_keys``.
    Blank values do not count, so an empty ``OPENROUTER_API_KEY=`` line in
    ``.env`` leaves the field open to a saved value.
    """
    found: set[str] = set()
    for source in sources:
        values = _safe_values(source)
        found.update(path for path in PROVIDER_FIELDS if _present(values, path))
    return frozenset(found)


class ProviderSourceMixin(BaseModel):
    """Chat provider connection fields, and :attr:`Settings.provider_explicit`.

    The fields live here, not in ``config/__init__.py``, which sits at the
    500-line ceiling. ``Settings`` inherits them like any other field.
    """

    openai_compatible_base_url: str = "https://api.openai.com/v1"
    openai_compatible_api_key: str = ""
    anthropic_api_key: str = ""

    #: Fields ``omrg.jsonc`` set (they also appear in ``provider_explicit``).
    config_file_fields: frozenset[str] = frozenset()
    #: Secret fields that only a key file set (a saved keychain key overrides them).
    key_file_fields: frozenset[str] = frozenset()
    #: The user config folder in use, as a full path.
    user_config_dir: str = ""

    @model_validator(mode="after")
    def _record_provider_sources(self) -> Settings:
        cls = self.__class__
        taken = cls._explicit_provider_sources | cls._init_provider_fields
        config = load_user_config()
        from_config = {p: v for p, v in config.values.items() if p not in taken}
        from_keys = {
            p: v
            for p, v in config.key_file.items()
            if p not in taken and p not in from_config and not str(getattr(self, p, "")).strip()
        }
        answer = {p.removeprefix("answer."): v for p, v in from_config.items() if "." in p}
        for path, value in {**from_config, **from_keys}.items():
            if "." not in path:
                object.__setattr__(self, path, value)
        if answer:
            object.__setattr__(self, "answer", self.answer.model_copy(update=answer))
        object.__setattr__(
            self, "provider_explicit", cls._explicit_provider_sources | frozenset(from_config)
        )
        object.__setattr__(self, "config_file_fields", frozenset(from_config))
        object.__setattr__(self, "key_file_fields", frozenset(from_keys))
        object.__setattr__(self, "user_config_dir", str(user_config_dir()))
        return self
