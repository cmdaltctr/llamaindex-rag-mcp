"""pypdf adapter — wraps the existing SimpleDirectoryReader path.

This is a pure refactor of the pre-change PDF ingestion logic. No
behaviour change; pypdf via ``llama-index-readers-file`` remains the
default when LiteParse is not installed.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PyPDFReader:
    """Adapter wrapping the current pypdf via SimpleDirectoryReader path.

    Preserves the pre-change PDF ingestion behaviour exactly. pypdf is
    always available via ``llama-index-readers-file``.
    """

    def load_data(self, file: Path, *args: Any, **kwargs: Any) -> list:
        """Parse a PDF using SimpleDirectoryReader (pypdf backend).

        Args:
            file: Path to the PDF file.

        Returns:
            List of LlamaIndex Document objects.
        """
        from llama_index.core import SimpleDirectoryReader

        reader = SimpleDirectoryReader(
            input_files=[str(file)],
            filename_as_id=True,
        )
        return reader.load_data()
