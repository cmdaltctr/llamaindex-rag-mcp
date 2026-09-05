"""Shared harness for Experiment 5 (reranker backend/device parity).

Implements the TDR-014 experiment-validity contract for a bounded
inference-only benchmark:

* D13 runtime manifests via ``experiments/_lib/manifest.py`` observers,
  reading production provenance seams (``last_loaded_variant``,
  ``last_loaded_device``, ``observe_onnx_providers``,
  ``observe_torch_device``) instead of re-deriving them;
* D14 provider/device preflight before any timing, with
  ``assert_manifest`` over the plan's universal assertions plus
  per-cell route assertions derived from the cell factors (single
  source of truth in ``plan.json``);
* D15 plan/runner cell agreement via ``plan.assert_runner_cells``;
* D16 per-query raw rows (``phase`` warmup/measured), statuses,
  ``cell_record``, warm-up exclusion;
* fresh child process per ``(cell, repetition)`` (``child_run.py``)
  so the production process-wide reranker cache cannot leak between
  routes; counterbalanced (rotated) cell order across repetitions;
* untimed model load (cold-start probe) and untimed warm-up pass, then
  >= 5 measured steady-state passes per repetition.

Only production reranker classes are measured:
``omrg.core.retrieval.reranker.CrossEncoderReranker`` (ONNX) and
``omrg.core.retrieval.reranker_torch.SentenceTransformerReranker``
(torch).  Device control happens at process level — the ONNX route
reads ``RERANK_ONNX_PROVIDER`` from the environment (production
behaviour), and the torch-CPU route hides MPS availability before the
model loads, mirroring the same class of environment-level factor
control without touching production code.  ``last_loaded_device``
therefore truthfully records the effective device.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
for _entry in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

#: Model scored in every cell (protocol section 5: same model ID).
MODEL_ID = "cross-encoder/ms-marco-MiniLM-L-6-v2"

#: Protocol section 3: fixed pool of 50 candidates, all re-scored.
TOP_K = 50

#: ONNX backend internal rerank batch size (production constant).
ONNX_BATCH_SIZE = 32

#: Protocol section 11: repetitions, warm-up, measured passes.
REPETITIONS = 3
WARMUP_PASSES = 1
MEASURED_PASSES = 5

#: Bootstrap seed for the summariser (D16 private-seed discipline).
SUMMARY_SEED = 20260819

WORKLOAD_PATH = SCRIPT_DIR / "workload.json"
PLAN_PATH = SCRIPT_DIR / "plan.json"


# ── Cell matrix (D15) ─────────────────────────────────────────────────


def build_cell_matrix() -> list[dict[str, Any]]:
    """Return the four execution-route cells (protocol section 4).

    Matches ``plan.json`` cells exactly; ``run_eval.py`` proves
    agreement via ``ExperimentPlan.assert_runner_cells`` before any
    measured work.
    """
    return [
        {
            "id": "onnx_cpu",
            "factors": {"backend": "onnx", "device": "cpu", "onnx_provider": "cpu"},
        },
        {
            "id": "onnx_coreml",
            "factors": {"backend": "onnx", "device": "coreml", "onnx_provider": "coreml"},
        },
        {
            "id": "torch_cpu",
            "factors": {"backend": "torch", "device": "cpu"},
        },
        {
            "id": "torch_mps",
            "factors": {"backend": "torch", "device": "mps"},
        },
    ]


def counterbalanced_order(cells: list[dict[str, Any]], repetition: int) -> list[dict[str, Any]]:
    """Rotate the cell list once per repetition (protocol section 10).

    Rotation gives a Latin-square-style counterbalancing with
    ``len(cells)`` repetitions; with three repetitions of four cells
    every cell starts a run at least once across the campaign.
    """
    if not cells:
        return []
    shift = repetition % len(cells)
    return cells[shift:] + cells[:shift]


# ── Workload identity (protocol section 9) ────────────────────────────


def workload_identity(path: Path | str = WORKLOAD_PATH) -> str:
    """Return ``sha256:<hex>`` of the committed workload file."""
    import hashlib

    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return f"sha256:{digest}"


def load_workload(path: Path | str = WORKLOAD_PATH) -> dict[str, Any]:
    """Load the fixed workload and check its declared shape."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    queries = payload["queries"]
    if payload["num_queries"] != len(queries):
        raise ValueError("workload num_queries disagrees with queries length")
    for query in queries:
        if len(query["candidates"]) != payload["candidates_per_query"]:
            raise ValueError(f"workload query {query['query_id']} has wrong candidate count")
    return payload


# ── Route policy: environment-level factor control ────────────────────


def route_env_overrides(cell: dict[str, Any]) -> dict[str, str]:
    """Environment variables the child sets before importing production.

    The ONNX route selects its execution provider through the
    production-read ``RERANK_ONNX_PROVIDER`` variable.  All children run
    with ``HF_HUB_OFFLINE=1`` so a cache miss fails loudly instead of
    contaminating the run with a model download (protocol section 12).
    """
    env = {"HF_HUB_OFFLINE": "1"}
    factors = cell["factors"]
    if factors["backend"] == "onnx":
        env["RERANK_ONNX_PROVIDER"] = str(factors["onnx_provider"])
    return env


def apply_device_policy(cell: dict[str, Any]) -> None:
    """Force the torch route onto the cell's declared device.

    Production exposes no device parameter for
    ``SentenceTransformerReranker``: sentence-transformers resolves
    ``device=None`` through ``get_device_name()``, which returns
    ``"mps"`` whenever MPS is available.  For the ``torch_cpu`` cell the
    child hides MPS availability *before* the model loads, so the
    production class itself lands on CPU and its
    ``last_loaded_device`` seam records the truth.  The ``torch_mps``
    cell needs no intervention — default resolution selects MPS on
    supported Apple Silicon, and preflight verifies it.
    """
    factors = cell["factors"]
    if factors["backend"] != "torch":
        return
    if factors["device"] == "cpu":
        import torch

        torch.backends.mps.is_available = lambda: False  # noqa: B010
    elif factors["device"] == "mps":
        return
    else:  # pragma: no cover — plan agreement blocks other levels
        raise ValueError(f"unsupported torch device factor {factors['device']!r}")


# ── Production reranker construction ──────────────────────────────────


def construct_reranker(cell: dict[str, Any], model_id: str = MODEL_ID) -> Any:
    """Build the production reranker class for *cell* (nothing else)."""
    factors = cell["factors"]
    if factors["backend"] == "onnx":
        from omrg.core.retrieval.reranker import CrossEncoderReranker

        return CrossEncoderReranker(model_id=model_id)
    if factors["backend"] == "torch":
        from omrg.core.retrieval.reranker_torch import SentenceTransformerReranker

        return SentenceTransformerReranker(model_id=model_id)
    raise ValueError(f"unsupported backend factor {factors['backend']!r}")


# ── Route preflight (D14, protocol section 12) ────────────────────────


def assert_effective_route(cell: dict[str, Any], reranker: Any) -> dict[str, Any]:
    """Prove the requested route is the effective one, before timing.

    ONNX cells: the loaded session's provider list must place the
    declared provider first — production registers
    ``["CoreMLExecutionProvider", "CPUExecutionProvider"]`` only when
    CoreML was requested *and* is installed, so a first-position match
    is exactly the no-silent-CPU-only-fallback proof protocol section
    12 demands.  Torch cells: ``observe_torch_device`` (which reads the
    production ``last_loaded_device`` seam) must start with the
    declared device.

    Returns the observed route facts for the manifest ``extra`` block.

    Raises:
        AssertionError: Naming the requested and effective route.
    """
    from experiments._lib.manifest import (
        observe_onnx_providers,
        observe_torch_device,
    )

    factors = cell["factors"]
    observed: dict[str, Any] = {}
    if factors["backend"] == "onnx":
        providers = observe_onnx_providers(reranker)
        observed["onnx_effective_providers"] = providers
        expected_first = (
            "CoreMLExecutionProvider"
            if factors["onnx_provider"] == "coreml"
            else "CPUExecutionProvider"
        )
        if not providers:
            raise AssertionError(
                f"cell {cell['id']}: no loaded ONNX session providers observed "
                f"(requested provider {expected_first!r})"
            )
        if providers[0] != expected_first:
            raise AssertionError(
                f"cell {cell['id']}: requested provider {expected_first!r} but "
                f"effective providers are {providers!r} — silent fallback"
            )
    else:
        device = observe_torch_device(reranker)
        observed["torch_effective_device"] = device
        expected = str(factors["device"])
        if device is None:
            raise AssertionError(
                f"cell {cell['id']}: no torch device observed (requested {expected!r})"
            )
        if not str(device).startswith(expected):
            raise AssertionError(
                f"cell {cell['id']}: requested torch device {expected!r} but "
                f"effective device is {device!r}"
            )
    return observed


def detect_inference_fallback(reranker: Any, ranked: list[dict]) -> str | None:
    """Return the production fallback reason if a rerank call degraded.

    Both production classes set ``last_failure_reason`` and mark results
    ``_reranked=False`` when inference fails, silently returning
    un-reranked output (protocol section 13 abort criterion).  This
    check runs after every rerank call so a degraded cell can never
    contribute timing or scores.
    """
    reason = getattr(reranker, "last_failure_reason", None)
    if reason is not None:
        return str(reason)
    unranked = [r for r in ranked if not r.get("_reranked", False)]
    if unranked:
        return (
            f"{len(unranked)}/{len(ranked)} results returned without "
            "reranker scores (_reranked=False)"
        )
    return None


# ── Runtime manifest (D13) ────────────────────────────────────────────


def build_cell_manifest(
    *,
    cell: dict[str, Any],
    reranker: Any,
    experiment_id: str,
    protocol_version: str,
    workload_path: Path | str = WORKLOAD_PATH,
    route_facts: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the per-child D13 manifest through the shared builder.

    The workload file doubles as corpus and query set (candidates and
    queries are one committed artefact), so both identities hash the
    same file; ``qrels`` is deliberately absent — this benchmark has no
    relevance judgements — and the builder records that as an explicit
    null reason.  Embedding, vector-store, sparse and document-backend
    sections are absent by design (inference-only benchmark); their
    null reasons make the absence explicit per D13.
    """
    from experiments._lib.manifest import build_runtime_manifest

    payload: dict[str, Any] = build_runtime_manifest(
        experiment_id=experiment_id,
        protocol_version=protocol_version,
        reranker=reranker,
        reranker_requested_backend=str(cell["factors"]["backend"]),
        retrieval={
            "top_k": TOP_K,
            "fetch_k": TOP_K,
            "hybrid": False,
            "rrf_k": None,
            "threshold": None,
            "threshold_score_kind": None,
            "rerank_policy_reason": None,
        },
        corpus_path=str(workload_path),
        query_set_path=str(workload_path),
        project_root=PROJECT_ROOT,
        extra={
            "cell_id": cell["id"],
            "cell_factors": dict(cell["factors"]),
            "workload_identity": workload_identity(workload_path),
            **(route_facts or {}),
            **(extra or {}),
        },
    )
    return payload


def preflight_cell(
    *,
    cell: dict[str, Any],
    reranker: Any,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Run the full untimed D14 preflight for one loaded route.

    Order: per-cell route proof (whose observed facts are merged into
    the manifest so H5 evidence lives in the artefact itself), plan
    assertions, no-fallback.  Any ``PreflightError`` /
    ``AssertionError`` propagates so the child records the cell invalid
    before any timing begins.  Returns the observed route facts.
    """
    from experiments._lib import preflight as preflight_lib

    route_facts = assert_effective_route(cell, reranker)
    manifest.update(route_facts)
    preflight_lib.assert_manifest(manifest, _plan_preflight_assertions())
    preflight_lib.assert_no_fallback(manifest)
    return route_facts


_PLAN_CACHE: dict[str, Any] = {}


def _plan_preflight_assertions() -> list[dict[str, Any]]:
    """Load and memoise the plan's universal preflight assertions."""
    if "assertions" not in _PLAN_CACHE:
        _PLAN_CACHE["assertions"] = json.loads(PLAN_PATH.read_text(encoding="utf-8"))[
            "preflight_assertions"
        ]
    return _PLAN_CACHE["assertions"]


# ── Measured execution ────────────────────────────────────────────────


def run_workload_pass(
    *,
    reranker: Any,
    workload: dict[str, Any],
    cell_id: str,
    repetition: int,
    pass_index: int,
    phase: str,
) -> tuple[list[dict[str, Any]], float]:
    """Score every workload query once; return per-query rows and total s.

    Each query gets a deep copy of its candidate pool because both
    production classes mutate result dicts in place (``score``,
    ``_reranked``).  ``top_k`` equals the pool size so every candidate
    is re-scored and the full ranking is returned (parity analysis
    needs all 50 scores, protocol section 7).
    """
    rows: list[dict[str, Any]] = []
    fallbacks: list[str] = []
    pass_start = time.perf_counter()
    for query in workload["queries"]:
        candidates = [
            {"text": candidate["text"], "score": 0.0, "doc_id": candidate["doc_id"]}
            for candidate in query["candidates"]
        ]
        started = time.perf_counter()
        ranked = reranker.rerank(query["text"], candidates, top_k=TOP_K)
        latency_ms = (time.perf_counter() - started) * 1000.0

        reason = detect_inference_fallback(reranker, ranked)
        if reason is not None:
            fallbacks.append(f"{query['query_id']}: {reason}")
            continue

        scores = {r["doc_id"]: float(r["score"]) for r in ranked}
        ranking = [r["doc_id"] for r in ranked]
        rows.append(
            {
                "cell_id": cell_id,
                "query_id": query["query_id"],
                "phase": phase,
                "pass_index": pass_index,
                "repetition": repetition,
                "latency_ms": latency_ms,
                "margin_class": query["margin_class"],
                "metrics": {
                    "scores": scores,
                    "ranking": ranking,
                },
            }
        )
    if fallbacks:
        raise RuntimeError(
            "production reranker fallback during pass "
            f"({phase} pass {pass_index}): " + "; ".join(fallbacks[:3])
        )
    return rows, time.perf_counter() - pass_start


# ── Cold-start probe (untimed metric, protocol section 7) ─────────────


def cold_start_probe(reranker: Any) -> tuple[float, str]:
    """Trigger the lazy production load with one trivial rerank call.

    Returns ``(cold_start_s, fallback_reason_or_empty)``.  The probe is
    untimed with respect to steady-state latency — its wall time is
    recorded as the cold-start dependent variable only.  Production
    exposes no public load trigger, so one single-pair rerank call is
    the smallest public-API load probe.
    """
    probe = [{"text": "probe passage", "score": 0.0, "doc_id": "probe"}]
    started = time.perf_counter()
    reranker.rerank("probe query", probe, top_k=1)
    elapsed = time.perf_counter() - started
    reason = detect_inference_fallback(reranker, probe)
    return elapsed, reason or ""


# ── Child process plumbing ────────────────────────────────────────────


def child_argv(
    *,
    cell_id: str,
    repetition: int,
    output_dir: Path,
    measured_passes: int,
    warmup_passes: int,
    dry_run: bool,
) -> list[str]:
    """Argument vector for one fresh child process (protocol section 5)."""
    argv = [
        str(SCRIPT_DIR / "child_run.py"),
        "--cell",
        cell_id,
        "--repetition",
        str(repetition),
        "--output-dir",
        str(output_dir),
        "--measured-passes",
        str(measured_passes),
        "--warmup-passes",
        str(warmup_passes),
    ]
    if dry_run:
        argv.append("--dry-run")
    return argv


def child_result_path(output_dir: Path, cell_id: str, repetition: int) -> Path:
    """Canonical result path for one (cell, repetition) child."""
    return output_dir / "children" / f"{cell_id}__rep{repetition}.json"


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Serialise, write to ``.tmp``, then rename (TDR-014 rule 7)."""
    import os

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def torch_predict_default_batch_size(reranker: Any) -> int | None:
    """Observe the torch backend's effective predict batch size.

    The production torch class never passes ``batch_size`` to
    ``CrossEncoder.predict``; this reads the installed library's
    declared default so the manifest records the actual value rather
    than an assumption (protocol section 5: same batch size across
    cells — verified against the ONNX constant at summarise time).
    """
    cross_encoder = getattr(reranker, "_cross_encoder", None)
    if cross_encoder is None:
        return None
    import inspect

    parameters = inspect.signature(cross_encoder.predict).parameters
    batch = parameters.get("batch_size")
    if batch is None or batch.default is inspect.Parameter.empty:
        return None
    return int(batch.default)
