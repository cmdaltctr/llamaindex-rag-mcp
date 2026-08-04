"""Protocol definition for PDF reader adapters.

Every adapter implements ``load_data(file: Path) -> list[Document]``,
compatible with LlamaIndex's ``SimpleDirectoryReader.file_extractor``
mapping.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BaseReader(Protocol):
    """Protocol that every PDF reader adapter SHALL satisfy.

    Adapters are used as values in LlamaIndex's ``file_extractor`` dict::

        SimpleDirectoryReader(file_extractor={".pdf": get_pdf_reader()})

    When ``SimpleDirectoryReader`` encounters a ``.pdf`` file, it calls
    ``adapter.load_data(file=Path(...))`` and expects a list of
    ``llama_index.core.Document`` objects in return.
    """

    def load_data(self, file: Path, *args: Any, **kwargs: Any) -> list:
        """Parse a PDF file and return LlamaIndex Document objects.

        Args:
            file: Path to the PDF file to parse.

        Returns:
            A list of ``Document`` objects, one per page or logical
            section, each carrying source-file metadata.
        """
        ...
