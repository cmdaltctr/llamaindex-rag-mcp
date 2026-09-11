"""omrg-ocr-worker: the isolated PaddleOCR-VL document-parsing worker.

This package runs inside the worker-owned Python environment declared
by ``ocr-worker/pyproject.toml``. It must stay importable in a
Paddle-free environment: every Paddle import belongs inside a function
body, never at module level.
"""

from __future__ import annotations
