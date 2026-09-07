"""Registered ``local`` document backend.

Wraps the existing local reader chain — LlamaIndex's
``SimpleDirectoryReader`` plus the configured PDF factory reader
(ADR-020) — as one explicit backend implementation so ``local`` and
``azure`` share one observable contract (design D2).  Parser selection
within the local chain (``PDF_READER`` and its ``auto`` capability
policy) is unchanged.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ...settings import EffectiveSettings


async def read_documents(
    file_path: Path, *, settings: EffectiveSettings, ocr_client: Any = None
) -> list[Any]:
    """Read *file_path* with the local reader chain.

    Args:
        file_path: File to read.
        settings: Injected effective settings; ``settings.pdf_reader``
            selects the concrete PDF parser via the factory.
        ocr_client: Injected managed OCR worker client, threaded to
            the PDF factory so the OCR routing seam can dispatch
            OCR-required PDFs (task 2.6a). ``None`` degrades
            OCR-required files deterministically.

    Returns:
        LlamaIndex ``Document`` objects carrying ``file_path`` metadata.
    """

    def _read_sync() -> list[Any]:
        from llama_index.core import SimpleDirectoryReader

        from omrg.integrations.pdf import build_pdf_reader

        pdf_reader = build_pdf_reader(settings.pdf_reader, settings, ocr_client=ocr_client)
        reader = SimpleDirectoryReader(
            input_files=[str(file_path)],
            filename_as_id=True,
            file_extractor={".pdf": pdf_reader},
        )
        return reader.load_data()

    # Blocking parser work runs in a worker thread so the event loop
    # stays responsive (spec: "no event-loop blocking").
    return await asyncio.to_thread(_read_sync)
