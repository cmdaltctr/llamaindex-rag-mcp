"""OCR engine route and maths-routing settings (change modular-ocr-workers-dots-mocr).

The six fields live in a mixin so ``config/__init__.py`` stays under the
file-size ceiling (the ``storage.py`` precedent). They are flat,
top-level fields beside the other OCR fields, read from ``OCR_WORKERS_DIR``,
``OCR_ENGINE_PRIMARY``, ``OCR_ENGINE_FALLBACK``, ``OCR_MATHS_ROUTING_ENABLED``,
``OCR_MATHS_PAGE_FRACTION`` and ``OCR_WORKER_SECONDS_PER_PAGE``.

Engine names are not validated against a list here: the host resolves an
engine from its folder name alone (design D3), and an unknown name
degrades to the unavailable fingerprint at the composition boundary.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .sources import LegacyBool


class OcrRouteSettingsMixin(BaseModel):
    """The OCR route and maths-routing fields of :class:`omrg.config.Settings`."""

    # Design D3: the primary route serves every OCR dispatch; the fallback
    # serves only when the primary is unavailable before dispatch. Empty
    # workers directory = every route unavailable; empty fallback = none.
    ocr_workers_dir: str = ""
    ocr_engine_primary: str = "dots-mocr"
    ocr_engine_fallback: str = "paddleocr-vl"
    # Design D5/D6: maths pages route to OCR. The document-unit fraction
    # 0.10 matches the calibrated OCR-page fraction of the gate (ADR-065).
    ocr_maths_routing_enabled: LegacyBool = True
    ocr_maths_page_fraction: float = Field(default=0.10, ge=0.0, le=1.0)
    # dots.mocr took 7-56 s per page on MPS (Experiment 34); 120 s leaves
    # headroom for CPU and long pages. The per-request timeout stays a floor.
    ocr_worker_seconds_per_page: float = Field(default=120.0, ge=0.0)

    @field_validator("ocr_workers_dir", "ocr_engine_primary", "ocr_engine_fallback")
    @classmethod
    def _strip(cls, value: str) -> str:
        """Strip padding so ``OCR_ENGINE_FALLBACK= `` means no fallback."""
        return value.strip()
