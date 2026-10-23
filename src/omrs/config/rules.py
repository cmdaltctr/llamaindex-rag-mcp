"""Value rules shared by ``Settings`` validation and ``omrs.jsonc`` reading.

``omrs.jsonc`` ignores a value that breaks its rule and names the key (task
2.4), so the rules must be checkable before ``Settings`` is built. This
module holds the rules that are not plain types: the accepted names of a
choice field, the shape of an address, and the three file-only keys.

It is a leaf: it imports only pure-data settings models. Messages name a
rule, never a value.
"""

from __future__ import annotations

import re
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

#: Settings that hold an address; ``omrs.jsonc`` accepts http and https only.
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

#: Settings that hold a key. ``omrs.jsonc`` holds a reference to the key, never the key.
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

#: Keys that only ``omrs.jsonc`` knows (no environment twin): kind, low, high.
FILE_ONLY: dict[str, tuple[str, int, int]] = {
    "web_port": ("int", 1024, 65535),
    "web_max_upload_mib": ("int", 1, 2048),
    "mcp_http_enabled": ("bool", 0, 0),
}


#: Names ``pdf_reader`` accepts. ``Settings`` warns and falls back to ``auto`` for
#: any other name, so ``pdf_reader`` is not in :data:`ACCEPTED` (the file reader
#: would then drop a bad value and use the code default instead).
PDF_READER_NAMES: tuple[str, ...] = ("auto", "liteparse", "pdf_inspector", "pypdfium2", "pypdf")

#: Engine names are folder names. ``config/`` cannot import ``integrations/``, so a
#: test pins this to ``integrations.ocr_worker.routes._ENGINE_NAME_RE``.
ENGINE_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
MAX_ENGINE_NAME_CHARS = 64
ENGINE_NAME_RULE = (
    "The engine name must start with a letter or digit, hold only letters, digits, dots, "
    "hyphens and underscores, and be at most 64 characters."
)

#: The keys of Settings > Document reading, in the order of the HTTP contract.
DOCUMENT_READING_KEYS: tuple[str, ...] = (
    "pdf_reader",
    "ocr_fallback_enabled",
    "ocr_fallback_min_confidence",
    "ocr_fallback_page_fraction",
    "ocr_routing_unit",
    "ocr_engine_primary",
    "ocr_engine_fallback",
    "ocr_maths_routing_enabled",
    "ocr_maths_page_fraction",
)
_READING_BOOLEANS = frozenset({"ocr_fallback_enabled", "ocr_maths_routing_enabled"})
_READING_FRACTIONS = frozenset(
    {"ocr_fallback_min_confidence", "ocr_fallback_page_fraction", "ocr_maths_page_fraction"}
)
_READING_ENGINES = frozenset({"ocr_engine_primary", "ocr_engine_fallback"})
BLANK_RULE = "The value must not be blank. Send null to use the default."
FRACTION_RULE = "The value must be a number from 0.0 to 1.0."
BOOL_RULE = "The value must be true or false."


def document_reading_problem(key: str, value: Any) -> str | None:
    """Return the write rule that a document-reading *value* breaks, or ``None``.

    Only a page write runs this check; startup reading does not. The JSON type
    is strict: a boolean key takes ``true`` or ``false``, a fraction key takes a
    number (not a boolean, not text) and a text key takes text. Blank text is
    refused, because the writer would read it as "remove the key". ``None``
    always passes: it removes the key. A key outside the nine passes.

    Args:
        key: The setting key.
        value: The JSON value the page sent.

    Returns:
        The rule, which never holds *value*, or ``None`` when *value* is fine.
    """
    if key not in DOCUMENT_READING_KEYS or value is None:
        return None
    if key in _READING_BOOLEANS:
        return None if isinstance(value, bool) else BOOL_RULE
    if key in _READING_FRACTIONS:
        number = isinstance(value, (int, float)) and not isinstance(value, bool)
        return None if number and 0.0 <= value <= 1.0 else FRACTION_RULE
    if isinstance(value, str) and not value.strip():
        return BLANK_RULE
    if key in _READING_ENGINES:
        ok = isinstance(value, str) and len(value) <= MAX_ENGINE_NAME_CHARS
        return None if ok and re.fullmatch(ENGINE_NAME_PATTERN, value) else ENGINE_NAME_RULE
    accepted = PDF_READER_NAMES if key == "pdf_reader" else ACCEPTED[key]
    return None if value in accepted else f"The value must be one of: {', '.join(accepted)}."


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
