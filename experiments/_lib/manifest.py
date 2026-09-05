"""Shared D13 runtime-manifest builder for experiment harnesses.

Provenance: design decision D13 ("Runtime manifest") of the OpenSpec change
``harden-pipeline-correctness-before-calibration`` (Stage 4, task 4.1).  A
reported result must be attributable to what actually ran, so every experiment
manifest records requested *and* effective backends, devices, providers and
fallback state alongside corpus/query/qrels content identities.

This module generalises the manifest slice that experiment 18's harness built
inline (``experiments/18-ingestion-lock-scope-ab-2026-08-19/harness.py``);
that harness stays untouched.  Future runners import this shared version,
whose repository root is injectable for tests.

Secrets: :func:`build_runtime_manifest` never receives or stores secrets —
it records backend names, model identifiers and content hashes only.  As
defence-in-depth for callers that assemble manifests from settings objects,
:func:`scrub_secrets` applies the production ``redact_secret`` helper to
every string leaf of an already-built manifest.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

# Repository root containing ``experiments/``, ``src/`` and ``uv.lock``.
_DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Reasons recorded in ``null_reasons`` when an observed reranker leaf is null.
_RERANKER_NULL_REASONS: dict[str, str] = {
    "requested_backend": "reranker_requested_backend parameter not provided",
    "model": "no _model_id attribute on reranker object",
    "device": "no torch device attribute on reranker object",
    "execution_provider": "no loaded ONNX session on reranker object",
    "variant_or_precision": "no last_loaded_variant attribute on reranker object",
}


def sha256_file(path: str | Path) -> str:
    """Return the ``"sha256:<hex>"`` content identity of *path*.

    Raises:
        FileNotFoundError: Propagated from ``Path.read_bytes`` when *path*
            does not exist — identity hashing fails loudly by design.
    """
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return f"sha256:{digest}"


def _run_git(args: list[str], project_root: Path) -> subprocess.CompletedProcess[str] | None:
    """Run a git command in *project_root*, returning None when git is missing."""
    try:
        return subprocess.run(  # noqa: S603 — git is the intended binary
            ["git", *args],  # noqa: S607 — PATH resolution is intended
            capture_output=True,
            text=True,
            cwd=project_root,
            check=False,
        )
    except OSError:
        return None


def git_commit(project_root: Path) -> str | None:
    """Return ``git rev-parse HEAD`` inside *project_root*, or None on failure."""
    result = _run_git(["rev-parse", "HEAD"], project_root)
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip() or None


def git_dirty(project_root: Path) -> bool | None:
    """Return whether *project_root* has uncommitted changes (None on failure)."""
    result = _run_git(["status", "--porcelain"], project_root)
    if result is None or result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def lock_hash(project_root: Path) -> str | None:
    """Return the SHA-256 hex digest of ``uv.lock`` in *project_root*, or None."""
    try:
        data = (project_root / "uv.lock").read_bytes()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def observe_torch_device(obj: Any) -> str | None:
    """Return the torch device string of *obj*, or None.

    Checks ``last_loaded_device`` first (set by the torch backend on
    successful load), then the ``_cross_encoder`` object's ``device`` and
    ``model.device`` attributes.  Never imports torch and never raises on
    missing attributes — absence yields None.
    """
    recorded = getattr(obj, "last_loaded_device", None)
    if recorded is not None:
        return str(recorded)
    cross_encoder = getattr(obj, "_cross_encoder", None)
    if cross_encoder is None:
        return None
    device = getattr(cross_encoder, "device", None)
    if device is None:
        device = getattr(getattr(cross_encoder, "model", None), "device", None)
    return str(device) if device is not None else None


def observe_onnx_providers(reranker: Any) -> list[str] | None:
    """Return the ONNX Runtime execution providers of *reranker*, or None.

    Reads the ``_session`` attribute's ``get_providers()`` method.  Returns
    None when no session is loaded or the call fails, so an unobserved
    provider list stays distinguishable from an empty one.
    """
    session = getattr(reranker, "_session", None)
    if session is None:
        return None
    try:
        return [str(provider) for provider in session.get_providers()]
    except Exception:
        return None


def observe_reranker(reranker: Any, requested_backend: str | None) -> dict[str, Any]:
    """Return the D13 ``reranker`` section observed from a backend object.

    Reads only existing attributes (guarded with ``getattr``): the class
    ``backend_name`` falling back to the class name, ``_model_id``, the
    loaded ONNX session's providers, ``last_loaded_variant`` and the torch
    device.  Never raises on missing attributes.
    """
    return {
        "requested_backend": requested_backend,
        "effective_backend": getattr(reranker, "backend_name", type(reranker).__name__),
        "model": getattr(reranker, "_model_id", None),
        "device": observe_torch_device(reranker),
        "execution_provider": observe_onnx_providers(reranker),
        "variant_or_precision": getattr(reranker, "last_loaded_variant", None),
    }


def observe_chunking(result: Any) -> dict[str, Any]:
    """Return the D13 ``chunker`` section from a chunking result.

    Accepts a :class:`~omrg.core.chunking.code.CodeChunkResult`
    (attribute access) or a plain mapping with the keys ``requested`` /
    ``effective`` / ``fallback_reason``.  A ``fallback_reason`` of None
    means no fallback occurred.
    """
    if isinstance(result, Mapping):
        return {
            "requested": result.get("requested"),
            "effective": result.get("effective"),
            "fallback_reason": result.get("fallback_reason"),
        }
    return {
        "requested": getattr(result, "chunk_strategy_requested", None),
        "effective": getattr(result, "chunk_strategy_effective", None),
        "fallback_reason": getattr(result, "fallback_reason", None),
    }


def observe_document_reader(requested: str | None, effective: str | None = None) -> dict[str, Any]:
    """Return the D13 ``document_backend`` section for a PDF reader choice.

    When *effective* is None and *requested* is ``"auto"``, resolves through
    the production factory's private ``_resolve_auto`` probe (lazy import at
    call time; no reader is constructed here).  Any other requested value is
    its own effective value.
    """
    if effective is not None:
        resolved = effective
    elif requested == "auto":
        from omrg.integrations.pdf.factory import _resolve_auto

        resolved = _resolve_auto()
    else:
        resolved = requested
    return {"requested": requested, "effective": resolved}


def scrub_secrets(manifest: Mapping[str, Any], secrets: Iterable[str | None]) -> dict[str, Any]:
    """Return a scrubbed deep copy of *manifest* with *secrets* redacted.

    Applies the production ``redact_secret`` helper
    (``omrg.core.vectordb.identity``) to every string leaf, recursively
    across mappings and lists, so neither a full secret value nor a prefix
    of six or more characters survives.  The input manifest is never
    mutated; None/empty entries in *secrets* are ignored.
    """
    from omrg.core.vectordb.identity import redact_secret

    secret_values = [secret for secret in secrets if secret]

    def _scrub(value: Any) -> Any:
        if isinstance(value, str):
            for secret in secret_values:
                value = redact_secret(value, secret)
            return value
        if isinstance(value, Mapping):
            return {key: _scrub(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_scrub(item) for item in value]
        return value

    return _scrub(manifest)


def _section_from_mapping(
    source: Mapping[str, Any] | None,
    section: str,
    keys: tuple[str, ...],
    reasons: dict[str, str],
    none_by_design: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build one D13 section dict from a caller-provided mapping.

    A missing section yields all-None keys, each recorded in ``reasons``
    under its dotted path.  Within a provided section, keys listed in
    ``none_by_design`` may be legitimately None without a reason (the null
    itself is the signal, e.g. ``fallback_reason`` when no fallback
    occurred); every other None key is recorded as unavailable.
    """
    if source is None:
        block = {key: None for key in keys}
        for key in keys:
            reasons[f"{section}.{key}"] = f"{section} mapping not provided"
        return block
    block: dict[str, Any] = {}
    for key in keys:
        value = source.get(key)
        if value is None and key not in none_by_design:
            reasons[f"{section}.{key}"] = f"{key!r} missing from provided {section} mapping"
        block[key] = value
    return block


def build_runtime_manifest(
    *,
    experiment_id: str,
    protocol_version: str,
    embedding: Mapping[str, Any] | None = None,
    vector_store: Mapping[str, Any] | None = None,
    sparse: Mapping[str, Any] | None = None,
    reranker: Any = None,
    reranker_requested_backend: str | None = None,
    chunking: Mapping[str, Any] | None = None,
    document_backend: Mapping[str, Any] | None = None,
    retrieval: Mapping[str, Any] | None = None,
    corpus_path: str | Path | None = None,
    query_set_path: str | Path | None = None,
    qrels_path: str | Path | None = None,
    index_identity: str | None = None,
    project_root: str | Path | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a JSON-serialisable D13 runtime manifest for one experiment run.

    Sections whose inputs are unavailable become explicit ``None`` leaves
    plus a ``null_reasons`` entry naming the dotted field path — D13
    forbids silently omitted fields.  One designed exception:
    ``chunker.fallback_reason`` is ``None`` without a reason when a chunking
    observation exists and no fallback occurred.

    Args:
        experiment_id: Experiment protocol identifier.
        protocol_version: Experiment protocol version string.
        embedding: Mapping with ``requested_provider``, ``effective_provider``, ``model``.
        vector_store: Mapping with ``backend``, ``mode``, ``score_kind``.
        sparse: Mapping with ``requested_backend``, ``effective_backend``,
            ``cache_namespace``.
        reranker: Live reranker object observed via :func:`observe_reranker`,
            or None when reranking is off.
        reranker_requested_backend: Backend name from the injected settings.
        chunking: Mapping with ``requested``/``effective``/``fallback_reason``
            (build via :func:`observe_chunking`).
        document_backend: Mapping with ``requested``/``effective``
            (build via :func:`observe_document_reader`).
        retrieval: Mapping with ``top_k``, ``fetch_k``, ``hybrid``, ``rrf_k``,
            ``threshold``, ``threshold_score_kind``, ``rerank_policy_reason``.
        corpus_path: Corpus file hashed into ``corpus_identity``.
        query_set_path: Query-set file hashed into ``query_set_identity``.
        qrels_path: Qrels file hashed into ``qrels_identity``.
        index_identity: Immutable index identity; overrides the
            ``index_identity`` key inside *vector_store*.
        project_root: Repository root for git/lockfile facts (inject for
            tests); defaults to this module's repository.
        extra: Mapping merged over the top level — runners use it for
            fields outside the D13 contract (cell id, order, ...).

    Returns:
        The manifest dict.  ``json.dumps(..., sort_keys=True)`` runs before
        returning and its ``TypeError`` propagates, so non-JSON-safe values
        fail loudly instead of escaping into artefacts.

    Raises:
        FileNotFoundError: When a provided corpus/query/qrels path does not
            exist — identity hashing fails loudly rather than recording a
            silent null.
    """
    root = Path(project_root) if project_root is not None else _DEFAULT_PROJECT_ROOT
    reasons: dict[str, str] = {}

    commit = git_commit(root)
    if commit is None:
        reasons["repo_commit"] = "git rev-parse HEAD failed in project root"
    lock = lock_hash(root)
    if lock is None:
        reasons["dependency_lock_hash"] = "uv.lock not found at project root"
    dirty = git_dirty(root)
    if dirty is None:
        reasons["git_dirty"] = "git status failed in project root"

    def _identity(path: str | Path | None, field: str, param: str) -> str | None:
        if path is None:
            reasons[field] = f"{param} not provided"
            return None
        return sha256_file(path)

    embedding_block = _section_from_mapping(
        embedding,
        "embedding",
        ("requested_provider", "effective_provider", "model"),
        reasons,
    )

    # The explicit index_identity parameter wins over the mapping's key so
    # the authoritative index identity cannot be shadowed (design P2).
    vector_store_source: dict[str, Any] | None = (
        None if vector_store is None else dict(vector_store)
    )
    if index_identity is not None:
        vector_store_source = {**(vector_store_source or {}), "index_identity": index_identity}
    vector_store_block = _section_from_mapping(
        vector_store_source,
        "vector_store",
        ("backend", "mode", "index_identity", "score_kind"),
        reasons,
    )

    sparse_block = _section_from_mapping(
        sparse,
        "sparse",
        ("requested_backend", "effective_backend", "cache_namespace"),
        reasons,
    )

    if reranker is None:
        reranker_block: dict[str, Any] = {
            "requested_backend": reranker_requested_backend,
            "effective_backend": None,
            "model": None,
            "device": None,
            "execution_provider": None,
            "variant_or_precision": None,
        }
        if reranker_requested_backend is None:
            reasons["reranker.requested_backend"] = _RERANKER_NULL_REASONS["requested_backend"]
        for key in (
            "effective_backend",
            "model",
            "device",
            "execution_provider",
            "variant_or_precision",
        ):
            reasons[f"reranker.{key}"] = "reranker object not provided"
    else:
        reranker_block = observe_reranker(reranker, reranker_requested_backend)
        for key, value in reranker_block.items():
            if value is None and key in _RERANKER_NULL_REASONS:
                reasons[f"reranker.{key}"] = _RERANKER_NULL_REASONS[key]

    chunker_block = _section_from_mapping(
        chunking,
        "chunker",
        ("requested", "effective", "fallback_reason"),
        reasons,
        none_by_design=("fallback_reason",),
    )
    document_backend_block = _section_from_mapping(
        document_backend,
        "document_backend",
        ("requested", "effective"),
        reasons,
    )
    retrieval_block = _section_from_mapping(
        retrieval,
        "retrieval",
        (
            "top_k",
            "fetch_k",
            "hybrid",
            "rrf_k",
            "threshold",
            "threshold_score_kind",
            "rerank_policy_reason",
        ),
        reasons,
    )

    manifest: dict[str, Any] = {
        "repo_commit": commit,
        "dependency_lock_hash": lock,
        "experiment_id": experiment_id,
        "protocol_version": protocol_version,
        "corpus_identity": _identity(corpus_path, "corpus_identity", "corpus_path"),
        "query_set_identity": _identity(query_set_path, "query_set_identity", "query_set_path"),
        "qrels_identity": _identity(qrels_path, "qrels_identity", "qrels_path"),
        "embedding": embedding_block,
        "vector_store": vector_store_block,
        "sparse": sparse_block,
        "reranker": reranker_block,
        "chunker": chunker_block,
        "document_backend": document_backend_block,
        "retrieval": retrieval_block,
        # Extra-style provenance additions, mirroring experiment 18's manifest.
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_dirty": dirty,
        "null_reasons": reasons,
    }
    if extra is not None:
        manifest.update(extra)

    # Fail loudly on non-JSON-safe values before the manifest escapes.
    json.dumps(manifest, sort_keys=True)
    return manifest
