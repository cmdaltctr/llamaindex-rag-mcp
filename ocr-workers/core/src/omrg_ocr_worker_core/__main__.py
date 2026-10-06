"""Module entry point: ``python -m omrg_ocr_worker_core``.

``--capabilities`` short-circuits to the metadata-only fingerprint
command (design D2.4): print one JSON object, exit, never start the
long-lived parsing loop. Without it, the framing loop serves the one
engine this environment registers.
"""

from __future__ import annotations

import sys

if "--capabilities" in sys.argv:
    from omrg_ocr_worker_core.capabilities import main as capabilities_main

    if __name__ == "__main__":
        raise SystemExit(capabilities_main())
else:
    from omrg_ocr_worker_core.framing import main

    if __name__ == "__main__":
        raise SystemExit(main())
