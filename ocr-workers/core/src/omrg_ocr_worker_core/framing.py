"""The worker entry loop: JSON Lines framing over standard I/O.

Framing contract (design D2.3 of change improve-rag-input-quality-5):

- standard input: one request object per line, UTF-8;
- standard output: exactly one terminal response line per accepted
  request, and nothing else, ever;
- standard error: every log, warning, and traceback.

The loop serves the one engine this environment registers
(:func:`omrg_ocr_worker_core.engine.load_engine`). Every engine speaks
this loop and this protocol; an engine supplies only ``parse``.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from .engine import DocumentMarkdown, EngineLoadError, OcrEngine, WorkerParseError, load_engine
from .pages import check_pages
from .protocol import (
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    ParseFailure,
    ParseRequest,
    ParseSuccess,
    ProtocolError,
    decode_request_line,
    encode_line,
    make_failure,
    make_success,
)

logger = logging.getLogger("omrg_ocr_worker_core")
_logger_configured = False

#: Exit status when the environment registers zero or several engines.
EXIT_NO_ENGINE = 3  # same value as capabilities.EXIT_NO_ENGINE


def parse_document(engine: OcrEngine, request: ParseRequest) -> ParseSuccess:
    """Run one request through *engine* and build the success envelope.

    Args:
        engine: The loaded engine.
        request: The decoded parse request.

    Returns:
        The terminal success envelope.

    Raises:
        WorkerParseError: If the PDF is unusable, a page is out of
            range, the engine returns the wrong number of pages, or a
            whole-document request yields no Markdown.
    """
    pdf_path = Path(request.pdf_path)
    if not pdf_path.is_file():
        raise WorkerParseError("invalid_pdf_path", f"no readable PDF at {request.pdf_path}")
    pages = request.pages
    if pages is not None:
        check_pages(pdf_path, pages)
    result = _run_engine(engine, pdf_path, pages)
    if pages is None and not result.markdown.strip():
        raise WorkerParseError("empty_markdown", f"{engine.name} produced empty Markdown")
    pipeline_identity, pipeline_revision = engine.pipeline
    model_identity, model_revision = engine.model
    return make_success(
        request.id,
        result.markdown,
        ocr_backend=engine.name,
        page_count=result.page_count,
        extra_metadata={
            "reader": engine.name,
            "ocr_used": True,
            "pipeline": pipeline_identity,
            "pipeline_revision": pipeline_revision,
            "model": model_identity,
            "model_revision": model_revision,
        },
        pages_markdown=result.pages_markdown,
        protocol_version=request.protocol_version,
    )


def _run_engine(
    engine: OcrEngine, pdf_path: Path, pages: tuple[int, ...] | None
) -> DocumentMarkdown:
    """Call the engine and normalise its answer to one shape."""
    assemble = getattr(engine, "parse_document", None)
    if callable(assemble):
        result = assemble(pdf_path, pages)
        if not isinstance(result, DocumentMarkdown):
            raise WorkerParseError("engine_contract", "parse_document must return DocumentMarkdown")
        if pages is not None and (
            result.pages_markdown is None or len(result.pages_markdown) != len(pages)
        ):
            raise WorkerParseError(
                "page_selection_mismatch",
                f"engine returned per-page Markdown not parallel to {len(pages)} page(s)",
            )
        return result
    page_texts = engine.parse(pdf_path, pages)
    if not isinstance(page_texts, list) or not all(isinstance(t, str) for t in page_texts):
        raise WorkerParseError("engine_contract", "parse must return a list of strings")
    if pages is not None and len(page_texts) != len(pages):
        raise WorkerParseError(
            "page_selection_mismatch",
            f"engine returned {len(page_texts)} page(s) for {len(pages)} requested page(s)",
        )
    markdown = "\n\n".join(text.strip() for text in page_texts if text.strip())
    return DocumentMarkdown(
        markdown=markdown,
        pages_markdown=tuple(page_texts) if pages is not None else None,
        page_count=len(page_texts),
    )


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001 - conventional signature
    """Serve parse requests over standard input and output.

    Returns:
        0 on clean end of input, 2 on an uncorrelatable request line,
        and :data:`EXIT_NO_ENGINE` when the environment does not register
        exactly one engine (no request is read then).
    """
    _configure_logging()
    try:
        engine = load_engine()
    except EngineLoadError as exc:
        logger.error("no usable OCR engine; refusing parse requests: %s", exc)
        return EXIT_NO_ENGINE
    logger.info("omrg OCR worker starting: engine %s, protocol %s", engine.name, PROTOCOL_VERSION)
    return serve(engine)


def serve(engine: OcrEngine) -> int:
    """Run the framing loop for *engine* until standard input closes."""
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
        _write_response(handle_request(engine, request))
    logger.info("omrg OCR worker input closed; stopping")
    return 0


def handle_request(engine: OcrEngine, request: ParseRequest) -> ParseSuccess | ParseFailure:
    """Run one request, converting every failure into a terminal envelope.

    The worker never raises out of a request it has accepted: the loop
    must answer with exactly one terminal line whatever the engine does.
    """
    try:
        return parse_document(engine, request)
    except WorkerParseError as exc:
        logger.warning("parse failed for %s: %s", request.id, exc.message)
        return make_failure(
            request.id, exc.code, exc.message, protocol_version=request.protocol_version
        )
    except Exception as exc:  # noqa: BLE001 - the loop must survive anything
        logger.exception("unhandled error while parsing %s", request.id)
        return make_failure(
            request.id,
            "internal_error",
            f"{type(exc).__name__}: {exc}",
            protocol_version=request.protocol_version,
        )


def _respond_to_recoverable_line(line: str, error: ProtocolError) -> bool:
    """Answer an invalid request line when its identifier is recoverable.

    A request carrying the wrong protocol version or an unexpected
    field still names a request, so it receives a correlated error
    envelope. A line with no recoverable identifier breaks the stream.

    Returns:
        True when a terminal error envelope was written; False when
        the line cannot be correlated.
    """
    try:
        payload: Any = json.loads(line)
    except json.JSONDecodeError:
        return False
    if not isinstance(payload, dict):
        return False
    request_id = payload.get("id")
    if not isinstance(request_id, str) or not request_id:
        return False
    # Answer in the version the broken line claimed, when that version
    # is one this endpoint speaks, so an old client can still read the
    # error; anything else gets this endpoint's own version.
    claimed = payload.get("protocol_version")
    version = (
        claimed
        if isinstance(claimed, str) and claimed in SUPPORTED_PROTOCOL_VERSIONS
        else PROTOCOL_VERSION
    )
    _write_response(
        make_failure(
            request_id,
            "invalid_request",
            f"{error.code}: {error.message}",
            protocol_version=version,
        )
    )
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
