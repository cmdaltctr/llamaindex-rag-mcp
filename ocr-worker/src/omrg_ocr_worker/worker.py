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
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from .protocol import (
    PROTOCOL_VERSION,
    ParseFailure,
    ParseRequest,
    ParseSuccess,
    ProtocolError,
    decode_request_line,
    encode_line,
    make_failure,
    make_success,
)

WORKER_BACKEND = "paddleocr-vl"
WORKER_DIR = Path(__file__).resolve().parents[2]
MODEL_CACHE_DIR = WORKER_DIR / ".model-cache"

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
    return _run_document_pipeline(pdf_path, request.id)


#: Process-wide pipeline singleton (design D2.2): the long-lived worker
#: loads the document pipeline and model once, then reuses them for
#: every later OCR-required file it accepts.
_PIPELINE_SINGLETON: Any | None = None


def _reset_pipeline_cache() -> None:
    """Drop the cached pipeline.

    Production code never calls this; tests use it to isolate module
    state without importing Paddle.
    """
    global _PIPELINE_SINGLETON
    _PIPELINE_SINGLETON = None


def _apply_worker_cache_env() -> None:
    """Force both Paddle cache variables to the worker-local directory.

    Assignment, not ``setdefault``: an inherited value pointing outside
    ``ocr-worker/`` would direct model reads and downloads to a path
    outside the worker-owned, git-ignored cache. Both variables are set
    before any Paddle import because PaddleOCR and PaddleX read them at
    import and initialisation time.
    """
    os.environ["PADDLE_OCR_BASE_DIR"] = str(MODEL_CACHE_DIR)
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(MODEL_CACHE_DIR)


def _load_pipeline() -> Any:
    """Return the process-wide PaddleOCR-VL pipeline, constructing it once.

    The lazy import is load-bearing. This module must stay importable
    and testable in a Paddle-free environment, so the Paddle packages
    are only ever touched inside this function, never at module level.

    Raises:
        WorkerParseError: If PaddleOCR-VL is unavailable in this
            environment. No cache entry is created, so a later request
            retries the import.
    """
    global _PIPELINE_SINGLETON
    _apply_worker_cache_env()
    if _PIPELINE_SINGLETON is None:
        try:
            from paddleocr import PaddleOCRVL  # lazy, worker-env only
        except (ImportError, ModuleNotFoundError) as exc:
            raise WorkerParseError(
                "paddle_unavailable", f"PaddleOCR-VL import failed: {exc}"
            ) from exc
        _PIPELINE_SINGLETON = PaddleOCRVL(
            device="cpu",
            use_ocr_for_image_block=True,
            format_block_content=True,
        )
    return _PIPELINE_SINGLETON


def _run_document_pipeline(pdf_path: Path, request_id: str) -> ParseSuccess:
    """Invoke the full PaddleOCR-VL document pipeline inside the worker env.

    The pipeline is loaded once per worker process (design D2.2) and
    performs layout analysis, reading-order handling, recognition, and
    Markdown assembly before the worker creates its protocol envelope.

    Args:
        pdf_path: The validated PDF path from the request.
        request_id: Correlation identifier for the terminal response.

    Returns:
        The assembled success envelope with pipeline metadata.

    Raises:
        WorkerParseError: If PaddleOCR-VL is unavailable or the pipeline
            returns no usable structured Markdown.
    """
    pipeline = _load_pipeline()

    try:
        page_results = list(pipeline.predict(input=str(pdf_path)))
        if not page_results:
            raise WorkerParseError("empty_pipeline_result", "PaddleOCR-VL returned no page results")
        structured_results = list(
            pipeline.restructure_pages(
                page_results,
                merge_tables=True,
                relevel_titles=True,
                concatenate_pages=True,
            )
        )
        markdown = _save_markdown_results(structured_results)
    except WorkerParseError:
        raise
    except Exception as exc:  # noqa: BLE001 - convert backend failures to protocol errors
        raise WorkerParseError("pipeline_error", f"{type(exc).__name__}: {exc}") from exc

    return make_success(
        request_id,
        markdown,
        ocr_backend=WORKER_BACKEND,
        page_count=len(page_results),
        extra_metadata={
            "reader": WORKER_BACKEND,
            "ocr_used": True,
            "pipeline": "PaddleOCRVL",
            "pipeline_revision": "predict+restructure_pages",
            "model": "PaddleOCR-VL",
            "model_revision": "1.6",
        },
    )


def _save_markdown_results(results: list[Any]) -> str:
    """Extract official Markdown output without writing persistent artefacts."""
    with tempfile.TemporaryDirectory(prefix=".ocr-output-", dir=WORKER_DIR) as output_dir:
        output_path = Path(output_dir)
        for result in results:
            result.save_to_markdown(save_path=str(output_path))
        markdown_files = sorted(output_path.rglob("*.md"))
        if not markdown_files:
            raise WorkerParseError(
                "missing_markdown", "PaddleOCR-VL produced no Markdown result files"
            )
        markdown = "\n\n".join(
            path.read_text(encoding="utf-8").strip() for path in markdown_files
        ).strip()
    if not markdown:
        raise WorkerParseError("empty_markdown", "PaddleOCR-VL produced empty Markdown")
    return markdown


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
