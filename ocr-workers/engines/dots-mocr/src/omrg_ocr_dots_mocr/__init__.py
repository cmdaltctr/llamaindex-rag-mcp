"""omrg-ocr-dots-mocr: the dots.mocr OCR engine for the OMRG worker core.

This package runs inside the engine-owned environment declared by
``ocr-workers/engines/dots-mocr/pyproject.toml``. It must stay
importable without PyTorch: every model import belongs inside a
function body, never at module level.
"""

from __future__ import annotations
