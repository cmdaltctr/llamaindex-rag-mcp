"""OCR worker entry loop: JSON Lines framing over standard I/O.

Framing contract (design D2.3 of change improve-rag-input-quality-5):

- standard input: one request object per line, UTF-8;
- standard output: exactly one terminal response line per accepted
  request, and nothing else, ever;
- standard error: every log, warning, and traceback.

The parse seam :func:`parse_document` is the single place the isolated
environment's Paddle packages enter, and it is the function tests
stub. Everything around it — validation, error conversion, framing,
logging — is Paddle-free and testable in the main environment.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from .protocol import (
    PROTOCOL_VERSION,
    ParseFailure,
    ParseRequest,
    ParseSuccess,
    ProtocolError,
    decode_request_line,
    encode_line,
    make_failure,
)

WORKER_BACKEND = "paddleocr-vl"

logger = logging.getLogger("omrg_ocr_worker")
_logger_configured = False


class WorkerParseError(Exception):
    """A parse failure that must surface as one terminal error envelope.

    Attributes:
        code: Stable machine-readable error code.
        message: Human-readable description; the envelope bounds it.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ── Parse seam ─────────────────────────────────────────────────────────────


def parse_document(request: ParseRequest) -> ParseSuccess:
    """Run the document pipeline for one request (the parse seam).

    Tests stub this function; the framing around it is the part under
    test in a Paddle-free environment.

    Args:
        request: The decoded parse request.

    Returns:
        The terminal success envelope carrying structured Markdown.

    Raises:
        WorkerParseError: If the referenced PDF is unusable or the
            pipeline cannot run.
    """
    pdf_path = Path(request.pdf_path)
    if not pdf_path.is_file():
        raise WorkerParseError("invalid_pdf_path", f"no readable PDF at {request.pdf_path}")
    return _run_document_pipeline(pdf_path)


def _run_document_pipeline(pdf_path: Path) -> ParseSuccess:
    """Invoke the PaddleOCR-VL document pipeline inside the worker env.

    The lazy import is load-bearing. This module must stay importable
    and testable in a Paddle-free environment, so the Paddle packages
    are only ever touched inside this function, never at module level.
    When wired with the provisioned smoke test (task 2.15) the body
    follows the official API shape::

        from paddleocr import PaddleOCRVL  # lazy, worker-env only
        pipeline = PaddleOCRVL()
        results = pipeline.predict(input=str(pdf_path))

    Args:
        pdf_path: The validated PDF path from the request.

    Returns:
        The assembled success envelope with pipeline metadata.

    Raises:
        WorkerParseError: Always in this wave, naming the pending
            wiring, so a real pipeline call is never faked.
    """
    raise WorkerParseError(
        "pipeline_not_wired",
        "the PaddleOCR-VL pipeline call is completed with the provisioned "
        "smoke test (change task 2.15); this build carries protocol "
        "framing only",
    )


# ── Entry loop ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Run the worker loop over standard input and output.

    Reads one request line at a time and writes exactly one terminal
    response line per accepted request. A request line that cannot be
    correlated (no parsable identifier) ends the process with a
    failure status: the input framing is broken, and continuing would
    desynchronise the stream.

    Args:
        argv: Unused; present for a conventional entry signature.

    Returns:
        The process exit status: 0 on clean end of input, 2 on an
        uncorrelatable request line.
    """
    _configure_logging()
    logger.info("omrg-ocr-worker starting (protocol %s)", PROTOCOL_VERSION)
    for raw_line in sys.stdin:
        line = raw_line.rstrip("\r\n")
        if not line.strip():
            continue
        try:
            request = decode_request_line(line)
        except ProtocolError as exc:
            if not _respond_to_recoverable_line(line, exc):
                logger.error("uncorrelatable request line; stopping: %s", exc.message)
                return 2
            continue
        _write_response(_handle_request(request))
    logger.info("omrg-ocr-worker input closed; stopping")
    return 0


def _handle_request(request: ParseRequest) -> ParseSuccess | ParseFailure:
    """Run one request, converting every failure into a terminal envelope.

    The worker never raises out of a request it has accepted: the loop
    must answer with exactly one terminal line whatever the seam does.
    """
    try:
        return parse_document(request)
    except WorkerParseError as exc:
        logger.warning("parse failed for %s: %s", request.id, exc.message)
        return make_failure(request.id, exc.code, exc.message)
    except Exception as exc:  # noqa: BLE001 - the loop must survive anything
        logger.exception("unhandled error while parsing %s", request.id)
        return make_failure(request.id, "internal_error", f"{type(exc).__name__}: {exc}")


def _respond_to_recoverable_line(line: str, error: ProtocolError) -> bool:
    """Answer an invalid request line when its identifier is recoverable.

    A request carrying the wrong protocol version or an unexpected
    field still names a request, so it receives a correlated error
    envelope. A line with no recoverable identifier breaks the stream.

    Args:
        line: The raw request line that failed validation.
        error: The protocol violation that rejected it.

    Returns:
        True when a terminal error envelope was written; False when
        the line cannot be correlated.
    """
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    request_id = payload.get("id")
    if not isinstance(request_id, str) or not request_id:
        return False
    _write_response(make_failure(request_id, "invalid_request", f"{error.code}: {error.message}"))
    return True


def _write_response(envelope: ParseSuccess | ParseFailure) -> None:
    """Write exactly one terminal response line and flush it."""
    sys.stdout.write(encode_line(envelope) + "\n")
    sys.stdout.flush()


def _configure_logging() -> None:
    """Route worker logs to standard error only, once per process."""
    global _logger_configured
    if _logger_configured:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    _logger_configured = True
