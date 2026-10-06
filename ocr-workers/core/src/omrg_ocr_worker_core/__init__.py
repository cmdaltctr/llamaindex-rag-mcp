"""omrg-ocr-worker-core: the shared core of every OMRG OCR engine.

The core owns the JSON Lines protocol, validation, the framing loop,
the capability command, page-subset writing and the engine contract
(change modular-ocr-workers-dots-mocr, design D1/D2). An engine project
depends on it and registers one ``omrg.ocr_engine`` entry point.

The core must stay importable without Paddle or PyTorch: it uses the
standard library and pypdf only.
"""

from __future__ import annotations
