"""Metadata-only capability fingerprint command for the OCR worker.

Prints exactly one JSON object on standard output and exits (design
D2.4 of change improve-rag-input-quality-5). The payload reports:

- the wire protocol version this worker speaks;
- every declared package with its exact installed version;
- the document-pipeline identity and revision;
- the parsing-model identity and revision;
- the output-schema identity and version of parse responses.

The command is metadata-only: it reads ``importlib.metadata`` and the
static declarations below. It must never initialise Paddle, import
model code, load weights, or keep running after printing — OMRG's
composition boundary calls it to decide availability before any parse
dispatch, and the probe must stay cheap.
"""

from __future__ import annotations

import json
import sys
from importlib import metadata as importlib_metadata

from .protocol import OUTPUT_SCHEMA_ID, OUTPUT_SCHEMA_VERSION, PROTOCOL_VERSION

#: Every package whose exact version belongs in the fingerprint. The
#: worker owns these through its lockfile (D2.1); a package that is
#: somehow missing reports ``not-installed`` rather than lying by
#: omission.
DECLARED_PACKAGES: tuple[str, ...] = (
    "omrg-ocr-worker",
    "paddleocr",
    "paddlepaddle",
)

#: Static pipeline/model declarations matching the worker's wired path.
#: The package versions remain in ``packages`` so a lockfile change also
#: changes the resolved worker identity.
PIPELINE_IDENTITY = "paddleocr-vl"
PIPELINE_REVISION = "predict+restructure_pages"
MODEL_IDENTITY = "PaddleOCR-VL"
MODEL_REVISION = "1.6"


def fingerprint_payload() -> dict[str, object]:
    """Build the capabilities payload from metadata and static declarations.

    Returns:
        The JSON-ready fingerprint object. Pure data — no process side
        effects, no model loading.
    """
    packages: dict[str, str] = {}
    for name in DECLARED_PACKAGES:
        try:
            packages[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            packages[name] = "not-installed"
    return {
        "protocol_version": PROTOCOL_VERSION,
        "packages": packages,
        "pipeline": {"identity": PIPELINE_IDENTITY, "revision": PIPELINE_REVISION},
        "model": {"identity": MODEL_IDENTITY, "revision": MODEL_REVISION},
        "output_schema": {"id": OUTPUT_SCHEMA_ID, "version": OUTPUT_SCHEMA_VERSION},
    }


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001 - conventional signature
    """Print the fingerprint as one JSON line and exit.

    Args:
        argv: Unused; present for a conventional entry signature.

    Returns:
        The process exit status (always 0 — a metadata read cannot
        meaningfully fail, and the probe treats non-zero exits as
        unavailability).
    """
    sys.stdout.write(json.dumps(fingerprint_payload(), sort_keys=True))
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
