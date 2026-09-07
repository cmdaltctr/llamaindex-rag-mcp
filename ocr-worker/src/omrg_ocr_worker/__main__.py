"""Module entry point: ``python -m omrg_ocr_worker``."""

from __future__ import annotations

from omrg_ocr_worker.worker import main

if __name__ == "__main__":
    raise SystemExit(main())
