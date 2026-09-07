"""Runtime capability resolution and startup validation helpers.

These functions ask the runtime a question ("is native sparse
available?", "is LiteParse installed?", "is the Azure SDK importable?")
or validate a configured strategy name against a registry —
construction work that belongs at the composition boundary: not in
``config/`` (the leaf invariant) and not in ``core/`` consumers.

The sparse/PDF probes moved here verbatim from ``compose.py``
(register-document-backend-strategies, tasks 2.1/2.4): ``compose.py``
sits at the 500-line file ceiling, so additions land here and
``compose`` re-imports them for backward compatibility.
"""

from __future__ import annotations

import logging
import subprocess
from importlib.util import find_spec
from typing import Any

from .config import Settings
from .integrations.ocr_worker.fingerprint import (
    UNAVAILABLE_OCR_WORKER_FINGERPRINT,  # noqa: F401 - re-exported probe result
)

__all__ = [
    "UNAVAILABLE_OCR_WORKER_FINGERPRINT",
    "build_managed_ocr_client",
    "probe_ocr_worker",
    "reset_ocr_fingerprint_cache",
    "resolve_document_backend",
    "resolve_pdf_reader",
    "resolve_sparse_backend",
    "validate_document_backend",
    "validate_sparse_backend",
]

logger = logging.getLogger(__name__)


def _azure_sdk_available() -> bool:
    """Whether the optional ``azure.ai.documentintelligence`` module resolves.

    ``find_spec`` raises (rather than returning ``None``) when a parent
    package is absent or a ``sys.modules`` entry is ``None``, so both
    miss modes are treated as "not installed".
    """
    try:
        return find_spec("azure.ai.documentintelligence") is not None
    except (ImportError, ValueError):
        return False


def resolve_document_backend(settings: Settings) -> str:
    """Resolve the configured document backend, degrading azure to local.

    Mirrors :func:`resolve_pdf_reader`: the capability probe (is the
    Azure SDK importable?) runs once at composition time and the
    RESOLVED name is baked into ``EffectiveSettings``, so the ingestion
    path performs a plain registry read (spec scenario "Azure SDK
    dependency is missing": the effective backend resolves to local
    BEFORE document reading, with a diagnostic naming the dependency).

    Args:
        settings: Resolved settings.

    Returns:
        The effective backend name: the configured name, or ``"local"``
        when azure is selected without the optional SDK.
    """
    name = settings.document_backend.strip() or "local"
    if name != "azure" or _azure_sdk_available():
        return name
    logger.warning(
        "DOCUMENT_BACKEND=azure was requested, but the optional dependency "
        "azure-ai-documentintelligence is not installed — degrading to the "
        "local document backend. Install with: uv sync --extra azure"
    )
    return "local"


def validate_document_backend(settings: Settings) -> None:
    """Validate the configured document backend name strictly at startup.

    Unknown names FAIL startup listing the registered names (spec
    scenario "Unknown backend is configured"), following the
    ``community_algorithm`` precedent: ``config/`` declares the field as
    a plain string and must not duplicate registry knowledge
    (invariant #10).

    Unlike community strategies, an unavailable optional dependency does
    NOT fail here: cloud opt-in (ADR-024) degrades azure to local, and
    :func:`resolve_document_backend` has already logged the reason.
    """
    from .core.ingestion.backends import registry as docbackend_registry

    name = settings.document_backend.strip() or "local"
    if name not in docbackend_registry.available():
        raise ValueError(
            f"DOCUMENT_BACKEND={settings.document_backend!r} is not a registered "
            "document backend. Available: "
            f"{', '.join(docbackend_registry.available())}."
        )
    # Resolve the callable (fail-fast on a bad import string).
    docbackend_registry.get(name)


def resolve_sparse_backend(settings: Settings) -> str:
    """Resolve the configured sparse backend to a concrete registered name.

    Store-neutral capability resolution (task 3.2,
    ``implement-native-sparse-backend-strategy``): ``auto`` and
    explicit ``native`` resolve through the selected store's registry
    metadata plus a REAL native-FTS probe (an import string resolved
    lazily), replacing the Chroma-specific
    ``detect_native_sparse_capability`` route.  Unknown concrete names
    fail here listing ``auto`` plus the registered names (task 3.5).

    Args:
        settings: Resolved settings.

    Returns:
        The concrete backend name: ``"native"`` or ``"bm25"``.
    """
    validate_sparse_backend(settings)
    backend = settings.retrieval.hybrid_sparse_backend
    if backend == "bm25":
        return "bm25"
    native_available = _native_sparse_available(settings)
    if backend == "auto":
        return "native" if native_available else "bm25"
    if native_available:
        return "native"
    logger.warning(
        "HYBRID_SPARSE_BACKEND=native was requested, but the selected "
        "vector store %r does not expose native sparse retrieval. "
        "Falling back to bm25.",
        settings.vector_store,
    )
    return "bm25"


def validate_sparse_backend(settings: Settings) -> None:
    """Validate the sparse backend name against the concrete registry.

    Registry-owned name validation at the composition boundary (task
    3.5): ``config/`` keeps only the §6.10 whitespace idiom and must
    not duplicate registry knowledge (leaf invariant,
    ``community_algorithm`` precedent).  ``auto`` stays a separately
    accepted policy name; the failure message lists it alongside the
    registered concrete names.  Resolving the registered callable
    also fails fast on a bad import string.

    Args:
        settings: Resolved settings carrying the configured
            ``retrieval.hybrid_sparse_backend`` name.

    Raises:
        ValueError: When the configured name is neither ``auto`` nor
            registered in the concrete sparse-backend registry (the
            error lists both).
    """
    from .core.retrieval import sparse_registry

    name = settings.retrieval.hybrid_sparse_backend
    if name == "auto":
        return
    if name not in sparse_registry.available():
        raise ValueError(
            f"RETRIEVAL__HYBRID_SPARSE_BACKEND={name!r} is not a registered "
            "sparse backend. Available: "
            f"{', '.join(['auto', *sparse_registry.available()])}."
        )
    sparse_registry.get(name)


def _native_sparse_available(settings: Settings) -> bool:
    """Probe the SELECTED store for real native sparse capability.

    The vector-store registry's ``native_sparse_probe`` metadata is an
    import string (``"module:attr"``) pointing at the store's real
    probe, or ``None`` when the store declares no native sparse
    capability (the quarantined Chroma extra).  Selection, not
    installation, decides the route.
    """
    import importlib

    from .core.vectordb import registry as vectordb_registry

    probe_spec = vectordb_registry.describe(settings.vector_store)["native_sparse_probe"]
    if not probe_spec:
        return False
    module_path, attr = probe_spec.split(":")
    try:
        probe = getattr(importlib.import_module(module_path), attr)
    except Exception:  # noqa: BLE001 - import drift means unavailable
        logger.debug("Native sparse probe %r could not be imported", probe_spec)
        return False
    try:
        return bool(probe())
    except Exception:  # noqa: BLE001 - a failing probe is an unavailable one
        logger.debug("Native sparse probe %r raised; treating as unavailable", probe_spec)
        return False


def resolve_pdf_reader(settings: Settings) -> str:
    """Resolve the configured PDF reader to a concrete backend name.

    Explicit values probe their registered dependency metadata. ``auto``
    keeps the established LiteParse → pypdfium2 → pypdf capability policy.
    """
    reader = settings.pdf_reader
    if reader != "auto":
        from .integrations.pdf import registry as pdf_registry

        if reader not in pdf_registry.available():
            logger.error("PDF_READER=%r is unregistered; falling back to pypdf.", reader)
            return "pypdf"
        try:
            pdf_registry.probe(reader)
            return reader
        except ImportError:
            logger.error(
                "PDF_READER=%r was requested but the package is not "
                "installed. Falling back to pypdf.",
                reader,
            )
            return "pypdf"

    # auto resolution: probe the established capability preference order.
    for backend in ("liteparse", "pypdfium2"):
        try:
            __import__(backend)
            logger.info("PDF_READER=auto resolved to %s", backend)
            return backend
        except ImportError:
            continue

    return "pypdf"


def _resolve_sparse_backend_for(settings: Settings) -> str:
    """Resolve ``auto`` to a concrete sparse backend via the capability probe."""
    return resolve_sparse_backend(settings)


# ── OCR worker capability probe (task 2.6, design D2.4/D8) ────────────────
#
# The probe is a metadata-only subprocess: it appends the capabilities
# flag to the configured worker command, reads one JSON fingerprint
# line, and the command exits. It never starts the long-lived parsing
# worker, never imports Paddle, and never loads model weights. Every
# unavailability mode collapses to the ONE stable
# UNAVAILABLE_OCR_WORKER_FINGERPRINT so the fingerprint can join the
# source index identity without churning on transient failure detail.

#: Seconds the probe waits for the capabilities command. Deliberately
#: short: a metadata read that takes longer than this is an unusable
#: worker, not a slow one.
OCR_PROBE_TIMEOUT_SECONDS = 10.0

# Memoised probe results, keyed by ``(command, timeout)``. This is a
# capability cache in the ADR-031 reranker-model-cache family, NOT a
# settings singleton: it stores an immutable resolved capability so the
# composition boundary resolves the probe once per command per process
# instead of once per engine or per file. Tests reset it via
# :func:`reset_ocr_fingerprint_cache`.
_ocr_fingerprint_cache: dict[tuple[tuple[str, ...], float], Any] = {}


def probe_ocr_worker(
    command: list[str],
    *,
    timeout: float = OCR_PROBE_TIMEOUT_SECONDS,
) -> Any:
    """Probe one OCR worker command for its capability fingerprint.

    Runs ``command + [CAPABILITIES_FLAG]`` as a one-shot subprocess,
    validates its JSON payload against the OMRG-owned protocol and
    output-schema constants, and memoises the result per command so the
    composition boundary pays for the probe once.

    Args:
        command: Worker launch command, argv-style. An empty command
            means no worker is configured.
        timeout: Seconds to wait for the capabilities command.

    Returns:
        The available :class:`OcrWorkerFingerprint`, or
        :data:`UNAVAILABLE_OCR_WORKER_FINGERPRINT` for a missing,
        unusable, malformed, or incompatible worker — always the same
        constant object, with the specific reason logged.
    """
    from .integrations.ocr_worker.fingerprint import (
        CAPABILITIES_FLAG,
    )

    if not command:
        return UNAVAILABLE_OCR_WORKER_FINGERPRINT
    cache_key = (tuple(command), timeout)
    cached = _ocr_fingerprint_cache.get(cache_key)
    if cached is not None:
        return cached
    # A command that already carries the capabilities flag is run
    # verbatim: an operator (or a test) may embed the flag with its own
    # value in a wrapper command. Otherwise the flag is appended.
    if CAPABILITIES_FLAG in command:
        argv = list(command)
    else:
        argv = [*command, CAPABILITIES_FLAG]
    fingerprint = _run_capability_probe(argv, timeout=timeout)
    _ocr_fingerprint_cache[cache_key] = fingerprint
    if fingerprint.available:
        logger.debug(
            "OCR worker available: protocol %s, %d package(s)",
            fingerprint.protocol_version,
            len(fingerprint.packages),
        )
    else:
        logger.debug("OCR worker unavailable; fingerprint is the stable constant")
    return fingerprint


def _run_capability_probe(argv: list[str], *, timeout: float) -> Any:
    """Run the one-shot capabilities command and classify its output."""
    from .integrations.ocr_worker.fingerprint import (
        UNAVAILABLE_OCR_WORKER_FINGERPRINT,
        fingerprint_from_output,
    )

    try:
        completed = subprocess.run(  # noqa: S603 - caller-configured argv, no shell
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        logger.debug("OCR worker capabilities command timed out after %.1fs", timeout)
        return UNAVAILABLE_OCR_WORKER_FINGERPRINT
    except OSError as exc:
        logger.debug("OCR worker capabilities command could not run: %s", exc)
        return UNAVAILABLE_OCR_WORKER_FINGERPRINT
    if completed.returncode != 0:
        logger.debug(
            "OCR worker capabilities command exited with status %d",
            completed.returncode,
        )
        return UNAVAILABLE_OCR_WORKER_FINGERPRINT
    fingerprint = fingerprint_from_output(completed.stdout)
    if fingerprint is None:
        return UNAVAILABLE_OCR_WORKER_FINGERPRINT
    return fingerprint


def reset_ocr_fingerprint_cache() -> None:
    """Clear the memoised OCR worker fingerprints (used by tests)."""
    _ocr_fingerprint_cache.clear()


def build_managed_ocr_client(settings: Any) -> Any:
    """Compose the owner-scoped OCR worker client from injected settings.

    Single composition path shared by ``build_engine`` (engine-owned
    client, closed at engine shutdown) and the ingest boundary
    (operation-owned client, closed when the batch finishes). The probe
    runs only when the operator enabled the fallback AND configured a
    command, so the packaged default spawns nothing; an empty command
    is the stable unavailable fingerprint.

    Args:
        settings: Settings object (flat ``Settings`` or frozen
            ``EffectiveSettings`` — the six OCR fields exist on both)
            carrying ``ocr_fallback_enabled``, ``ocr_worker_command``,
            ``ocr_worker_env_dir`` and ``ocr_worker_request_timeout``.

    Returns:
        A :class:`~omrg.integrations.ocr_worker.managed.ManagedOcrClient`
        holding the resolved fingerprint. Construction starts no
        process.
    """
    import shlex

    from .integrations.ocr_worker.managed import ManagedOcrClient

    command = shlex.split(getattr(settings, "ocr_worker_command", "") or "")
    if not getattr(settings, "ocr_fallback_enabled", False) or not command:
        fingerprint: Any = UNAVAILABLE_OCR_WORKER_FINGERPRINT
    else:
        fingerprint = probe_ocr_worker(command)
    env_dir = (getattr(settings, "ocr_worker_env_dir", "") or "").strip() or None
    return ManagedOcrClient(
        fingerprint=fingerprint,
        command=command,
        request_timeout=settings.ocr_worker_request_timeout,
        cwd=env_dir,
    )
