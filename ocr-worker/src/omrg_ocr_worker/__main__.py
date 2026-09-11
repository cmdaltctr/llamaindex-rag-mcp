"""Module entry point: ``python -m omrg_ocr_worker``.

``--capabilities`` short-circuits to the metadata-only fingerprint
command (design D2.4): print one JSON object, exit, never start the
long-lived parsing loop.
"""

from __future__ import annotations

import sys

if "--capabilities" in sys.argv:
    from omrg_ocr_worker.capabilities import main as capabilities_main

    if __name__ == "__main__":
        raise SystemExit(capabilities_main())
else:
    from omrg_ocr_worker.worker import main

    if __name__ == "__main__":
        raise SystemExit(main())
