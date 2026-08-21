#!/usr/bin/env python3
"""Experiment 5b persistent reranker worker (protocol.md section 11).

Versioned JSON-lines worker over stdin/stdout.  Stdout carries protocol
frames only; diagnostics go to stderr, drained concurrently by the parent.

Lifecycle: emit ``hello`` -> load the production reranker -> emit ``ready``
with exact model identity, stack versions, requested/effective device, MPS
availability and fallback policy -> serve bounded ``rerank`` frames -> exit
on ``shutdown``, stdin EOF or idle expiry.

``PYTORCH_ENABLE_MPS_FALLBACK=0`` is assigned before any other statement so
no Torch-capable import can precede it (protocol section 7).

``--stub`` replaces the model with a deterministic stub for lifecycle probes
and fast tests; it never imports the Torch stack.  ``--stub-behaviour``
selects a registered probe violation (stderr-flood, slow-response,
exit-on-request, hang-on-request, malformed-on-ready, oversized-on-request).
"""

from __future__ import annotations

import os

os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "0"  # noqa: E402 — must precede all imports

import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import selectors  # noqa: E402
import signal  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from collections import deque  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parent.parent))

import protocol_frames as pf  # noqa: E402

OVERSIZED_SENTINEL = b"\x00OVERSIZED"
REGISTERED_MODEL_FILES = (
    "config.json",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
    "special_tokens_map.json",
)
STUB_BEHAVIOURS = (
    "stderr-flood",
    "slow-response",
    "exit-on-request",
    "hang-on-request",
    "malformed-on-ready",
    "oversized-on-request",
)


def _log(message: str) -> None:
    """Write a diagnostic line to stderr (stdout is protocol-only)."""
    print(f"[worker pid={os.getpid()}] {message}", file=sys.stderr, flush=True)


def resolve_model_identity(model_id: str) -> dict[str, Any]:
    """Resolve the cached model revision and registered file digests offline.

    Reads the local HF cache ``refs/main`` pointer so the reported revision
    is exactly the snapshot sentence-transformers resolves with
    ``HF_HUB_OFFLINE=1``.  No network access.
    """
    hub_root = Path(os.environ.get("HF_HUB", os.path.expanduser("~/.cache/huggingface/hub")))
    model_dir = hub_root / ("models--" + model_id.replace("/", "--"))
    refs_main = model_dir / "refs" / "main"
    revision = refs_main.read_text(encoding="utf-8").strip()
    snapshot = model_dir / "snapshots" / revision
    digests: dict[str, str] = {}
    for name in REGISTERED_MODEL_FILES:
        digest = hashlib.sha256()
        with (snapshot / name).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        digests[name] = digest.hexdigest()
    return {
        "model_revision": revision,
        "snapshot_path": str(snapshot),
        "model_file_sha256": digests,
    }


def mps_memory() -> dict[str, int] | None:
    """Return MPS allocator/driver bytes, or None when unavailable."""
    try:
        import torch

        if getattr(torch.backends, "mps", None) is None or not torch.backends.mps.is_available():
            return None
        return {
            "current_allocated_bytes": int(torch.mps.current_allocated_memory()),
            "driver_allocated_bytes": int(torch.mps.driver_allocated_memory()),
        }
    except Exception:  # noqa: BLE001 — diagnostic field only
        return None


class StubReranker:
    """Deterministic no-model reranker for probes and fast tests.

    Produces scores from a stable hash of (query, doc_id) so ranking order
    is reproducible without any model.  Matches the production surface the
    worker and parent observe: ``rerank``, ``_model_id``,
    ``last_loaded_device``, ``last_failure_reason``.
    """

    backend_name = "torch-stub"

    def __init__(self, model_id: str, device: str) -> None:
        self._model_id = model_id
        self.last_loaded_device = device
        self.last_failure_reason: str | None = None

    def rerank(
        self,
        query: str,
        results: list[dict],
        top_k: int = 5,
    ) -> list[dict]:
        ranked = sorted(
            results,
            key=lambda r: hashlib.sha256(f"{query}:{r['doc_id']}".encode()).hexdigest(),
            reverse=True,
        )[:top_k]
        for row in ranked:
            digest = hashlib.sha256(f"{query}:{row['doc_id']}".encode()).digest()
            row["score"] = int.from_bytes(digest[:8], "big") / 2**64
            row["_reranked"] = True
        return ranked


def load_production_reranker(model_id: str, device: str) -> tuple[Any, bool]:
    """Construct the unmodified production reranker on the declared device.

    Returns ``(reranker, mps_available_before_policy)``.  The real MPS
    availability is captured *before* the CPU device policy hides it, so the
    ready frame reports host truth rather than policy effect (Exp 5 seam).
    """
    import torch

    mps_available = bool(
        getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available()
    )
    if device == "cpu":
        torch.backends.mps.is_available = lambda: False  # noqa: B010 — Exp 5 seam
    from rag_mcp.core.retrieval.reranker_torch import SentenceTransformerReranker

    reranker = SentenceTransformerReranker(model_id=model_id)
    probe = [{"text": "probe passage", "score": 0.0, "doc_id": "probe"}]
    reranker.rerank("probe query", probe, top_k=1)  # untimed load trigger
    if probe[0].get("_reranked") is not True or reranker.last_failure_reason:
        raise RuntimeError(f"production load degraded: {reranker.last_failure_reason!r}")
    return reranker, mps_available


def stack_versions(stub: bool) -> dict[str, str]:
    """Record stack versions for the handshake evidence block."""
    if stub:
        return {"stub": "1", "python": sys.version.split()[0]}
    import sentence_transformers
    import torch
    import transformers

    return {
        "python": sys.version.split()[0],
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "sentence_transformers": sentence_transformers.__version__,
    }


def build_result_frame(
    *,
    frame: dict[str, Any],
    reranker: Any,
    model_id: str,
    model_revision: str,
    device: str,
    inference_ms: float,
) -> dict[str, Any]:
    """Assemble the per-response route-admission evidence frame (design D2)."""
    ranked = frame["_ranked"]
    reranked = bool(ranked) and all(row.get("_reranked") is True for row in ranked)
    expected = min(frame["top_k"], len(frame["candidates"]))
    reranked = reranked and len(ranked) == expected
    return {
        "type": "result",
        "request_id": frame["request_id"],
        "generation": frame["generation"],
        "model_id": model_id,
        "model_revision": model_revision,
        "backend": "torch",
        "device": str(getattr(reranker, "last_loaded_device", device)),
        "reranked": reranked,
        "cardinality": len(ranked),
        "expected_cardinality": expected,
        "ranking": [row["doc_id"] for row in ranked],
        "scores": {row["doc_id"]: float(row["score"]) for row in ranked},
        "inference_ms": inference_ms,
        "mps": mps_memory() if device == "mps" else None,
    }


def serve_rerank(
    frame: dict[str, Any],
    *,
    reranker: Any,
    model_id: str,
    model_revision: str,
    device: str,
    generation: int,
    seen_request_ids: deque[int],
    stub_behaviour: str | None,
    stub_slow_seconds: float,
    stub_stderr_bytes: int,
) -> bytes | None:
    """Validate and serve one rerank frame; return the response bytes.

    Returns ``None`` when the process must exit (exit-on-request behaviour).
    Violations produce ``error`` frames; they are never silently dropped.
    """
    request_id = frame.get("request_id")
    frame_generation = frame.get("generation")
    if frame_generation != generation:
        return pf.encode_frame(
            pf.error_frame(
                request_id if isinstance(request_id, int) else None,
                "wrong_generation",
                f"worker generation {generation}, frame generation {frame_generation!r}",
            )
        )
    if isinstance(request_id, int) and request_id in seen_request_ids:
        return pf.encode_frame(
            pf.error_frame(request_id, "duplicate_request", "request id already served")
        )
    errors = pf.validate_rerank(frame)
    if errors:
        code = "bound_violation" if any("exceeds" in e for e in errors) else "malformed_frame"
        return pf.encode_frame(
            pf.error_frame(
                request_id if isinstance(request_id, int) else None,
                code,
                "; ".join(errors),
            )
        )
    if not isinstance(request_id, int) or isinstance(request_id, bool):
        return pf.encode_frame(
            pf.error_frame(None, "malformed_frame", "request_id must be an integer")
        )

    if stub_behaviour == "exit-on-request":
        _log(f"stub behaviour: exiting on request {request_id}")
        return None
    if stub_behaviour == "stderr-flood":
        chunk = b"x" * 65536
        emitted = 0
        target = max(1, stub_stderr_bytes)
        while emitted < target:
            sys.stderr.write(chunk.decode())
            sys.stderr.flush()
            emitted += len(chunk)
        _log(f"stub behaviour: flooded {emitted} stderr bytes")
    if stub_behaviour == "slow-response":
        _log(f"stub behaviour: sleeping {stub_slow_seconds}s before response")
        time.sleep(stub_slow_seconds)
    if stub_behaviour == "hang-on-request":
        _log("stub behaviour: SIGSTOP self")
        sys.stdout.flush()
        os.kill(os.getpid(), signal.SIGSTOP)
    if stub_behaviour == "oversized-on-request":
        payload = {
            "type": "result",
            "request_id": request_id,
            "generation": generation,
            "pad": "y" * (pf.MAX_FRAME_BYTES + 1024),
        }
        sys.stdout.buffer.write(json.dumps(payload).encode() + b"\n")
        sys.stdout.buffer.flush()
        return b""

    candidates = [
        {"text": c["text"], "score": 0.0, "doc_id": c["doc_id"]} for c in frame["candidates"]
    ]
    started = time.perf_counter()
    ranked = reranker.rerank(frame["query"], candidates, top_k=frame["top_k"])
    inference_ms = (time.perf_counter() - started) * 1000.0
    seen_request_ids.append(request_id)
    result = build_result_frame(
        frame={**frame, "_ranked": ranked},
        reranker=reranker,
        model_id=model_id,
        model_revision=model_revision,
        device=device,
        inference_ms=inference_ms,
    )
    return pf.encode_frame(result)


def read_frames(stdin_fd: int, idle_seconds: float):
    """Yield decoded inbound lines until EOF or idle expiry.

    Raises ``TimeoutError`` when no frame arrives within *idle_seconds*.
    """
    selector = selectors.DefaultSelector()
    selector.register(stdin_fd, selectors.EVENT_READ)
    buffer = b""
    oversized = False
    deadline = time.monotonic() + idle_seconds
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"idle expiry after {idle_seconds}s")
            events = selector.select(timeout=remaining)
            if not events:
                raise TimeoutError(f"idle expiry after {idle_seconds}s")
            chunk = os.read(stdin_fd, 1 << 16)
            if not chunk:
                return
            buffer += chunk
            if oversized or len(buffer) > pf.MAX_FRAME_BYTES:
                oversized = True
                if b"\n" in chunk:
                    buffer = b""  # oversized frame fully drained
                    oversized = False
                    deadline = time.monotonic() + idle_seconds
                    yield OVERSIZED_SENTINEL
                else:
                    buffer = b""
                continue
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                deadline = time.monotonic() + idle_seconds
                yield line
    finally:
        selector.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("cpu", "mps"), required=True)
    parser.add_argument("--model-id", default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    parser.add_argument("--generation", type=int, default=0)
    parser.add_argument("--idle-seconds", type=float, default=60.0)
    parser.add_argument("--stub", action="store_true")
    parser.add_argument("--stub-behaviour", choices=STUB_BEHAVIOURS)
    parser.add_argument("--stub-slow-seconds", type=float, default=5.0)
    parser.add_argument("--stub-stderr-bytes", type=int, default=pf.STDERR_PRESSURE_BYTES)
    args = parser.parse_args(argv)

    hello = pf.encode_frame(
        {
            "type": "hello",
            "protocol_version": pf.PROTOCOL_VERSION,
            "pid": os.getpid(),
            "python_version": sys.version.split()[0],
        }
    )
    sys.stdout.buffer.write(hello)
    sys.stdout.buffer.flush()

    if args.stub:
        reranker = StubReranker(args.model_id, args.device)
        identity = {
            "model_revision": "stub",
            "model_file_sha256": {
                name: hashlib.sha256(f"stub:{name}".encode()).hexdigest()
                for name in REGISTERED_MODEL_FILES
            },
        }
        mps_available = False
    else:
        reranker, mps_available = load_production_reranker(args.model_id, args.device)
        identity = resolve_model_identity(args.model_id)

    effective_device = str(getattr(reranker, "last_loaded_device", args.device))
    ready = pf.encode_frame(
        {
            "type": "ready",
            "protocol_version": pf.PROTOCOL_VERSION,
            "pid": os.getpid(),
            "model_id": args.model_id,
            "model_revision": identity["model_revision"],
            "model_file_sha256": identity["model_file_sha256"],
            "snapshot_path": identity.get("snapshot_path"),
            "stack_versions": stack_versions(args.stub),
            "requested_device": args.device,
            "effective_device": effective_device,
            "mps_available": mps_available,
            "pytorch_enable_mps_fallback": os.environ["PYTORCH_ENABLE_MPS_FALLBACK"],
        }
    )
    if identity.get("snapshot_path"):
        home = str(Path.home())
        if identity["snapshot_path"].startswith(home):
            identity["snapshot_path"] = "~" + identity["snapshot_path"][len(home) :]
    sys.stdout.buffer.write(ready)
    sys.stdout.buffer.flush()

    if args.stub_behaviour == "malformed-on-ready":
        sys.stdout.buffer.write(b"this-is-not-json{\n")
        sys.stdout.buffer.flush()
        _log("stub behaviour: emitted malformed frame after ready")

    # Bounded recent-request memory for duplicate detection.  The worker
    # serves synchronously, so in-flight requests never exceed one and the
    # queue-depth bound is a parent-side admission rule, not a worker count.
    recent_request_ids: deque[int] = deque(maxlen=1024)
    exit_code = 0
    try:
        for line in read_frames(sys.stdin.fileno(), args.idle_seconds):
            if line == OVERSIZED_SENTINEL:
                response = pf.error_frame(
                    None, "oversized_frame", "inbound frame exceeded the size bound"
                )
                sys.stdout.buffer.write(pf.encode_frame(response))
                sys.stdout.buffer.flush()
                continue
            try:
                frame = pf.decode_frame(line)
            except pf.FrameError as exc:
                response = pf.error_frame(None, "malformed_frame", str(exc))
                sys.stdout.buffer.write(pf.encode_frame(response))
                sys.stdout.buffer.flush()
                continue
            if frame["type"] == "shutdown":
                _log("orderly shutdown frame received")
                break
            response = serve_rerank(
                frame,
                reranker=reranker,
                model_id=args.model_id,
                model_revision=identity["model_revision"],
                device=args.device,
                generation=args.generation,
                seen_request_ids=recent_request_ids,
                stub_behaviour=args.stub_behaviour,
                stub_slow_seconds=args.stub_slow_seconds,
                stub_stderr_bytes=args.stub_stderr_bytes,
            )
            if response is None:
                _log("exiting mid-request by stub behaviour")
                return 1
            if response:
                sys.stdout.buffer.write(response)
                sys.stdout.buffer.flush()
    except TimeoutError as exc:
        _log(f"idle expiry: {exc}")
        exit_code = 0
    _log("worker exiting")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
