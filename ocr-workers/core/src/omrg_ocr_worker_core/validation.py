"""Wire-validation helpers for the OCR worker JSON Lines protocol.

Split out of ``protocol.py`` when the 500-line ceiling caught up with it
(change page-level-ocr-routing, task 4.3). This is the WORKER-owned copy;
the OMRG project keeps an independent twin at
``src/omrg/integrations/ocr_worker/validation.py``. The duplication is
deliberate so neither project imports the other, and the protocol tests
prove the copies agree on codes, schema identity and behaviour.

Holds the parts of the contract both decoders lean on: the violation
codes, the output-schema identity, the typed protocol error, and the
generic payload-validation helpers. The envelope types, the factories,
the protocol-version constants and the encode/decode entry points stay
in ``protocol.py``, which re-exports every public name here so existing
importers are unaffected.
"""

from __future__ import annotations

import json
from typing import Any

# ── Output schema identity ─────────────────────────────────────────────────

OUTPUT_SCHEMA_ID = "omrg.ocr.parse_output"
OUTPUT_SCHEMA_VERSION = "1"

# ── Protocol violation codes ───────────────────────────────────────────────

ERR_INVALID_JSON = "invalid_json"
ERR_UNSUPPORTED_PROTOCOL_VERSION = "unsupported_protocol_version"
ERR_MISSING_FIELD = "missing_field"
ERR_INVALID_FIELD = "invalid_field"
ERR_UNEXPECTED_FIELD = "unexpected_field"
ERR_NON_TERMINAL_TYPE = "non_terminal_type"
ERR_UNKNOWN_TYPE = "unknown_type"
ERR_MISMATCHED_ID = "mismatched_id"
ERR_OUTPUT_SCHEMA_MISMATCH = "output_schema_mismatch"


class ProtocolError(Exception):
    """A JSON Lines protocol violation detected while decoding a line.

    Attributes:
        code: Stable machine-readable violation code (``ERR_*``).
        message: Human-readable description of the violation.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


def _load_object(line: str) -> dict[str, Any]:
    """Parse one line as a JSON object or raise a protocol error."""
    text = line.strip()
    if not text:
        raise ProtocolError(ERR_INVALID_JSON, "line is empty")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError(ERR_INVALID_JSON, f"line is not valid JSON: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ProtocolError(ERR_INVALID_JSON, "line is not a JSON object")
    return parsed


def _require_exact_keys(payload: dict[str, Any], expected: frozenset[str], context: str) -> None:
    """Reject payloads with missing or unexpected envelope fields."""
    _require_keys(payload, expected, frozenset(), context)


def _require_keys(
    payload: dict[str, Any],
    required: frozenset[str],
    optional: frozenset[str],
    context: str,
) -> None:
    """Reject payloads with missing fields or fields outside the two sets.

    Protocol 1.1 made the page fields optional on their version: a 1.1
    envelope MAY carry ``pages`` / ``pages_markdown`` and a 1.0 envelope
    may not. Expressing optionality as a second key set keeps the strict
    unknown-field rejection while allowing absence.
    """
    missing = sorted(required - payload.keys())
    if missing:
        raise ProtocolError(ERR_MISSING_FIELD, f"{context} is missing fields: {', '.join(missing)}")
    extra = sorted(payload.keys() - required - optional)
    if extra:
        raise ProtocolError(
            ERR_UNEXPECTED_FIELD, f"{context} has unexpected fields: {', '.join(extra)}"
        )


def _require_non_empty_str(payload: dict[str, Any], key: str, context: str) -> str:
    """Return ``payload[key]`` if it is a non-empty string."""
    value = payload[key]
    if not isinstance(value, str) or not value:
        raise ProtocolError(ERR_INVALID_FIELD, f"{context}.{key} must be a non-empty string")
    return value


def _normalise_pages(raw: Any) -> tuple[int, ...]:
    """Return *raw* as a page tuple, or raise ``ValueError`` naming the rule.

    The page list is non-empty, positive, and strictly increasing:
    1-based document order, no repeats, no zero — a page number the
    decoder accepts is a page the worker will parse. The factories use
    the same rule, so a builder-side rejection always matches what the
    wire would refuse anyway.
    """
    if not isinstance(raw, list) or not raw:
        raise ValueError("must be a non-empty list")
    pages: list[int] = []
    for value in raw:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("entries must be positive integers")
        if pages and value <= pages[-1]:
            raise ValueError("must be strictly increasing")
        pages.append(value)
    return tuple(pages)


def _normalise_pages_markdown(raw: Any) -> tuple[str, ...]:
    """Return *raw* as a per-page Markdown tuple, or raise ``ValueError``.

    A non-empty list of strings; an entry may be an empty string, since
    a page the pipeline could not read still occupies its slot.
    """
    if not isinstance(raw, list) or not raw or not all(isinstance(v, str) for v in raw):
        raise ValueError("must be a non-empty list of strings")
    return tuple(raw)


def _require_protocol_version(
    payload: dict[str, Any], context: str, *, supported: tuple[str, ...]
) -> None:
    """Reject envelopes speaking any unsupported protocol version.

    The supported set arrives from the caller because the version
    constants are protocol identity, which stays in ``protocol.py``;
    accepting a set rather than one value is what lets a 1.1 endpoint
    keep serving 1.0 envelopes during a rolling upgrade.
    """
    version = payload["protocol_version"]
    if version not in supported:
        raise ProtocolError(
            ERR_UNSUPPORTED_PROTOCOL_VERSION,
            f"{context}.protocol_version is {version!r}; this endpoint speaks "
            f"{'/'.join(supported)}",
        )


#: Metadata keys the success envelope itself owns (design D2.4/D2.5).
_METADATA_REQUIRED_KEYS = frozenset({"ocr_backend", "page_count", "output_schema"})


def _decode_metadata(raw: Any, context: str) -> dict[str, Any]:
    """Decode and validate the metadata object of a success envelope.

    The three protocol-owned keys are mandatory; additive diagnostic
    keys are preserved untouched.
    """
    if not isinstance(raw, dict):
        raise ProtocolError(ERR_INVALID_FIELD, f"{context}.metadata must be an object")
    missing = sorted(_METADATA_REQUIRED_KEYS - raw.keys())
    if missing:
        raise ProtocolError(
            ERR_MISSING_FIELD, f"{context}.metadata is missing fields: {', '.join(missing)}"
        )
    backend = raw["ocr_backend"]
    if not isinstance(backend, str) or not backend:
        raise ProtocolError(
            ERR_INVALID_FIELD, f"{context}.metadata.ocr_backend must be a non-empty string"
        )
    page_count = raw["page_count"]
    if isinstance(page_count, bool) or not isinstance(page_count, int) or page_count < 0:
        raise ProtocolError(
            ERR_INVALID_FIELD,
            f"{context}.metadata.page_count must be a non-negative integer",
        )
    schema = raw["output_schema"]
    if not isinstance(schema, dict):
        raise ProtocolError(
            ERR_INVALID_FIELD, f"{context}.metadata.output_schema must be an object"
        )
    if schema.get("id") != OUTPUT_SCHEMA_ID or schema.get("version") != OUTPUT_SCHEMA_VERSION:
        raise ProtocolError(
            ERR_OUTPUT_SCHEMA_MISMATCH,
            f"output schema {schema.get('id')!r}/{schema.get('version')!r} does not "
            f"match {OUTPUT_SCHEMA_ID!r}/{OUTPUT_SCHEMA_VERSION!r}",
        )
    return dict(raw)
