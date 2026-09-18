"""Versioned JSON Lines protocol for the isolated OCR worker.

One JSON object per line, UTF-8, newline-terminated. Standard output
carries protocol messages only; every other byte belongs on standard
error (design D2.3 of change improve-rag-input-quality-5).

Protocol 1.1 (change page-level-ocr-routing, task 4.3) adds exactly one
payload feature: an optional ``pages`` list on the parse request, with
an optional ``pages_markdown`` list on the success response, parallel
to the requested pages, so a page-routing client can place worker text
at each page's position in the merged document. The wire rules:

- a request that carries ``pages`` speaks protocol 1.1;
- a request without ``pages`` speaks 1.0, the minimum version that
  expresses it, so a worker still on 1.0 keeps serving plain requests
  during a rolling upgrade;
- both endpoints accept 1.0 and 1.1 envelopes, and answer in the
  version the request spoke;
- a 1.0 envelope may not carry ``pages`` or ``pages_markdown`` — those
  fields did not exist in 1.0.

This is the WORKER-owned copy. The OMRG project keeps an independent
twin at ``src/omrg/integrations/ocr_worker/protocol.py``; the duplication
is deliberate so neither project imports the other. Tests prove the
two copies agree byte-for-byte on the wire.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .validation import _METADATA_REQUIRED_KEYS as _METADATA_OWNED_KEYS
from .validation import (
    ERR_INVALID_FIELD,
    ERR_MISMATCHED_ID,
    ERR_NON_TERMINAL_TYPE,
    ERR_UNKNOWN_TYPE,
    OUTPUT_SCHEMA_ID,
    OUTPUT_SCHEMA_VERSION,
    ProtocolError,
    _decode_metadata,
    _load_object,
    _normalise_pages,
    _normalise_pages_markdown,
    _require_exact_keys,
    _require_keys,
    _require_non_empty_str,
    _require_protocol_version,
)

# ── Protocol identity ──────────────────────────────────────────────────────

PROTOCOL_VERSION = "1.1"
#: Every version this endpoint accepts on the wire. 1.0 stays valid so a
#: deployment can upgrade the OMRG side and the worker side separately:
#: plain requests keep flowing until the worker catches up.
SUPPORTED_PROTOCOL_VERSIONS = ("1.0", "1.1")
#: The version that introduced the ``pages`` request field and the
#: ``pages_markdown`` response field. An envelope speaking an earlier
#: version may not carry either field.
PAGES_PROTOCOL_VERSION = "1.1"

REQUEST_TYPE_PARSE = "parse"
RESPONSE_TYPE_PARSE_RESULT = "parse_result"
RESPONSE_TYPE_PARSE_ERROR = "parse_error"

MAX_ERROR_MESSAGE_LENGTH = 2000

_REQUEST_KEYS = frozenset({"id", "protocol_version", "type", "pdf_path"})
_SUCCESS_KEYS = frozenset({"id", "protocol_version", "type", "ok", "markdown", "metadata"})
_PAGES_MARKDOWN_KEYS = frozenset({"pages_markdown"})
_FAILURE_KEYS = frozenset({"id", "protocol_version", "type", "ok", "error"})
_ERROR_KEYS = frozenset({"code", "message"})


@dataclass(frozen=True)
class ParseRequest:
    """One parse request envelope; ``type`` is always ``parse``.

    Attributes:
        id: Correlation identifier echoed on the terminal response.
        pdf_path: Path of the PDF the worker must parse.
        pages: 1-based page numbers to parse, in strictly increasing
            order. ``None`` parses the whole document. Present only on
            a 1.1 envelope: a page-listed request is the one payload
            feature 1.1 added.
        protocol_version: Wire protocol version of the envelope.
        type: Envelope type discriminator.
    """

    id: str
    pdf_path: str
    pages: tuple[int, ...] | None = None
    protocol_version: str = "1.0"
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
        pages_markdown: Per-page Markdown, parallel to the requested
            ``pages``, present only when the request carried a page
            list. Lets a page-routing client merge worker text in page
            order; absent means the whole document was parsed.
        protocol_version: Wire protocol version of the envelope.
        type: Envelope type discriminator.
    """

    id: str
    markdown: str
    metadata: dict[str, Any]
    pages_markdown: tuple[str, ...] | None = None
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


def make_request(
    request_id: str, pdf_path: str, *, pages: Sequence[int] | None = None
) -> ParseRequest:
    """Build a parse request envelope.

    The version is the minimum that expresses the payload: ``pages``
    requires 1.1, anything else is fully expressible in 1.0, and
    speaking 1.0 keeps an un-upgraded worker serving the request
    during a rolling upgrade.

    Args:
        request_id: Correlation identifier, non-empty.
        pdf_path: Path of the PDF to parse, non-empty.
        pages: 1-based page numbers to parse, in strictly increasing
            order. ``None`` or omitted parses the whole document.

    Returns:
        The request envelope.

    Raises:
        ValueError: If an argument is empty, or ``pages`` is not a
            non-empty, strictly increasing sequence of positive
            integers.
    """
    if not request_id:
        raise ValueError("request_id must be a non-empty string")
    if not pdf_path:
        raise ValueError("pdf_path must be a non-empty string")
    pages_tuple = None
    if pages is not None:
        try:
            pages_tuple = _normalise_pages(list(pages))
        except ValueError as exc:
            raise ValueError(f"pages: {exc}") from exc
    version = PAGES_PROTOCOL_VERSION if pages_tuple is not None else "1.0"
    return ParseRequest(
        id=request_id, pdf_path=pdf_path, pages=pages_tuple, protocol_version=version
    )


def make_success(
    request_id: str,
    markdown: str,
    *,
    ocr_backend: str,
    page_count: int,
    extra_metadata: Mapping[str, Any] | None = None,
    pages_markdown: Sequence[str] | None = None,
    protocol_version: str = PROTOCOL_VERSION,
) -> ParseSuccess:
    """Build a terminal success envelope carrying the output-schema identity.

    Args:
        request_id: Correlation identifier copied from the request.
        markdown: Structured Markdown emitted by the document pipeline.
        ocr_backend: Backend identifier, for example ``paddleocr-vl``.
        page_count: Number of pages the pipeline processed.
        extra_metadata: Additive diagnostic keys merged into metadata.
            The three protocol-owned keys cannot be overridden.
        pages_markdown: Per-page Markdown, parallel to the requested
            pages. Only valid on a 1.1 envelope; the worker passes the
            request's version so a plain 1.0 request is answered in 1.0.
        protocol_version: Wire version of the envelope; the worker
            passes the version the request spoke.

    Returns:
        The success envelope.

    Raises:
        ValueError: If ``extra_metadata`` collides with a protocol-owned
            metadata key, or ``pages_markdown`` is empty or not a
            sequence of strings, or it is set on a version earlier than
            the pages protocol version.
    """
    if pages_markdown is not None:
        if protocol_version != PAGES_PROTOCOL_VERSION:
            raise ValueError(
                f"pages_markdown requires protocol {PAGES_PROTOCOL_VERSION!r}; "
                f"got {protocol_version!r}"
            )
        pages_tuple = tuple(pages_markdown)
        if not pages_tuple:
            raise ValueError("pages_markdown must be a non-empty sequence of strings")
    else:
        pages_tuple = None
    metadata: dict[str, Any] = dict(extra_metadata) if extra_metadata else {}
    collisions = sorted(_METADATA_OWNED_KEYS & metadata.keys())
    if collisions:
        raise ValueError(f"extra_metadata overrides protocol-owned keys: {', '.join(collisions)}")
    metadata["ocr_backend"] = ocr_backend
    metadata["page_count"] = page_count
    metadata["output_schema"] = {
        "id": OUTPUT_SCHEMA_ID,
        "version": OUTPUT_SCHEMA_VERSION,
    }
    return ParseSuccess(
        id=request_id,
        markdown=markdown,
        metadata=metadata,
        pages_markdown=pages_tuple,
        protocol_version=protocol_version,
    )


def make_failure(
    request_id: str, code: str, message: str, *, protocol_version: str = PROTOCOL_VERSION
) -> ParseFailure:
    """Build a terminal error envelope with a bounded single-line message.

    The message is whitespace-collapsed and truncated so one response
    line can never grow a second line, and tracebacks embedded in the
    input text lose their line structure.

    Args:
        request_id: Correlation identifier copied from the request.
        code: Stable machine-readable error code.
        message: Error description; it is bounded on the way in.
        protocol_version: Wire version of the envelope; the worker
            passes the version the request spoke.

    Returns:
        The error envelope.
    """
    return ParseFailure(
        id=request_id,
        error=ErrorInfo(code=code, message=_bound_message(message)),
        protocol_version=protocol_version,
    )


def _bound_message(message: str) -> str:
    """Collapse whitespace and truncate a message to the wire bound."""
    collapsed = " ".join(message.split())
    if len(collapsed) > MAX_ERROR_MESSAGE_LENGTH:
        collapsed = collapsed[: MAX_ERROR_MESSAGE_LENGTH - 3] + "..."
    return collapsed


# ── Encoding ───────────────────────────────────────────────────────────────
# Page-list normalisation lives in the validation twin module: it is
# decoder validation, shared by the factories above for builder-side
# rejection of what the wire would refuse anyway.


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
        if envelope.pages is not None:
            payload["pages"] = list(envelope.pages)
    elif isinstance(envelope, ParseSuccess):
        payload = {
            "id": envelope.id,
            "markdown": envelope.markdown,
            "metadata": envelope.metadata,
            "ok": True,
            "protocol_version": envelope.protocol_version,
            "type": envelope.type,
        }
        if envelope.pages_markdown is not None:
            payload["pages_markdown"] = list(envelope.pages_markdown)
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
        ProtocolError: On non-JSON input, an unsupported protocol
            version, a non-``parse`` type, missing, extra, or
            invalidly-typed fields, or an invalid ``pages`` list on a
            1.1 envelope.
    """
    payload = _load_object(line)
    context = "request"
    # Optional keys depend on the version: a 1.0 envelope carrying one
    # must fail as an unexpected field.
    carries_pages = payload.get("protocol_version") == PAGES_PROTOCOL_VERSION
    _require_keys(
        payload, _REQUEST_KEYS, frozenset(("pages",)) if carries_pages else frozenset(), context
    )
    _require_protocol_version(payload, context, supported=SUPPORTED_PROTOCOL_VERSIONS)
    envelope_type = payload["type"]
    if envelope_type in (RESPONSE_TYPE_PARSE_RESULT, RESPONSE_TYPE_PARSE_ERROR):
        raise ProtocolError(
            ERR_NON_TERMINAL_TYPE,
            f"response-type envelope on the request stream: {envelope_type!r}",
        )
    if envelope_type != REQUEST_TYPE_PARSE:
        raise ProtocolError(ERR_UNKNOWN_TYPE, f"unknown request type: {envelope_type!r}")
    pages: tuple[int, ...] | None = None
    if "pages" in payload:
        try:
            pages = _normalise_pages(payload["pages"])
        except ValueError as exc:
            raise ProtocolError(ERR_INVALID_FIELD, f"{context}.pages {exc}") from exc
    return ParseRequest(
        id=_require_non_empty_str(payload, "id", context),
        pdf_path=_require_non_empty_str(payload, "pdf_path", context),
        pages=pages,
        protocol_version=payload["protocol_version"],
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
        ProtocolError: On non-JSON input, an unsupported protocol
            version, an unknown or non-terminal type, a contradicted
            ``ok`` flag, an output-schema mismatch, missing, extra, or
            invalidly-typed fields, a mismatched request identifier, or
            an invalid ``pages_markdown`` list on a 1.1 envelope.
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
    version = payload.get("protocol_version")
    if envelope_type == RESPONSE_TYPE_PARSE_RESULT:
        optional = _PAGES_MARKDOWN_KEYS if version == PAGES_PROTOCOL_VERSION else frozenset()
        _require_keys(payload, _SUCCESS_KEYS, optional, context)
    else:
        _require_exact_keys(payload, _FAILURE_KEYS, context)
    _require_protocol_version(payload, context, supported=SUPPORTED_PROTOCOL_VERSIONS)
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
    pages_markdown: tuple[str, ...] | None = None
    if "pages_markdown" in payload:
        try:
            pages_markdown = _normalise_pages_markdown(payload["pages_markdown"])
        except ValueError as exc:
            raise ProtocolError(ERR_INVALID_FIELD, f"{context}.pages_markdown {exc}") from exc
    return ParseSuccess(
        id=request_id,
        markdown=markdown,
        metadata=_decode_metadata(payload["metadata"], context),
        pages_markdown=pages_markdown,
        protocol_version=payload["protocol_version"],
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
    return ParseFailure(
        id=request_id,
        error=ErrorInfo(code=code, message=message),
        protocol_version=payload["protocol_version"],
    )


# Names re-exported from the validation twin stay importable from here;
# no importer should have to know the split happened.
