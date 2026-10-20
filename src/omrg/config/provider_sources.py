"""Which source set each setting, and the key references (design D2, D3, D6).

The web workspace may save an address, a key or the Chat model. A value that
the process environment or ``.env`` sets wins and locks its field, so this
module records those fields at resolution time, the way ``storage`` records
``vector_store_provenance``. A value from ``omrg.jsonc`` does not lock. YAML
and ``defaults.yaml`` count as defaults.

``omrg.jsonc`` values arrive through ``UserConfigSource``. Key fields do not:
their ``env://`` and ``file://`` references, and the implicit
``secrets/<provider>.key`` files, apply after validation, and a
``keychain://`` reference is only recorded (``compose_providers`` resolves it).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import PydanticBaseSettingsSource

from ..core.settings import PROVIDER_ADDRESS_FIELDS, PROVIDER_SECRET_FIELDS
from .provenance import SOURCE_ORDER, leaf_paths, merge_layers, split_environment
from .rules import FILE_ONLY, SECRET_FIELDS, provider_of
from .settings_file import SettingsFile, UserConfigSource, read_settings_file, setting_blocks
from .user_config import INT_KEY_BOUNDS, SECRETS_DIR

if TYPE_CHECKING:
    from . import Settings

#: Whole-number editable fields (the context windows), each with its range.
PROVIDER_INT_FIELDS: tuple[str, ...] = tuple(INT_KEY_BOUNDS)
#: Settings of the llama.cpp server that ``omrg web`` manages (program, model).
PROVIDER_SERVER_FIELDS: tuple[str, ...] = ("llamacpp_server_binary", "llamacpp_server_model")

#: Editable provider fields, as ``Settings`` paths. ``answer.*`` live in the
#: nested answer block: the Chat choice and the claim check judge choice.
PROVIDER_FIELDS: tuple[str, ...] = (
    *PROVIDER_ADDRESS_FIELDS,
    *PROVIDER_SECRET_FIELDS,
    *PROVIDER_INT_FIELDS,
    *PROVIDER_SERVER_FIELDS,
    "answer.provider",
    "answer.model",
    "answer.verify_provider",
    "answer.verify_model",
)


def coerce_field(path: str, value: str) -> str | int | None:
    """Return *value* typed for the ``Settings`` field *path*, or ``None`` when unusable.

    A whole-number field takes a string of digits inside its range. A text
    field returns the stripped text. ``None`` means the value is damaged or out
    of range, so the caller keeps the next source.
    """
    text = str(value).strip()
    bounds = INT_KEY_BOUNDS.get(path)
    if bounds is None:
        return text or None
    if not (text.isascii() and text.isdigit()):
        return None
    number = int(text)
    return number if bounds[0] <= number <= bounds[1] else None


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


def source_layers(
    settings_cls: type[Any],
    init: PydanticBaseSettingsSource,
    env: PydanticBaseSettingsSource,
    dotenv: PydanticBaseSettingsSource,
    user: UserConfigSource,
    *defaults: PydanticBaseSettingsSource,
) -> dict[str, frozenset[str]]:
    """Return the setting paths each source word supplies (see ``provenance``).

    The environment source also holds the ``.env`` names that ``load_dotenv``
    copied into the environment, so they move to the ``dotenv`` layer.
    """
    blocks = setting_blocks(settings_cls)
    shell, from_dotenv = split_environment(leaf_paths(_safe_values(env), blocks))
    return {
        "init": leaf_paths(_safe_values(init), blocks),
        "env": shell,
        "dotenv": leaf_paths(_safe_values(dotenv), blocks) | from_dotenv,
        "config-file": frozenset(p for p in user.file.values if p not in FILE_ONLY),
        "yaml": frozenset().union(*(leaf_paths(_safe_values(s), blocks) for s in defaults)),
    }


class ProviderSourceMixin(BaseModel):
    """Chat provider connection fields, and :attr:`Settings.provider_explicit`.

    The fields live here, not in ``config/__init__.py``, which sits at the
    500-line ceiling. ``Settings`` inherits them like any other field.
    """

    openai_compatible_base_url: str = "https://api.openai.com/v1"
    openai_compatible_api_key: str = ""
    anthropic_api_key: str = ""
    #: Tokens sent as ``num_ctx`` to Ollama chat and metadata calls (not embeddings).
    ollama_context_window: int = Field(16384, ge=2048, le=262144)
    #: Tokens passed as ``-c`` to the llama.cpp server that ``omrg web`` starts.
    llamacpp_context_window: int = Field(16384, ge=2048, le=262144)
    #: Idle seconds before the managed llama.cpp server frees its model
    #: (``--sleep-idle-seconds``). 0 turns sleep off.
    llamacpp_idle_sleep_seconds: int = Field(300, ge=0, le=86400)
    #: Program and model of the managed llama.cpp server (empty means not set).
    llamacpp_server_binary: str = ""
    llamacpp_server_model: str = ""

    #: Fields ``omrg.jsonc`` set (an ``env://`` key reference counts).
    config_file_fields: frozenset[str] = frozenset()
    #: Secret fields that a key file set (a saved keychain key overrides them).
    key_file_fields: frozenset[str] = frozenset()
    #: Where each key-file key was read, as a full path.
    key_file_paths: dict[str, str] = {}
    #: ``keychain://`` references in ``omrg.jsonc``: field name to provider name.
    #: ``compose_providers.resolve_keychain_references`` turns them into keys.
    keychain_refs: dict[str, str] = {}
    #: Source word of every setting that a source set, by dotted path
    #: (``init``, ``env``, ``dotenv``, ``config-file``, ``yaml``, ``key-file``).
    #: A path that is missing here came from the code default.
    setting_sources: dict[str, str] = {}
    #: The user config folder in use, as a full path.
    user_config_dir: str = ""

    @model_validator(mode="after")
    def _record_provider_sources(self) -> Settings:
        cls = self.__class__
        parsed: SettingsFile = getattr(cls, "_user_file", None) or read_settings_file()
        layers: dict[str, frozenset[str]] = getattr(cls, "_source_layers", {})
        sources = merge_layers([(word, layers.get(word, ())) for word in SOURCE_ORDER])
        held = layers.get("init", frozenset()) | layers.get("env", frozenset())
        held = held | layers.get("dotenv", frozenset())
        refs: dict[str, str] = {}
        paths: dict[str, str] = {}
        for name in SECRET_FIELDS:
            if name in held:
                continue
            if name in parsed.references:
                refs[name] = parsed.references[name]
                continue
            if name in parsed.secrets:
                value, word = parsed.secrets[name], "config-file"
                if name in parsed.key_paths:
                    word, paths[name] = "key-file", parsed.key_paths[name]
            elif name in parsed.key_file:
                value, word = parsed.key_file[name], "key-file"
                paths[name] = str(parsed.directory / SECRETS_DIR / f"{provider_of(name)}.key")
            else:
                continue
            object.__setattr__(self, name, value)
            sources[name] = word
        object.__setattr__(self, "provider_explicit", cls._explicit_provider_sources)
        object.__setattr__(self, "setting_sources", sources)
        object.__setattr__(self, "keychain_refs", refs)
        object.__setattr__(self, "key_file_paths", paths)
        object.__setattr__(
            self,
            "config_file_fields",
            frozenset(p for p, w in sources.items() if w == "config-file"),
        )
        object.__setattr__(
            self,
            "key_file_fields",
            frozenset(p for p, w in sources.items() if w == "key-file"),
        )
        object.__setattr__(self, "user_config_dir", str(parsed.directory))
        return self
