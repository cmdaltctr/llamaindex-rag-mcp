"""Value rules shared by ``Settings`` validation and ``omrg.jsonc`` reading.

``omrg.jsonc`` ignores a value that breaks its rule and names the key (task
2.4), so the rules must be checkable before ``Settings`` is built. This
module holds the rules that are not plain types: the accepted names of a
choice field, the shape of an address, and the three file-only keys.

It is a leaf: it imports only pure-data settings models. Messages name a
rule, never a value.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from ..core.settings import OCR_ROUTING_UNITS, PROVIDER_SECRET_FIELDS

METADATA_EXTRACTION_MODES = (
    "disabled",
    "keyword",
    "local",
    "llamaindex",
    "ollama",
    "llamacpp",
    "openrouter",
)

#: Accepted names by setting path. ``Settings`` validators and the file reader
#: both read this table, so they cannot drift apart.
ACCEPTED: dict[str, tuple[str, ...]] = {
    "embed_provider": ("local", "cloud", "ollama", "llamacpp", "openrouter"),
    "metadata_llm_provider": ("local", "cloud"),
    "metadata.extraction_mode": METADATA_EXTRACTION_MODES,
    "local_backend": ("llamacpp", "ollama"),
    "cloud_backend": ("openrouter",),
    "retrieval.rerank_backend": ("onnx", "torch"),
    "chroma_mode": ("local", "cloud"),
    "ocr_routing_unit": OCR_ROUTING_UNITS,
}

#: Settings that hold an address; ``omrg.jsonc`` accepts http and https only.
ADDRESS_FIELDS: tuple[str, ...] = (
    "ollama_base_url",
    "llamacpp_chat_url",
    "llamacpp_embed_url",
    "openai_compatible_base_url",
    "azure_doc_intelligence_endpoint",
)
MAX_ADDRESS_CHARS = 2048
ADDRESS_RULE = (
    "The address must be an absolute http or https URL with a host, at most 2,048 "
    "characters, and no user name, password, query or fragment."
)

#: Settings that hold a key. ``omrg.jsonc`` holds a reference to the key, never the key.
SECRET_FIELDS: tuple[str, ...] = (
    *PROVIDER_SECRET_FIELDS,
    "chroma_cloud_api_key",
    "azure_doc_intelligence_key",
)
#: Settings fields that are bookkeeping, not settings. A file key may not name them.
INTERNAL_FIELDS: frozenset[str] = frozenset(
    {
        "config_file_fields",
        "key_file_fields",
        "key_file_paths",
        "keychain_refs",
        "user_config_dir",
        "provider_explicit",
        "setting_sources",
        "vector_store_provenance",
    }
)

#: Keys that only ``omrg.jsonc`` knows (no environment twin): kind, low, high.
FILE_ONLY: dict[str, tuple[str, int, int]] = {
    "web_port": ("int", 1024, 65535),
    "web_max_upload_mib": ("int", 1, 2048),
    "mcp_http_enabled": ("bool", 0, 0),
}


def address_problem(value: str) -> str | None:
    """Return the rule that address *value* breaks, or ``None`` when it is valid.

    The result never contains *value*.
    """
    if not value or len(value) > MAX_ADDRESS_CHARS:
        return ADDRESS_RULE
    if any(ord(ch) <= 0x20 or ord(ch) == 0x7F for ch in value) or "?" in value or "#" in value:
        return ADDRESS_RULE
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018 - raises ValueError on a bad port
    except ValueError:
        return ADDRESS_RULE
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ADDRESS_RULE
    if parts.username is not None or parts.password is not None:
        return ADDRESS_RULE
    return None


def accepted_problem(path: str, value: Any) -> str | None:
    """Return the rule that a choice or address *value* breaks, or ``None``.

    Paths with no choice list and no address rule always pass here (their
    type is checked elsewhere).
    """
    accepted = ACCEPTED.get(path)
    if accepted is not None and value not in accepted:
        return f"The value must be one of: {', '.join(accepted)}."
    if path in ADDRESS_FIELDS and isinstance(value, str):
        return address_problem(value)
    return None


def file_only_problem(key: str, value: Any) -> str | None:
    """Return the rule that a file-only key breaks, or ``None`` when valid."""
    kind, low, high = FILE_ONLY[key]
    if kind == "bool":
        return None if isinstance(value, bool) else "The value must be true or false."
    ok = isinstance(value, int) and not isinstance(value, bool) and low <= value <= high
    return None if ok else f"The value must be a whole number from {low} to {high}."


def provider_of(field: str) -> str:
    """Return the provider name of a secret field (``openrouter_api_key`` gives ``openrouter``)."""
    return field.removesuffix("_api_key").removesuffix("_key")


# ── Provider-selection validation helper ──────────────────────────────


def _validate_provider_value(
    obj: object,
    field: str,
    accepted: tuple[str, ...],
    env_name: str,
) -> None:
    """Strip whitespace, reset empty to default, raise on unrecognised value.

    An empty or whitespace-only value (``SETTING=`` in .env) is how operators
    unset a knob, so it resets to the field's declared default rather than
    raising.  A non-empty value not in ``accepted`` raises ValueError naming
    the offending value and the accepted set.  The stripped value is stored
    so that padded input like ``" auto "`` resolves to ``"auto"``.

    Args:
        obj: The model instance owning the field (``self`` or a nested block).
        field: The field name on ``obj``.
        accepted: The recognised values.
        env_name: The environment variable name for the error message.
    """
    raw = getattr(obj, field)
    if not isinstance(raw, str):
        return
    stripped = raw.strip()
    if not stripped:
        # Empty after strip = operator unset the knob.  Reset to the
        # declared default so "" does not reach runtime code that would
        # probe it (e.g. resolve_sparse_backend on "").
        object.__setattr__(obj, field, type(obj).model_fields[field].default)
        return
    if stripped not in accepted:
        raise ValueError(
            f"{env_name}={raw!r} is not recognised. Accepted values: {', '.join(accepted)}."
        )
    # Store the stripped value so " auto " becomes "auto".
    object.__setattr__(obj, field, stripped)
