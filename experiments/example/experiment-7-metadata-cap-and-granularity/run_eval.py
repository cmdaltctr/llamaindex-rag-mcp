"""Run Experiment 7: metadata extraction cap and persisted granularity.

Executes the pre-registered protocol (``protocol.md`` v1.0) as written:

- Six cells: ``max_chunks`` {1, 3, 10} x document {synthetic divergence,
  realistic Markdown}.  Each cell ingests one fixture through the
  PRODUCTION path ``read_and_chunk_file_async`` with
  ``extraction_mode="llamaindex"`` and ``LLAMANDEX_EXTRACTOR_MAX_CHUNKS``
  set to the cell's cap.
- Two harness-only seams (no production file is edited):
  1. ``rag_mcp.core.providers.llm.registry.get`` is replaced with a
     factory returning :class:`fake_llm.CountingMockLLM` — deterministic
     outputs, full call accounting, no network, no Ollama.
  2. ``llama_index.core.ingestion.IngestionPipeline.arun`` is wrapped to
     record the exact node texts entering the extractor pipeline (the
     capped chunk selection) before delegating to the real pipeline.
- Observations per cell: capped node hashes (H1/H2 vs
  ``fixtures/expected_chunks.json``), fake call log (H5), aggregated
  file-level metadata and its uniform presence on every final stored
  chunk (H3), ``metadata_granularity`` manifest declaration (H4).
- Preflight per cell (D13/D14): plan assertions, ``assert_no_fallback``;
  a degraded extraction or an empty call log aborts the cell (protocol
  section 13: a real LLM was accidentally used).
- D16 rows, atomic checkpoints, ``--resume``, ``--verify-rerun`` byte
  comparison — same contract as the Stage 4 runners.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from experiments._lib import manifest as manifest_lib  # noqa: E402
from experiments._lib import preflight, stats  # noqa: E402
from experiments._lib.plan import ExperimentPlan  # noqa: E402
from fake_llm import CountingMockLLM, summarise_calls  # noqa: E402

from rag_mcp.core.ingestion.chunker import read_and_chunk_file_async  # noqa: E402
from rag_mcp.core.settings import EffectiveSettings, MetadataBlock  # noqa: E402

EXPERIMENT_ID = "example-experiment-7-metadata-cap-and-granularity"
PROTOCOL_VERSION = "1.0"
PLAN_PATH = SCRIPT_DIR / "plan.json"
FIXTURES_DIR = SCRIPT_DIR / "fixtures"
EXPECTED_PATH = FIXTURES_DIR / "expected_chunks.json"
PRE_REGISTRATION_PATH = FIXTURES_DIR / "manifest.json"
OUTPUT_DIR = SCRIPT_DIR / "output"
CELLS_DIR = OUTPUT_DIR / "cells"
MANIFESTS_DIR = OUTPUT_DIR / "manifests"
CHECKPOINT_PATH = OUTPUT_DIR / "checkpoint.json"

DOC_FILES = {
    "synthetic": "synthetic_token_char_divergence.txt",
    "realistic_md": "realistic_long_document.md",
}
METADATA_KEYS = ("category", "keywords", "summary", "document_title")


def build_cell_matrix() -> list[dict[str, Any]]:
    """Return the six-cell matrix declared by plan.json."""
    return [
        {"id": f"M{cap}__{doc}", "factors": {"max_chunks": cap, "document": doc}}
        for cap in (1, 3, 10)
        for doc in DOC_FILES
    ]


def build_settings() -> EffectiveSettings:
    """Return the controlled settings shared by every cell."""
    return EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="llamaindex"),
    )


class HarnessPatches:
    """Install and always restore the two harness observation seams."""

    def __init__(self) -> None:
        self.fake_llm = CountingMockLLM()
        self.captured_batches: list[list[str]] = []
        self._undo: list[Any] = []

    def __enter__(self) -> HarnessPatches:
        from llama_index.core.ingestion import IngestionPipeline

        import rag_mcp.core.providers.llm.registry as llm_registry

        original_get = llm_registry.get
        # ``arun`` carries a wrapt-style decorator, so class access yields a
        # BoundFunctionWrapper that refuses an explicit instance argument.
        # Unwrap to the raw function; delegation then binds the instance
        # explicitly.
        original_arun = getattr(IngestionPipeline.arun, "__wrapped__", IngestionPipeline.arun)
        harness = self

        def fake_get(name: str) -> Any:
            def factory(settings: Any, timeout: float | None = None) -> Any:
                return harness.fake_llm

            return factory

        async def recording_arun(self_pipeline: Any, *args: Any, **kwargs: Any) -> Any:
            nodes = kwargs.get("nodes")
            if nodes is None and args:
                nodes = args[0]
            if nodes is not None:
                harness.captured_batches.append([node.get_content() for node in nodes])
            return await original_arun(self_pipeline, *args, **kwargs)

        llm_registry.get = fake_get
        IngestionPipeline.arun = recording_arun
        self._undo = [
            lambda: setattr(llm_registry, "get", original_get),
            lambda: setattr(IngestionPipeline, "arun", original_arun),
        ]
        return self

    def __exit__(self, *exc_info: Any) -> None:
        for undo in self._undo:
            undo()


def expected_for(document: str, expected: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the ground-truth chunk list for one document."""
    return expected["documents"][document]["chunks"]


def build_cell_manifest(cell: dict[str, Any], fake_calls: dict[str, Any]) -> dict[str, Any]:
    """Build the D13 runtime manifest for one cell (metadata experiment)."""
    return manifest_lib.build_runtime_manifest(
        experiment_id=EXPERIMENT_ID,
        protocol_version=PROTOCOL_VERSION,
        chunking={
            "requested": "sentence",
            "effective": "sentence",
            "fallback_reason": None,
        },
        corpus_path=PRE_REGISTRATION_PATH,
        extra={
            "cell_id": cell["id"],
            "max_chunks": cell["factors"]["max_chunks"],
            "document": cell["factors"]["document"],
            "metadata_granularity": "file_aggregate",
            "chunking_settings": {"chunk_size": 512, "chunk_overlap": 100},
            "fake_llm_calls": fake_calls,
        },
    )


def atomic_write_json(path: Path, payload: Any) -> None:
    """Serialise to a .tmp file then atomically rename (TDR-014 rule 7)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def final_metadata_signature(final_nodes: list[Any]) -> dict[str, Any]:
    """Extract the file-level metadata keys from final stored chunks."""
    signatures = []
    for node in final_nodes:
        signatures.append({key: node.metadata.get(key) for key in METADATA_KEYS})
    uniform = all(signature == signatures[0] for signature in signatures) if signatures else False
    return {"uniform_across_final_chunks": uniform, "value": signatures[0] if signatures else None}


async def run_cell(
    cell: dict[str, Any],
    plan: ExperimentPlan,
    expected: dict[str, Any],
    *,
    cells_dir: Path,
    manifests_dir: Path,
) -> dict[str, Any]:
    """Execute one cell: patch seams, ingest, observe, preflight, checkpoint."""
    cell_id = cell["id"]
    cap = cell["factors"]["max_chunks"]
    document = cell["factors"]["document"]
    doc_path = FIXTURES_DIR / DOC_FILES[document]
    doc_expected = expected_for(document, expected)
    if len(doc_expected) <= cap:
        raise preflight.PreflightError(
            f"{cell_id}: document has {len(doc_expected)} chunks <= cap {cap}"
        )

    saved_env = os.environ.get("LLAMANDEX_EXTRACTOR_MAX_CHUNKS")
    os.environ["LLAMANDEX_EXTRACTOR_MAX_CHUNKS"] = str(cap)
    try:
        with HarnessPatches() as harness:
            result = await read_and_chunk_file_async(doc_path, settings=build_settings())
            captured = list(harness.captured_batches)
            calls = list(harness.fake_llm.calls)
    finally:
        if saved_env is None:
            os.environ.pop("LLAMANDEX_EXTRACTOR_MAX_CHUNKS", None)
        else:
            os.environ["LLAMANDEX_EXTRACTOR_MAX_CHUNKS"] = saved_env

    degraded = bool(getattr(result, "metadata_degraded", False))
    if degraded or not calls:
        raise preflight.PreflightError(
            f"{cell_id}: metadata path degraded={degraded} with {len(calls)} fake calls — "
            "the deterministic fake extractor was not the LLM in play (protocol section 13)"
        )
    if len(captured) != 1:
        raise preflight.PreflightError(
            f"{cell_id}: expected exactly one extractor pipeline batch, saw {len(captured)}"
        )

    capped_texts = captured[0]
    capped_hashes = [hashlib.sha256(text.encode("utf-8")).hexdigest() for text in capped_texts]
    expected_prefix = [chunk["sha256"] for chunk in doc_expected[:cap]]
    final_nodes = list(result)
    signature = final_metadata_signature(final_nodes)

    call_summary = summarise_calls(calls)
    manifest = build_cell_manifest(cell, call_summary)
    preflight.assert_manifest(manifest, plan.required_manifest_assertions)
    preflight.assert_no_fallback(manifest)
    manifests_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(manifests_dir / f"{cell_id}.manifest.json", manifest)

    # Locked call pattern (llama-index 0.14.23): KeywordExtractor and
    # SummaryExtractor run once per capped node; TitleExtractor extracts
    # candidates from at most its ``nodes`` (production passes
    # min(5, len(capped))) documents plus one combine call per document.
    expected_call_count = 2 * len(capped_texts) + min(5, len(capped_texts)) + 1
    metrics = {
        "cap": cap,
        "document": document,
        "expected_total_chunks": len(doc_expected),
        "observed_selected_chunks": len(capped_hashes),
        "selected_hashes_match_first_n": capped_hashes == expected_prefix,
        "expected_selected_hashes": expected_prefix,
        "observed_selected_hashes": capped_hashes,
        "fake_llm_total_calls": call_summary["total_calls"],
        "expected_llm_calls_analytic": expected_call_count,
        "calls_match_analytic": call_summary["total_calls"] == expected_call_count,
        "final_chunk_count": len(final_nodes),
        "final_metadata_uniform": signature["uniform_across_final_chunks"],
        "final_metadata": signature["value"],
        "metadata_degraded": degraded,
    }
    row = {
        "cell_id": cell_id,
        "query_id": document,
        "phase": "measured",
        "latency_ms": 0.0,
        "metrics": metrics,
    }
    stats.validate_per_query_rows([row])
    payload = {
        "cell_id": cell_id,
        "factors": cell["factors"],
        "manifest_path": f"output/manifests/{cell_id}.manifest.json",
        "rows": [row],
        "fake_call_summary": call_summary,
        "final_chunk_sha256": [
            hashlib.sha256(node.get_content().encode("utf-8")).hexdigest() for node in final_nodes
        ],
    }
    atomic_write_json(cells_dir / f"{cell_id}.json", payload)
    print(
        f"[{cell_id}] selected {len(capped_hashes)}/{len(doc_expected)} chunks, "
        f"{call_summary['total_calls']} calls, final metadata uniform="
        f"{signature['uniform_across_final_chunks']}",
        file=sys.stderr,
    )
    return stats.cell_record(status="complete", cell_id=cell_id)


def load_checkpoint() -> set[str]:
    """Return completed cell ids from the checkpoint file."""
    if not CHECKPOINT_PATH.exists():
        return set()
    return set(json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))["completed"])


def save_checkpoint(completed: list[str]) -> None:
    atomic_write_json(CHECKPOINT_PATH, {"completed": completed})


def ground_truth_preflight(expected: dict[str, Any], pre_registration: dict[str, Any]) -> None:
    """Protocol section 12 preflight over the frozen ground truth."""
    if not pre_registration.get("written_before_treatments"):
        raise preflight.PreflightError("fixture manifest lacks the pre-registration flag")
    synthetic = expected["documents"]["synthetic"]
    if synthetic["token_char_divergence_ratio"] < 1.5:
        raise preflight.PreflightError("synthetic token/char divergence below 1.5")
    for document, entry in expected["documents"].items():
        if entry["chunk_count"] <= 10:
            raise preflight.PreflightError(f"{document}: {entry['chunk_count']} chunks <= 10")


async def run_all(cells_dir: Path, manifests_dir: Path, *, resume: bool) -> list[dict[str, Any]]:
    """Run all six cells with plan agreement and controlled constants."""
    plan = ExperimentPlan.from_json(PLAN_PATH)
    plan.assert_runner_cells(build_cell_matrix())
    expected = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    pre_registration = json.loads(PRE_REGISTRATION_PATH.read_text(encoding="utf-8"))
    ground_truth_preflight(expected, pre_registration)

    completed = load_checkpoint() if resume else set()
    records: list[dict[str, Any]] = []
    manifests_by_cell: dict[str, dict[str, Any]] = {}
    for cell in build_cell_matrix():
        if cell["id"] in completed:
            print(f"skipping completed cell {cell['id']} (--resume)", file=sys.stderr)
            manifests_by_cell[cell["id"]] = json.loads(
                (manifests_dir / f"{cell['id']}.manifest.json").read_text(encoding="utf-8")
            )
            records.append(stats.cell_record(status="complete", cell_id=cell["id"], resumed=True))
            continue
        records.append(
            await run_cell(cell, plan, expected, cells_dir=cells_dir, manifests_dir=manifests_dir)
        )
        manifests_by_cell[cell["id"]] = json.loads(
            (manifests_dir / f"{cell['id']}.manifest.json").read_text(encoding="utf-8")
        )
        save_checkpoint(sorted(load_checkpoint() | {cell["id"]}))

    preflight.assert_controlled_constant(
        manifests_by_cell,
        [
            "corpus_identity",
            "dependency_lock_hash",
            "chunking_settings.chunk_size",
            "chunking_settings.chunk_overlap",
        ],
    )
    return records


async def verify_rerun() -> int:
    """Re-run all cells into a scratch dir and byte-compare cell JSON."""
    scratch_cells = OUTPUT_DIR / "verify-rerun" / "cells"
    scratch_manifests = OUTPUT_DIR / "verify-rerun" / "manifests"
    await run_all(scratch_cells, scratch_manifests, resume=False)

    checked: list[dict[str, Any]] = []
    byte_identical = True
    for cell in build_cell_matrix():
        recorded = (CELLS_DIR / f"{cell['id']}.json").read_bytes()
        rerun = (scratch_cells / f"{cell['id']}.json").read_bytes()
        same = recorded == rerun
        byte_identical = byte_identical and same
        checked.append(
            {
                "cell_id": cell["id"],
                "byte_identical": same,
                "recorded_sha256": hashlib.sha256(recorded).hexdigest(),
                "rerun_sha256": hashlib.sha256(rerun).hexdigest(),
            }
        )
    atomic_write_json(
        OUTPUT_DIR / "verify_rerun.json",
        {"byte_identical": byte_identical, "checked": checked},
    )
    shutil.rmtree(OUTPUT_DIR / "verify-rerun")
    print(f"verify-rerun byte_identical={byte_identical}", file=sys.stderr)
    return 0 if byte_identical else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true", help="skip completed cells")
    parser.add_argument(
        "--verify-rerun",
        action="store_true",
        help="re-execute all cells and byte-compare with the recorded run",
    )
    args = parser.parse_args()

    if args.verify_rerun:
        return asyncio.run(verify_rerun())
    records = asyncio.run(run_all(CELLS_DIR, MANIFESTS_DIR, resume=args.resume))
    print(json.dumps({"cells": records}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
