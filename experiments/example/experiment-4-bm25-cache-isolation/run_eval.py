"""Run Example Experiment 4: BM25 cache isolation (task 5.4).

Executes the pre-registered protocol ``protocol.md`` v1.0 AS WRITTEN:
the full 9-step namespace sequence per backend block (ChromaDB AND
LanceDB), forward AND reversed initial query order (§10), in ONE
process so cache-sharing bugs can manifest (§5).

Contracts honoured (TDR-014): plan/cell agreement before measured
work; one D13 runtime manifest per cell (hybrid active, so
``sparse.effective_backend`` is non-null and honest about the internal
BM25Okapi fallback because ``rank_bm25`` is not installed); D14
preflight per cell including the protocol §12 battery (distinct
instances, literal ``documents`` collections, contents differ,
collision generations equal, cache starts empty); D16 rows via
``stats.validate_per_query_rows``; atomic ``.tmp`` → rename checkpoint
after every cell with ``--resume``; controlled constants pinned across
cells; temporary store directories deleted after raw results are saved
(§20).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from battery import run_battery  # noqa: E402
from experiments._lib import manifest as manifest_lib  # noqa: E402
from experiments._lib import preflight, stats  # noqa: E402
from experiments._lib.plan import ExperimentPlan  # noqa: E402

EXPERIMENT_ID = "example-experiment-4-bm25-cache-isolation"
PROTOCOL_VERSION = "1.0"
PLAN_PATH = SCRIPT_DIR / "plan.json"
FIXTURES_DIR = SCRIPT_DIR / "fixtures"
TOP_N = 5


def build_cell_matrix() -> list[dict[str, Any]]:
    """Return the runner cell matrix (must match ``plan.json``)."""
    return [
        {"id": f"{backend}_{order}", "factors": {"backend": backend, "sequence_order": order}}
        for backend in ("chroma", "lancedb")
        for order in ("forward", "reversed")
    ]


def _atomic_write(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _cell_manifest(
    cell: dict[str, Any],
    battery_result: dict[str, Any],
    corpus_path: Path,
    queries_path: Path,
    qrels_path: Path,
) -> dict[str, Any]:
    backend = cell["factors"]["backend"]
    corpus_identity = manifest_lib.sha256_file(corpus_path)
    return manifest_lib.build_runtime_manifest(
        experiment_id=EXPERIMENT_ID,
        protocol_version=PROTOCOL_VERSION,
        embedding={
            "requested_provider": "precomputed",
            "effective_provider": "precomputed",
            "model": "fixed-fixture-vectors",
        },
        vector_store={
            "backend": backend,
            "mode": "local",
            "score_kind": "dense_similarity_v1",
        },
        # rank_bm25 is not installed: the internal deterministic
        # BM25Okapi mirror serves the sparse path (sparse.py:142-151).
        sparse={
            "requested_backend": "bm25",
            "effective_backend": "bm25-internal-okapi",
            "cache_namespace": "(store.cache_identity, collection_name)",
        },
        retrieval={
            "top_k": TOP_N,
            "hybrid": True,
            "threshold": 0.0,
            "threshold_score_kind": "not_applied",
        },
        corpus_path=corpus_path,
        query_set_path=queries_path,
        qrels_path=qrels_path,
        index_identity=f"exp4-namespaces::{backend}::{corpus_identity.removeprefix('sha256:')[:12]}",
        project_root=PROJECT_ROOT,
        extra={
            "cell_id": cell["id"],
            "sequence_order": cell["factors"]["sequence_order"],
            "preflight": battery_result["preflight_observations"],
        },
    )


def run(output_dir: Path, resume: bool) -> dict[str, Any]:
    # Store reads (paged iter_documents) resolve the default page size
    # through the process default settings; install a no-LLM default.
    from omrg.core.settings import (
        EffectiveSettings,
        MetadataBlock,
        set_default_effective_settings,
    )

    set_default_effective_settings(
        EffectiveSettings(metadata=MetadataBlock(extraction_mode="disabled"))
    )

    plan = ExperimentPlan.from_json(PLAN_PATH)
    plan.assert_runner_cells(build_cell_matrix())

    corpus = json.loads((FIXTURES_DIR / "docs.json").read_text(encoding="utf-8"))
    corpus_path = FIXTURES_DIR / "docs.json"
    queries_path = FIXTURES_DIR / "queries.json"
    qrels_path = FIXTURES_DIR / "qrels.json"

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "results.raw.json"
    cells_dir = output_dir / "cells"
    cells_dir.mkdir(exist_ok=True)

    raw: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID,
        "protocol_version": PROTOCOL_VERSION,
        "plan_cells": plan.cell_dicts(),
        "cleanup": [],
        "rows": [],
        "cells": {},
        "manifests": {},
        "battery_results": {},
    }
    if resume and raw_path.exists():
        raw = json.loads(raw_path.read_text(encoding="utf-8"))

    deleted: list[str] = []
    try:
        for cell in build_cell_matrix():
            cell_id = cell["id"]
            if cell_id in raw["cells"]:
                continue
            tmp_root = Path(tempfile.mkdtemp(prefix=f"exp4_{cell_id}_"))
            deleted.append(str(tmp_root))
            try:
                battery_result = run_battery(
                    cell["factors"]["backend"],
                    cell["factors"]["sequence_order"],
                    corpus,
                    tmp_root,
                    top_n=TOP_N,
                )
            finally:
                shutil.rmtree(tmp_root, ignore_errors=True)

            manifest = _cell_manifest(cell, battery_result, corpus_path, queries_path, qrels_path)
            preflight.assert_manifest(manifest, plan.required_manifest_assertions)

            for row in battery_result["rows"]:
                row["cell_id"] = cell_id
            stats.validate_per_query_rows(battery_result["rows"])

            raw["rows"].extend(battery_result["rows"])
            raw["manifests"][cell_id] = manifest
            raw["battery_results"][cell_id] = {
                "mutation_trace": battery_result["mutation_trace"],
                "build_counters": battery_result["build_counters"],
                "cache_key_mechanism": battery_result["cache_key_mechanism"],
                "preflight_observations": battery_result["preflight_observations"],
            }
            raw["cells"][cell_id] = stats.cell_record(
                status="complete",
                rows=len(battery_result["rows"]),
                mutations=len(battery_result["mutation_trace"]),
            )
            _atomic_write(raw_path, raw)
            _atomic_write(cells_dir / f"{cell_id}.json", raw["cells"][cell_id])
    finally:
        raw["cleanup"] = sorted(set(deleted))
        _atomic_write(raw_path, raw)

    preflight.assert_controlled_constant(
        raw["manifests"],
        [
            "corpus_identity",
            "query_set_identity",
            "qrels_identity",
            "sparse.effective_backend",
            "retrieval.top_k",
            "vector_store.score_kind",
        ],
    )
    _atomic_write(raw_path, raw)
    return raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=SCRIPT_DIR / "output" / "run1",
        help="Directory for raw artefacts (default: output/run1)",
    )
    parser.add_argument("--resume", action="store_true", help="Skip completed cells")
    args = parser.parse_args()
    raw = run(args.output_dir, args.resume)
    total_mutations = sum(len(br["mutation_trace"]) for br in raw["battery_results"].values())
    print(
        f"rows={len(raw['rows'])} cells={sorted(raw['cells'])} "
        f"mutations={total_mutations} -> {args.output_dir / 'results.raw.json'}",
        flush=True,
    )


if __name__ == "__main__":
    main()
