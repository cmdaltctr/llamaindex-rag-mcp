"""Versioned JSON-lines protocol contract for the Experiment 5b worker.

Implements protocol.md section 11 (versioned bounded stdio protocol) as a
pure-stdlib module importable by the worker child, the parent supervisor and
the fast test suite — no model, no network, no Torch import.

Stdout carries protocol frames only; stderr carries diagnostics drained
concurrently by the parent.  Every frame is one JSON object per newline.
Bounds (section 11): maximum frame size 8 MiB, maximum candidate count 200,
maximum token budget 65,536 tokens per request, maximum queue depth 16.
Duplicate, unknown, oversized, wrong-generation and late frames are rejected
and retained as failure evidence.

The token budget guard uses the registered frame-level estimator
``ceil(len(utf8 bytes) / 4)`` — a conservative pre-inference approximation
applied identically by parent and worker so rejection behaviour is
deterministic and testable without a tokeniser.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "1.0"

MAX_FRAME_BYTES = 8_388_608  # 8 MiB (section 11)
MAX_CANDIDATES = 200
MAX_TOKEN_BUDGET = 65_536
MAX_QUEUE_DEPTH = 16
STDERR_PRESSURE_BYTES = 4_194_304  # 4 MiB sustained (section 12)

FRAME_TYPES = frozenset({"hello", "ready", "rerank", "result", "shutdown", "error"})
_ERROR_CODES = frozenset(
    {
        "malformed_frame",
        "oversized_frame",
        "unknown_frame",
        "duplicate_request",
        "wrong_generation",
        "late_response",
        "bound_violation",
        "model_error",
        "stub_behaviour",
    }
)


class FrameError(ValueError):
    """A frame violated the protocol contract.

    The message is safe evidence: it names the violated rule without echoing
    frame payloads beyond bounded excerpts.
    """


def estimate_tokens(text: str) -> int:
    """Return the registered frame-guard token estimate for *text*.

    ``ceil(len(utf8)/4)`` is the pre-inference bound recorded in the module
    docstring; it is deliberately crude so parent and worker reject the same
    frames deterministically.
    """
    return max(1, math.ceil(len(text.encode("utf-8")) / 4))


def request_token_budget(query: str, candidates: list[dict[str, Any]]) -> int:
    """Total estimated tokens for one rerank request (query + candidates)."""
    total = estimate_tokens(query)
    for candidate in candidates:
        total += estimate_tokens(str(candidate.get("text", "")))
    return total


def encode_frame(payload: dict[str, Any]) -> bytes:
    """Serialise *payload* as one protocol frame, enforcing the size bound.

    Returns:
        The JSON object followed by a newline, ready to write to a pipe.

    Raises:
        FrameError: When the encoded frame exceeds ``MAX_FRAME_BYTES``.
    """
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(encoded) + 1 > MAX_FRAME_BYTES:
        raise FrameError(f"oversized frame: {len(encoded) + 1} bytes exceeds {MAX_FRAME_BYTES}")
    return encoded + b"\n"


def decode_frame(line: bytes | str) -> dict[str, Any]:
    """Decode one protocol line into a validated frame object.

    Args:
        line: One newline-terminated frame as read from the pipe.

    Returns:
        The parsed frame dictionary.

    Raises:
        FrameError: On non-JSON input, non-object roots, size violations,
            missing ``type``, or unknown frame types.
    """
    if isinstance(line, bytes):
        raw = line
    else:
        raw = line.encode("utf-8")
    stripped = raw.strip(b"\r\n")
    if len(stripped) + 1 > MAX_FRAME_BYTES:
        raise FrameError(f"oversized frame: {len(stripped) + 1} bytes")
    try:
        payload = json.loads(stripped.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FrameError(f"malformed frame: {exc}") from exc
    if not isinstance(payload, dict):
        raise FrameError(f"malformed frame: root is {type(payload).__name__}, not object")
    frame_type = payload.get("type")
    if frame_type not in FRAME_TYPES:
        raise FrameError(f"unknown frame type {frame_type!r}")
    return payload


def validate_hello(frame: dict[str, Any]) -> list[str]:
    """Return the list of contract violations in a ``hello`` frame."""
    errors: list[str] = []
    if frame.get("type") != "hello":
        errors.append("type must be 'hello'")
    if frame.get("protocol_version") != PROTOCOL_VERSION:
        errors.append(f"protocol_version must be {PROTOCOL_VERSION!r}")
    pid = frame.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool):
        errors.append("pid must be a positive integer")
    elif pid <= 0:
        errors.append("pid must be a positive integer")
    if not isinstance(frame.get("python_version"), str) or not frame["python_version"]:
        errors.append("python_version must be a non-empty string")
    return errors


def validate_ready(frame: dict[str, Any]) -> list[str]:
    """Return the list of contract violations in a ``ready`` frame.

    The ready frame is the handshake evidence block (protocol section 11
    step 2): model revision and file digests, stack versions, requested and
    effective device, MPS availability and fallback policy.
    """
    errors: list[str] = []
    if frame.get("type") != "ready":
        errors.append("type must be 'ready'")
    if frame.get("protocol_version") != PROTOCOL_VERSION:
        errors.append(f"protocol_version must be {PROTOCOL_VERSION!r}")
    for field in ("model_id", "model_revision"):
        value = frame.get(field)
        if not isinstance(value, str) or not value:
            errors.append(f"{field} must be a non-empty string")
    digests = frame.get("model_file_sha256")
    if not isinstance(digests, dict) or not digests:
        errors.append("model_file_sha256 must be a non-empty mapping")
    elif not all(
        isinstance(k, str)
        and isinstance(v, str)
        and len(v) == 64
        and all(c in "0123456789abcdef" for c in v)
        for k, v in digests.items()
    ):
        errors.append("model_file_sha256 values must be 64-lowercase-hex-char strings")
    versions = frame.get("stack_versions")
    if not isinstance(versions, dict) or not versions:
        errors.append("stack_versions must be a non-empty mapping")
    for field in ("requested_device", "effective_device"):
        value = frame.get(field)
        if not isinstance(value, str) or not value:
            errors.append(f"{field} must be a non-empty string")
    if not isinstance(frame.get("mps_available"), bool):
        errors.append("mps_available must be a boolean")
    fallback = frame.get("pytorch_enable_mps_fallback")
    if fallback != "0":
        errors.append("pytorch_enable_mps_fallback must be the string '0'")
    return errors


def validate_rerank(frame: dict[str, Any]) -> list[str]:
    """Return the list of contract violations in an inbound ``rerank`` frame.

    Enforces the section 11 bounds: positive integer request id and
    generation, non-negative generation, string query, candidate list within
    ``MAX_CANDIDATES``, per-candidate ``doc_id``/``text`` shape, positive
    ``top_k`` and the token budget.
    """
    errors: list[str] = []
    if frame.get("type") != "rerank":
        errors.append("type must be 'rerank'")
    request_id = frame.get("request_id")
    if not isinstance(request_id, int) or isinstance(request_id, bool):
        errors.append("request_id must be a non-negative integer")
    elif request_id < 0:
        errors.append("request_id must be a non-negative integer")
    generation = frame.get("generation")
    if not isinstance(generation, int) or isinstance(generation, bool):
        errors.append("generation must be a non-negative integer")
    elif generation < 0:
        errors.append("generation must be a non-negative integer")
    if not isinstance(frame.get("query"), str):
        errors.append("query must be a string")
    candidates = frame.get("candidates")
    if not isinstance(candidates, list):
        errors.append("candidates must be a list")
        return errors
    if len(candidates) > MAX_CANDIDATES:
        errors.append(f"candidate count {len(candidates)} exceeds {MAX_CANDIDATES}")
    if len(candidates) == 0:
        errors.append("candidates must not be empty")
    doc_ids: set[str] = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            errors.append(f"candidate {index} must be an object")
            continue
        doc_id = candidate.get("doc_id")
        text = candidate.get("text")
        if not isinstance(doc_id, str) or not doc_id:
            errors.append(f"candidate {index} doc_id must be a non-empty string")
        else:
            if doc_id in doc_ids:
                errors.append(f"candidate {index} duplicates doc_id {doc_id!r}")
            doc_ids.add(doc_id)
        if not isinstance(text, str):
            errors.append(f"candidate {index} text must be a string")
    top_k = frame.get("top_k")
    if not isinstance(top_k, int) or isinstance(top_k, bool):
        errors.append("top_k must be a positive integer")
    elif top_k <= 0:
        errors.append("top_k must be a positive integer")
    if isinstance(frame.get("query"), str) and isinstance(candidates, list):
        budget_ok = all(isinstance(c, dict) and isinstance(c.get("text"), str) for c in candidates)
        if budget_ok:
            budget = request_token_budget(frame["query"], candidates)
            if budget > MAX_TOKEN_BUDGET:
                errors.append(f"token budget {budget} exceeds {MAX_TOKEN_BUDGET}")
    return errors


def validate_result(frame: dict[str, Any]) -> list[str]:
    """Return the list of contract violations in a ``result`` frame.

    Per-response route admission evidence (design D2): request id,
    generation, model identity, effective backend/device, reranked status
    and cardinality must all be present and well-formed.
    """
    errors: list[str] = []
    if frame.get("type") != "result":
        errors.append("type must be 'result'")
    request_id = frame.get("request_id")
    if not isinstance(request_id, int) or isinstance(request_id, bool):
        errors.append("request_id must be an integer")
    generation = frame.get("generation")
    if not isinstance(generation, int) or isinstance(generation, bool):
        errors.append("generation must be an integer")
    for field in ("model_id", "model_revision", "backend", "device"):
        value = frame.get(field)
        if not isinstance(value, str) or not value:
            errors.append(f"{field} must be a non-empty string")
    if not isinstance(frame.get("reranked"), bool):
        errors.append("reranked must be a boolean")
    ranking = frame.get("ranking")
    if not isinstance(ranking, list) or not all(isinstance(item, str) for item in ranking):
        errors.append("ranking must be a list of strings")
    scores = frame.get("scores")
    if not isinstance(scores, dict):
        errors.append("scores must be an object")
    inference_ms = frame.get("inference_ms")
    if not isinstance(inference_ms, (int, float)) or isinstance(inference_ms, bool):
        errors.append("inference_ms must be a non-negative number")
    elif inference_ms < 0:
        errors.append("inference_ms must be a non-negative number")
    if isinstance(ranking, list) and isinstance(scores, dict):
        if len(ranking) != len(scores):
            errors.append("ranking and scores must have equal cardinality")
    return errors


def error_frame(
    request_id: int | None,
    code: str,
    detail: str,
) -> dict[str, Any]:
    """Build a protocol ``error`` frame.

    Raises:
        FrameError: On an unregistered error code (contract drift guard).
    """
    if code not in _ERROR_CODES:
        raise FrameError(f"unknown error code {code!r}")
    return {
        "type": "error",
        "request_id": request_id,
        "code": code,
        "detail": detail[:2000],
    }


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read a JSON-lines artefact file for analysis (raw evidence helper).

    Raises:
        ValueError: Naming the artefact and line number when a line exceeds
            the bounded-frame guard, so a corrupt artefact fails loudly.
    """
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        if len(line) > MAX_FRAME_BYTES:
            raise ValueError(
                f"{path}: line {number} is {len(line)} bytes "
                f"(bound {MAX_FRAME_BYTES}); artefact is not a bounded JSONL file"
            )
        rows.append(json.loads(line))
    return rows
