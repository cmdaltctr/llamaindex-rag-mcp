"""The PaddleOCR-VL OCR engine: the fallback route.

This module was ``ocr-worker/src/omrg_ocr_worker/worker.py``. The JSON
Lines framing loop, validation, the capability command and page-subset
writing moved to the shared worker core (``omrg_ocr_worker_core``,
change modular-ocr-workers-dots-mocr, design D1/D2). What stays here is
the PaddleOCR-VL document pipeline call, and its output does not change.

The pipeline seam :func:`_run_document_pipeline` is the single place the
isolated environment's Paddle packages enter, and it is the function
tests stub. Everything around it is Paddle-free and testable in the
main environment.
"""

from __future__ import annotations

import copy
import logging
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from omrg_ocr_worker_core.engine import DocumentMarkdown, WorkerParseError, model_cache_dir
from omrg_ocr_worker_core.pages import page_subset

WORKER_BACKEND = "paddleocr-vl"
WORKER_DIR = Path(__file__).resolve().parents[2]

logger = logging.getLogger("omrg_ocr_paddleocr_vl")


def model_cache() -> Path:
    """Return the Paddle model cache folder (design D8)."""
    return model_cache_dir(WORKER_BACKEND, WORKER_DIR)


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
    """Force both Paddle cache variables to the engine-owned cache.

    Assignment, not ``setdefault``: an inherited value pointing outside
    the engine cache would direct model reads and downloads to a path
    outside the engine-owned, git-ignored cache. Both variables are set
    before any Paddle import because PaddleOCR and PaddleX read them at
    import and initialisation time.
    """
    cache = str(model_cache())
    os.environ["PADDLE_OCR_BASE_DIR"] = cache
    os.environ["PADDLE_PDX_CACHE_HOME"] = cache


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


def _run_document_pipeline(
    pdf_path: Path, *, pages: Sequence[int] | None = None
) -> DocumentMarkdown:
    """Invoke the PaddleOCR-VL document pipeline inside the engine env.

    The pipeline is loaded once per worker process (design D2.2) and
    performs layout analysis, reading-order handling, recognition, and
    Markdown assembly.

    A page-listed request (protocol 1.1) parses only those pages: the
    requested pages are first written to a temporary subset PDF by the
    worker core, because paddleocr 3.7.0 has no page-selection parameter:
    a ``page_num`` kwarg is swallowed by ``**kwargs`` and the engine
    silently processes the whole document (TDR-027). The page count
    reports pages processed, which under a page list is the list's
    length; a mismatch fails loudly rather than being padded.

    Args:
        pdf_path: The validated PDF path from the request.
        pages: 1-based page numbers to parse, or ``None`` for the whole
            document.

    Returns:
        The whole-request Markdown and, for a page list, one Markdown
        string per requested page.

    Raises:
        WorkerParseError: If PaddleOCR-VL is unavailable or the pipeline
            returns no usable structured Markdown.
    """
    pipeline = _load_pipeline()

    try:
        with page_subset(pdf_path, pages, directory=WORKER_DIR) as target:
            page_results = list(pipeline.predict(input=str(target)))
        if pages is not None and len(page_results) != len(pages):
            raise WorkerParseError(
                "page_selection_mismatch",
                f"pipeline returned {len(page_results)} page result(s) for {len(pages)} "
                "requested page(s)",
            )
        if not page_results:
            raise WorkerParseError("empty_pipeline_result", "PaddleOCR-VL returned no page results")
        pages_markdown = None
        if pages is not None:
            # A second assembly pass, without concatenation, yields each
            # page's Markdown on its own; re-prediction is the expensive part
            # and is not repeated. restructure_pages rewrites its input in
            # place: with concatenate_pages=True it gives the first page
            # result every page's blocks (paddlex PaddleOCR-VL pipeline).
            # So the per-page pass runs first, on a deep copy, or page 1
            # would carry the whole request (Experiment 34 A9).
            per_page_results = list(
                pipeline.restructure_pages(
                    copy.deepcopy(page_results),
                    merge_tables=True,
                    relevel_titles=True,
                    concatenate_pages=False,
                )
            )
            pages_markdown = tuple(_per_page_markdown(per_page_results, len(pages)))
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

    return DocumentMarkdown(
        markdown=markdown, pages_markdown=pages_markdown, page_count=len(page_results)
    )


def _per_page_markdown(results: list[Any], expected: int) -> list[str]:
    """Return one Markdown string per result.

    The results come from a page-subset PDF, so they are exactly the
    requested pages in order. No padding, no truncation: a length
    mismatch is a bug upstream of this function and fails loudly
    (TDR-027 — padding here once masked a whole-document run).
    """
    if len(results) != expected:
        raise WorkerParseError(
            "page_selection_mismatch",
            f"{len(results)} restructured page(s) for {expected} requested page(s)",
        )
    pages: list[str] = []
    for result in results:
        with tempfile.TemporaryDirectory(prefix=".ocr-output-page-", dir=WORKER_DIR) as page_dir:
            output_path = Path(page_dir)
            result.save_to_markdown(save_path=str(output_path))
            markdown_files = sorted(output_path.rglob("*.md"))
            pages.append(
                "\n\n".join(
                    path.read_text(encoding="utf-8").strip() for path in markdown_files
                ).strip()
            )
    return pages


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


class PaddleOcrVlEngine:
    """PaddleOCR-VL on the worker core contract (design D2).

    The engine defines ``parse_document`` because PaddleOCR-VL assembles
    the whole request itself (it merges tables across pages and re-levels
    titles), so the whole-request Markdown is not a join of the pages.
    """

    name = WORKER_BACKEND
    backend_id = "paddleocr_vl"
    #: Every package whose exact version belongs in the fingerprint.
    #: PaddleX is declared even though ``paddleocr`` pulls it in
    #: transitively: ``PaddleOCRVL`` delegates prediction and page
    #: restructuring to PaddleX, so a PaddleX-only change can alter the
    #: emitted Markdown and must change the worker identity.
    declared_packages: tuple[str, ...] = (
        "omrg-ocr-worker-core",
        "omrg-ocr-paddleocr-vl",
        "paddleocr",
        "paddlex",
        "paddlepaddle",
    )
    pipeline = ("paddleocr-vl", "predict+restructure_pages")
    model = ("PaddleOCR-VL", "1.6")

    def parse_document(self, pdf: Path, pages: Sequence[int] | None) -> DocumentMarkdown:
        """Run the pipeline once for the whole request."""
        return _run_document_pipeline(pdf, pages=pages)

    def parse(self, pdf: Path, pages: Sequence[int] | None) -> list[str]:
        """Return one Markdown string per parsed page."""
        if pages is None:
            from omrg_ocr_worker_core.pages import document_page_count

            pages = range(1, document_page_count(pdf) + 1)
        result = _run_document_pipeline(pdf, pages=tuple(pages))
        return list(result.pages_markdown or ())


#: The object the ``omrg.ocr_engine`` entry point names.
ENGINE = PaddleOcrVlEngine()
