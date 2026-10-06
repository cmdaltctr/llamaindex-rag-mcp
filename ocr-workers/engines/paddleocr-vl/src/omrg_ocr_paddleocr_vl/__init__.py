"""omrg-ocr-paddleocr-vl: the PaddleOCR-VL engine for the OMRG worker core.

This package runs inside the engine-owned Python environment declared
by ``ocr-workers/engines/paddleocr-vl/pyproject.toml``. It must stay
importable in a Paddle-free environment: every Paddle import belongs
inside a function body, never at module level.
"""

from __future__ import annotations
