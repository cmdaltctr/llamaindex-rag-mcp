"""Versioned JSON Lines protocol for the isolated OCR worker.

One JSON object per line, UTF-8, newline-terminated. Standard output
carries protocol messages only; every other byte belongs on standard
error (design D2.3 of change improve-rag-input-quality-5).

This is the OMRG-owned twin. The worker project keeps an independent
copy at ``ocr-worker/src/omrg_ocr_worker/protocol.py``; the duplication
is deliberate so neither project imports the other. Tests prove the
two copies agree byte-for-byte on the wire.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

# ── Protocol identity ──────────────────────────────────────────────────────

PROTOCOL_VERSION = "1.0"
OUTPUT_SCHEMA_ID = "omrg.ocr.parse_output"
OUTPUT_SCHEMA_VERSION = "1"

REQUEST_TYPE_PARSE = "parse"
RESPONSE_TYPE_PARSE_RESULT = "parse_result"
RESPONSE_TYPE_PARSE_ERROR = "parse_error"

MAX_ERROR_MESSAGE_LENGTH = 2000

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

_REQUEST_KEYS = frozenset({"id", "protocol_version", "type", "pdf_path"})
_SUCCESS_KEYS = frozenset({"id", "protocol_version", "type", "ok", "markdown", "metadata"})
_FAILURE_KEYS = frozenset({"id", "protocol_version", "type", "ok", "error"})
_ERROR_KEYS = frozenset({"code", "message"})
_METADATA_REQUIRED_KEYS = frozenset({"ocr_backend", "page_count", "output_schema"})


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


@dataclass(frozen=True)
class ParseRequest:
    """One parse request envelope; ``type`` is always ``parse``.

    Attributes:
        id: Correlation identifier echoed on the terminal response.
        pdf_path: Path of the PDF the worker must parse.
        protocol_version: Wire protocol version of the envelope.
        type: Envelope type discriminator.
    """

    id: str
    pdf_path: str
    protocol_version: str = PROTOCOL_VERSION
    type: str = REQUEST_TYPE_PARSE


@dataclass(frozen=True)
class ErrorInfo:
    """Bounded error body of a terminal ``parse_error`` envelope.

    Attributes:
        code: Stable machine-readable error code from the worker.
        message: Single-line, length-bounded description. It never
            carries a traceback.
    """

    code: str
    message: str


@dataclass(frozen=True)
class ParseSuccess:
    """Terminal success envelope; ``type`` is always ``parse_result``.

    Attributes:
        id: Correlation identifier copied from the request.
        markdown: Structured Markdown emitted by the document pipeline.
        metadata: Diagnostics including ``ocr_backend``,
            ``page_count``, and the ``output_schema`` identity.
        protocol_version: Wire protocol version of the envelope.
        type: Envelope type discriminator.
    """

    id: str
    markdown: str
    metadata: dict[str, Any]
    protocol_version: str = PROTOCOL_VERSION
    type: str = RESPONSE_TYPE_PARSE_RESULT


@dataclass(frozen=True)
class ParseFailure:
    """Terminal error envelope; ``type`` is always ``parse_error``.

    Attributes:
        id: Correlation identifier copied from the request.
        error: Bounded structured error body.
        protocol_version: Wire protocol version of the envelope.
        type: Envelope type discriminator.
    """

    id: str
    error: ErrorInfo
    protocol_version: str = PROTOCOL_VERSION
    type: str = RESPONSE_TYPE_PARSE_ERROR


ParseResponse = ParseSuccess | ParseFailure


# ── Envelope factories ─────────────────────────────────────────────────────


def make_request(request_id: str, pdf_path: str) -> ParseRequest:
    """Build a parse request envelope.

    Args:
        request_id: Correlation identifier, non-empty.
        pdf_path: Path of the PDF to parse, non-empty.

    Returns:
        The request envelope.

    Raises:
        ValueError: If either argument is empty.
    """
    if not request_id:
        raise ValueError("request_id must be a non-empty string")
    if not pdf_path:
        raise ValueError("pdf_path must be a non-empty string")
    return ParseRequest(id=request_id, pdf_path=pdf_path)


def make_success(
    request_id: str,
    markdown: str,
    *,
    ocr_backend: str,
    page_count: int,
    extra_metadata: Mapping[str, Any] | None = None,
) -> ParseSuccess:
    """Build a terminal success envelope carrying the output-schema identity.

    Args:
        request_id: Correlation identifier copied from the request.
        markdown: Structured Markdown emitted by the document pipeline.
        ocr_backend: Backend identifier, for example ``paddleocr-vl``.
        page_count: Number of pages the pipeline processed.
        extra_metadata: Additive diagnostic keys merged into metadata.
            The three protocol-owned keys cannot be overridden.

    Returns:
        The success envelope.

    Raises:
        ValueError: If ``extra_metadata`` collides with a protocol-owned
            metadata key.
    """
    metadata: dict[str, Any] = dict(extra_metadata) if extra_metadata else {}
    collisions = sorted(_METADATA_REQUIRED_KEYS & metadata.keys())
    if collisions:
        raise ValueError(f"extra_metadata overrides protocol-owned keys: {', '.join(collisions)}")
    metadata["ocr_backend"] = ocr_backend
    metadata["page_count"] = page_count
    metadata["output_schema"] = {
        "id": OUTPUT_SCHEMA_ID,
        "version": OUTPUT_SCHEMA_VERSION,
    }
    return ParseSuccess(id=request_id, markdown=markdown, metadata=metadata)


def make_failure(request_id: str, code: str, message: str) -> ParseFailure:
    """Build a terminal error envelope with a bounded single-line message.

    The message is whitespace-collapsed and truncated so one response
    line can never grow a second line, and tracebacks embedded in the
    input text lose their line structure.

    Args:
        request_id: Correlation identifier copied from the request.
        code: Stable machine-readable error code.
        message: Error description; it is bounded on the way in.

    Returns:
        The error envelope.
    """
    return ParseFailure(
        id=request_id,
        error=ErrorInfo(code=code, message=_bound_message(message)),
    )


def _bound_message(message: str) -> str:
    """Collapse whitespace and truncate a message to the wire bound."""
    collapsed = " ".join(message.split())
    if len(collapsed) > MAX_ERROR_MESSAGE_LENGTH:
        collapsed = collapsed[: MAX_ERROR_MESSAGE_LENGTH - 3] + "..."
    return collapsed


# ── Encoding ───────────────────────────────────────────────────────────────


def encode_line(envelope: ParseRequest | ParseResponse) -> str:
    """Serialise one envelope to a single JSON line without its newline.

    Key order is canonical (sorted) so the two independent protocol
    copies produce byte-identical lines for equal envelopes.

    Args:
        envelope: Request, success, or failure envelope.

    Returns:
        The JSON Lines payload for the envelope.

    Raises:
        TypeError: If the value is not a protocol envelope.
    """
    if isinstance(envelope, ParseRequest):
        payload: dict[str, Any] = {
            "id": envelope.id,
            "pdf_path": envelope.pdf_path,
            "protocol_version": envelope.protocol_version,
            "type": envelope.type,
        }
    elif isinstance(envelope, ParseSuccess):
        payload = {
            "id": envelope.id,
            "markdown": envelope.markdown,
            "metadata": envelope.metadata,
            "ok": True,
            "protocol_version": envelope.protocol_version,
            "type": envelope.type,
        }
    elif isinstance(envelope, ParseFailure):
        payload = {
            "error": {"code": envelope.error.code, "message": envelope.error.message},
            "id": envelope.id,
            "ok": False,
            "protocol_version": envelope.protocol_version,
            "type": envelope.type,
        }
    else:
        raise TypeError(f"unsupported envelope type: {type(envelope).__name__}")
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ── Decoding ───────────────────────────────────────────────────────────────


def decode_request_line(line: str) -> ParseRequest:
    """Decode one request line from the worker's standard input.

    Args:
        line: One input line, with or without its trailing newline.

    Returns:
        The parsed request envelope.

    Raises:
        ProtocolError: On non-JSON input, wrong protocol version, a
            non-``parse`` type, or missing, extra, or invalidly-typed
            fields.
    """
    payload = _load_object(line)
    context = "request"
    _require_exact_keys(payload, _REQUEST_KEYS, context)
    _require_protocol_version(payload, context)
    envelope_type = payload["type"]
    if envelope_type in (RESPONSE_TYPE_PARSE_RESULT, RESPONSE_TYPE_PARSE_ERROR):
        raise ProtocolError(
            ERR_NON_TERMINAL_TYPE,
            f"response-type envelope on the request stream: {envelope_type!r}",
        )
    if envelope_type != REQUEST_TYPE_PARSE:
        raise ProtocolError(ERR_UNKNOWN_TYPE, f"unknown request type: {envelope_type!r}")
    return ParseRequest(
        id=_require_non_empty_str(payload, "id", context),
        pdf_path=_require_non_empty_str(payload, "pdf_path", context),
    )


def decode_response_line(
    line: str, *, expected_id: str | None = None
) -> ParseSuccess | ParseFailure:
    """Decode one terminal response line from the worker's standard output.

    Args:
        line: One output line, with or without its trailing newline.
        expected_id: When set, a response carrying a different request
            identifier is rejected as a correlation failure.

    Returns:
        The terminal success or failure envelope.

    Raises:
        ProtocolError: On non-JSON input, wrong protocol version, an
            unknown or non-terminal type, a contradicted ``ok`` flag,
            an output-schema mismatch, missing, extra, or invalidly
            typed fields, or a mismatched request identifier.
    """
    payload = _load_object(line)
    context = "response"
    envelope_type = payload.get("type")
    if envelope_type not in (RESPONSE_TYPE_PARSE_RESULT, RESPONSE_TYPE_PARSE_ERROR):
        if envelope_type == REQUEST_TYPE_PARSE:
            raise ProtocolError(
                ERR_NON_TERMINAL_TYPE, "request-type envelope on the response stream"
            )
        raise ProtocolError(ERR_UNKNOWN_TYPE, f"unknown response type: {envelope_type!r}")
    expected_keys = _SUCCESS_KEYS if envelope_type == RESPONSE_TYPE_PARSE_RESULT else _FAILURE_KEYS
    _require_exact_keys(payload, expected_keys, context)
    _require_protocol_version(payload, context)
    request_id = _require_non_empty_str(payload, "id", context)
    if expected_id is not None and request_id != expected_id:
        raise ProtocolError(
            ERR_MISMATCHED_ID,
            f"response id {request_id!r} does not match expected {expected_id!r}",
        )
    if envelope_type == RESPONSE_TYPE_PARSE_RESULT:
        return _decode_success(payload, context, request_id)
    return _decode_failure(payload, context, request_id)


def _decode_success(payload: dict[str, Any], context: str, request_id: str) -> ParseSuccess:
    """Decode a validated ``parse_result`` payload body."""
    if payload["ok"] is not True:
        raise ProtocolError(
            ERR_INVALID_FIELD, f"{context}.ok must be true for {RESPONSE_TYPE_PARSE_RESULT}"
        )
    markdown = payload["markdown"]
    if not isinstance(markdown, str):
        raise ProtocolError(ERR_INVALID_FIELD, f"{context}.markdown must be a string")
    return ParseSuccess(
        id=request_id,
        markdown=markdown,
        metadata=_decode_metadata(payload["metadata"], context),
    )


def _decode_failure(payload: dict[str, Any], context: str, request_id: str) -> ParseFailure:
    """Decode a validated ``parse_error`` payload body."""
    if payload["ok"] is not False:
        raise ProtocolError(
            ERR_INVALID_FIELD,
            f"{context}.ok must be false for {RESPONSE_TYPE_PARSE_ERROR}",
        )
    error = payload["error"]
    if not isinstance(error, dict):
        raise ProtocolError(ERR_INVALID_FIELD, f"{context}.error must be an object")
    _require_exact_keys(error, _ERROR_KEYS, f"{context}.error")
    code = error["code"]
    if not isinstance(code, str) or not code:
        raise ProtocolError(ERR_INVALID_FIELD, f"{context}.error.code must be a non-empty string")
    message = error["message"]
    if not isinstance(message, str):
        raise ProtocolError(ERR_INVALID_FIELD, f"{context}.error.message must be a string")
    return ParseFailure(id=request_id, error=ErrorInfo(code=code, message=message))


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
    missing = sorted(expected - payload.keys())
    if missing:
        raise ProtocolError(ERR_MISSING_FIELD, f"{context} is missing fields: {', '.join(missing)}")
    extra = sorted(payload.keys() - expected)
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


def _require_protocol_version(payload: dict[str, Any], context: str) -> None:
    """Reject envelopes speaking any other protocol version."""
    version = payload["protocol_version"]
    if version != PROTOCOL_VERSION:
        raise ProtocolError(
            ERR_UNSUPPORTED_PROTOCOL_VERSION,
            f"{context}.protocol_version is {version!r}; this endpoint speaks {PROTOCOL_VERSION!r}",
        )
