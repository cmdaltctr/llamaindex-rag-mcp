"""The canonical OCR worker capability fingerprint (design D2.4/D8).

One frozen value object describes the isolated worker's extraction
contract: availability, protocol version, package names and exact
versions, pipeline identity and revision, model identity and revision,
and output-schema identity and version. Transient process detail
(process identifiers, timestamps) is deliberately excluded so the
fingerprint can participate in the source index identity.

Every unavailability mode — missing command, failed spawn, malformed
probe output, wrong protocol version, incompatible output schema —
maps to the ONE stable :data:`UNAVAILABLE_OCR_WORKER_FINGERPRINT`
constant, so "why unavailable" is a log message, never a fingerprint
variant.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .protocol import OUTPUT_SCHEMA_ID, OUTPUT_SCHEMA_VERSION, PROTOCOL_VERSION

logger = logging.getLogger(__name__)

#: How the probe asks a worker command for its fingerprint: the flag is
#: appended to the configured worker command, and a conforming worker
#: prints exactly one JSON object to standard output and exits. The
#: long-lived parsing worker is never started by the probe.
CAPABILITIES_FLAG = "--capabilities"


@dataclass(frozen=True)
class OcrWorkerFingerprint:
    """Frozen capability fingerprint of the isolated OCR worker.

    Attributes:
        available: Whether a compatible, usable worker was probed.
        protocol_version: Wire protocol version the worker speaks.
        packages: Sorted ``(name, exact version)`` pairs for every
            declared worker package.
        pipeline_identity: Document-pipeline identity (for example
            ``paddleocr-vl``).
        pipeline_revision: Revision of the document pipeline.
        model_identity: Identity of the parsing model.
        model_revision: Revision of the parsing model.
        output_schema_id: Output-schema identity of successful parse
            responses.
        output_schema_version: Output-schema version.
    """

    available: bool
    protocol_version: str
    packages: tuple[tuple[str, str], ...]
    pipeline_identity: str
    pipeline_revision: str
    model_identity: str
    model_revision: str
    output_schema_id: str
    output_schema_version: str


#: The ONE stable unavailable fingerprint (task 2.6, design D2.4).
#: Identity-safe by construction: no reason string, no process detail —
#: the reason a probe failed belongs in the log, not in the payload
#: that decides re-ingestion.
UNAVAILABLE_OCR_WORKER_FINGERPRINT = OcrWorkerFingerprint(
    available=False,
    protocol_version="",
    packages=(),
    pipeline_identity="",
    pipeline_revision="",
    model_identity="",
    model_revision="",
    output_schema_id="",
    output_schema_version="",
)


def fingerprint_from_payload(payload: Mapping[str, Any]) -> OcrWorkerFingerprint | None:
    """Validate one capabilities payload into a fingerprint.

    Compatibility is decided HERE against the OMRG-owned protocol
    constants: a worker speaking another protocol version or another
    output-schema identity is incompatible, whatever else it reports.

    Args:
        payload: The decoded JSON object printed by the worker's
            capabilities command.

    Returns:
        The available fingerprint, or ``None`` when the payload is
        malformed or incompatible (the caller maps ``None`` to the
        stable unavailable fingerprint).
    """
    try:
        protocol_version = _non_empty_str(payload["protocol_version"])
        packages_raw = payload["packages"]
        pipeline = _identity_pair(payload["pipeline"])
        model = _identity_pair(payload["model"])
        schema_id = _non_empty_str(payload["output_schema"]["id"])
        schema_version = _non_empty_str(payload["output_schema"]["version"])
    except (KeyError, TypeError) as exc:
        _reject(f"capabilities payload is missing or mistyped: {exc}")
        return None
    if not isinstance(packages_raw, Mapping):
        _reject("capabilities payload field 'packages' must be an object")
        return None
    if protocol_version != PROTOCOL_VERSION:
        _reject(f"worker protocol {protocol_version!r} is incompatible with {PROTOCOL_VERSION!r}")
        return None
    if schema_id != OUTPUT_SCHEMA_ID or schema_version != OUTPUT_SCHEMA_VERSION:
        _reject(
            f"worker output schema {schema_id!r}/{schema_version!r} is incompatible "
            f"with {OUTPUT_SCHEMA_ID!r}/{OUTPUT_SCHEMA_VERSION!r}"
        )
        return None
    packages = tuple(sorted((str(k), str(v)) for k, v in packages_raw.items()))
    return OcrWorkerFingerprint(
        available=True,
        protocol_version=protocol_version,
        packages=packages,
        pipeline_identity=pipeline[0],
        pipeline_revision=pipeline[1],
        model_identity=model[0],
        model_revision=model[1],
        output_schema_id=schema_id,
        output_schema_version=schema_version,
    )


def fingerprint_from_output(output: str) -> OcrWorkerFingerprint | None:
    """Parse the first JSON object on a capabilities command's stdout.

    Args:
        output: Everything the capabilities command wrote to standard
            output. Leading diagnostics are tolerated; only the first
            JSON object line is read.

    Returns:
        The available fingerprint, or ``None`` on malformed or
        incompatible output.
    """
    for line in output.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            _reject("capabilities output line is not valid JSON")
            return None
        if not isinstance(parsed, dict):
            _reject("capabilities output line is not a JSON object")
            return None
        return fingerprint_from_payload(parsed)
    _reject("capabilities command printed no JSON object")
    return None


def _identity_pair(raw: Any) -> tuple[str, str]:
    """Return the ``(identity, revision)`` strings from a payload pair."""
    if not isinstance(raw, Mapping):
        raise TypeError("identity pair must be an object")
    return _non_empty_str(raw["identity"]), _non_empty_str(raw["revision"])


def _non_empty_str(value: Any) -> str:
    """Return *value* when it is a non-empty string, else raise."""
    if not isinstance(value, str) or not value:
        raise TypeError("expected a non-empty string")
    return value


def _reject(reason: str) -> None:
    """Log why a capabilities payload was rejected (never a fingerprint variant)."""
    logger.debug("OCR worker unavailable: %s", reason)
