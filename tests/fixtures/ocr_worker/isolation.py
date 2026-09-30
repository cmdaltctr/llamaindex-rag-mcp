"""Keep the OCR worker packages from leaking between tests.

The worker core and the engines are imported from source by several
test modules, each with its own ``sys.path``. A half-restored
``sys.modules`` would mix two generations of the same classes (an
``isinstance`` check against a class from the other generation fails).
Each test that imports them starts and ends with none loaded.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager

_PREFIX = "omrg_ocr_"


@contextmanager
def isolated_worker_modules() -> Iterator[None]:
    """Unload every ``omrg_ocr_*`` module on entry; restore the originals on exit."""
    saved = {name: mod for name, mod in sys.modules.items() if name.startswith(_PREFIX)}
    for name in saved:
        del sys.modules[name]
    try:
        yield
    finally:
        for name in [name for name in sys.modules if name.startswith(_PREFIX)]:
            del sys.modules[name]
        sys.modules.update(saved)
