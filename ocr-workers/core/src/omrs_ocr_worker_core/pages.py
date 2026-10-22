"""Page selection helpers shared by every engine (TDR-027).

A page-listed request (protocol 1.1) names 1-based pages. The core
checks the pages against the document before any engine runs. An engine
that has no page-selection parameter writes the listed pages to a
temporary subset PDF with :func:`page_subset`, so what reaches the model
is exactly what was asked for.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from .engine import WorkerParseError

#: Prefix of temporary subset files; engine ``.gitignore`` files list it.
SUBSET_PREFIX = ".ocr-pages-"


def document_page_count(pdf: Path) -> int:
    """Return the number of pages in *pdf*.

    Raises:
        WorkerParseError: If the PDF cannot be read.
    """
    from pypdf import PdfReader

    try:
        return len(PdfReader(str(pdf)).pages)
    except Exception as exc:  # noqa: BLE001 - any read failure is an unusable PDF
        raise WorkerParseError(
            "invalid_pdf", f"cannot read PDF: {type(exc).__name__}: {exc}"
        ) from exc


def check_pages(pdf: Path, pages: Sequence[int]) -> None:
    """Reject page numbers outside the document.

    Raises:
        WorkerParseError: With code ``invalid_page`` for any page
            outside ``1..page_count``.
    """
    total = document_page_count(pdf)
    out_of_range = [page for page in pages if not 1 <= page <= total]
    if out_of_range:
        raise WorkerParseError(
            "invalid_page", f"requested page(s) {out_of_range} outside 1..{total}"
        )


def write_page_subset(source: Path, pages: Sequence[int], *, directory: Path | None = None) -> Path:
    """Write a temporary PDF that holds exactly *pages* from *source*.

    Args:
        source: The request's PDF.
        pages: 1-based page numbers, in the order to write them.
        directory: Folder for the temporary file; the system temporary
            folder when ``None``.

    Returns:
        The subset path. The caller deletes it.

    Raises:
        WorkerParseError: If a requested page is outside the document.
    """
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(source))
    total = len(reader.pages)
    out_of_range = [page for page in pages if not 1 <= page <= total]
    if out_of_range:
        raise WorkerParseError(
            "invalid_page", f"requested page(s) {out_of_range} outside 1..{total}"
        )
    writer = PdfWriter()
    for page in pages:
        writer.add_page(reader.pages[page - 1])
    handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - caller unlinks the file
        prefix=SUBSET_PREFIX, suffix=".pdf", dir=directory, delete=False
    )
    handle.close()
    subset = Path(handle.name)
    writer.write(subset)
    return subset


@contextmanager
def page_subset(
    source: Path, pages: Sequence[int] | None, *, directory: Path | None = None
) -> Iterator[Path]:
    """Yield *source*, or a temporary subset of it when *pages* is given.

    The subset file is deleted on exit, whatever happens inside.
    """
    if pages is None:
        yield source
        return
    subset = write_page_subset(source, pages, directory=directory)
    try:
        yield subset
    finally:
        subset.unlink(missing_ok=True)
