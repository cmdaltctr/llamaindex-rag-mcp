"""Metadata-only capability fingerprint command for every OCR engine.

Prints exactly one JSON object on standard output and exits (design
D2.4 of change improve-rag-input-quality-5). The payload reports:

- the wire protocol version the worker speaks;
- the engine's diagnostic backend identifier (``backend_id``), so the
  host can stamp diagnostics without knowing engine names;
- every declared package with its exact installed version;
- the document-pipeline identity and revision;
- the parsing-model identity and revision;
- the output-schema identity and version of parse responses.

The command is metadata-only: it reads ``importlib.metadata`` and the
engine's static fields. It must never initialise a model runtime, load
weights, or keep running after printing. OMRG's composition boundary
calls it to decide availability before any parse dispatch.

An environment that registers zero or several engines prints nothing on
standard output and exits with a failure status, so the host records
the stable unavailable fingerprint.
"""

from __future__ import annotations

import json
import sys
from importlib import metadata as importlib_metadata

from .engine import EngineLoadError, OcrEngine, load_engine
from .protocol import OUTPUT_SCHEMA_ID, OUTPUT_SCHEMA_VERSION, PROTOCOL_VERSION

#: Exit status when the environment does not register exactly one engine.
EXIT_NO_ENGINE = 3


def fingerprint_payload(engine: OcrEngine) -> dict[str, object]:
    """Build the capabilities payload from metadata and static declarations.

    A declared package that is somehow missing reports ``not-installed``
    rather than lying by omission.

    Args:
        engine: The loaded engine.

    Returns:
        The JSON-ready fingerprint object. Pure data: no process side
        effects, no model loading.
    """
    packages: dict[str, str] = {}
    for name in engine.declared_packages:
        try:
            packages[name] = importlib_metadata.version(name)
        except importlib_metadata.PackageNotFoundError:
            packages[name] = "not-installed"
    pipeline_identity, pipeline_revision = engine.pipeline
    model_identity, model_revision = engine.model
    return {
        "protocol_version": PROTOCOL_VERSION,
        "backend_id": engine.backend_id,
        "packages": packages,
        "pipeline": {"identity": pipeline_identity, "revision": pipeline_revision},
        "model": {"identity": model_identity, "revision": model_revision},
        "output_schema": {"id": OUTPUT_SCHEMA_ID, "version": OUTPUT_SCHEMA_VERSION},
    }


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001 - conventional signature
    """Print the fingerprint as one JSON line and exit.

    Returns:
        0 after printing; :data:`EXIT_NO_ENGINE` when the environment
        does not register exactly one usable engine (nothing printed on
        standard output, the reason on standard error).
    """
    try:
        engine = load_engine()
    except EngineLoadError as exc:
        sys.stderr.write(f"omrg OCR worker unavailable: {exc}\n")
        sys.stderr.flush()
        return EXIT_NO_ENGINE
    sys.stdout.write(json.dumps(fingerprint_payload(engine), sort_keys=True))
    sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
