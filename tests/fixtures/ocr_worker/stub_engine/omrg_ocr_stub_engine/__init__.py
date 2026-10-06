"""A stub OCR engine for worker-core tests (change modular-ocr-workers-dots-mocr).

It satisfies the engine contract (design D2) with no model at all. The
``ocr-workers/README.md`` add-an-engine checklist names the same pieces
this stub has: the static identity fields, ``parse``, and a module-level
object an ``omrg.ocr_engine`` entry point can name.

Tests register it by writing a ``.dist-info`` folder with an
``entry_points.txt`` onto ``sys.path``; nothing is installed.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path


class StubEngine:
    """Returns one heading per requested page."""

    def __init__(self, name: str = "stub", backend_id: str = "stub_engine") -> None:
        self.name = name
        self.backend_id = backend_id
        self.declared_packages: tuple[str, ...] = ("omrg-ocr-worker-core",)
        self.pipeline = ("stub-pipeline", "1")
        self.model = ("stub-model", "1")

    def parse(self, pdf: Path, pages: Sequence[int] | None) -> list[str]:
        """Return ``# Stub page N`` for each page (page 1 alone for a whole document)."""
        return [f"# Stub page {page}" for page in (pages or [1])]


ENGINE = StubEngine()
SECOND_ENGINE = StubEngine(name="stub-two", backend_id="stub_two")
NOT_AN_ENGINE = object()
