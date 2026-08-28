"""Run Experiment 1: SentenceSplitter vs CodeSplitter structural integrity.

Executes the pre-registered protocol (``protocol.md`` v1.0) as written:

- Two cells over the SAME 18 committed fixtures: ``S`` (sentence control,
  generic document path) and ``C`` (AST-aware CodeSplitter treatment via
  the production ``content_type`` dispatch in
  ``rag_mcp.core.ingestion.chunker.read_and_chunk_file_async``).
- Structural-only execution; the optional H4 retrieval arm is NOT run
  (requires an embedding runtime; H1-H3 are the correctness gates).
- Every cell builds a D13 runtime manifest and passes the D14 preflight
  (plan assertions, no fallback, controlled constants) BEFORE measured
  work; a failed preflight aborts the cell.
- Per-file raw rows follow the D16 contract (``cell_id``/``query_id``/
  ``phase="measured"``/``latency_ms``/``metrics``) and are validated with
  ``experiments._lib.stats.validate_per_query_rows``.  ``latency_ms`` is
  0.0 by design so a deterministic rerun is byte-identical (protocol
  section 11); wall-clock timings print to stderr only.
- Checkpoints are atomic (``.tmp`` then ``replace``) and ``--resume``
  skips completed cells.  ``--verify-rerun`` re-executes both cells into
  a scratch directory and byte-compares the cell JSON with the recorded
  run.

TDR-014 note: retrieval/vector-store manifest sections are explicit nulls
with ``null_reasons`` — the mandatory-field list for ADR evidence applies
to retrieval experiments; this is a chunker experiment with nulls by
design (see results.md).
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from experiments._lib import manifest as manifest_lib  # noqa: E402
from experiments._lib import preflight, stats  # noqa: E402
from experiments._lib.plan import ExperimentPlan  # noqa: E402

from rag_mcp.core.chunking.code import CodeChunkResult  # noqa: E402
from rag_mcp.core.ingestion.chunker import read_and_chunk_file_async  # noqa: E402
from rag_mcp.core.settings import EffectiveSettings, MetadataBlock  # noqa: E402

EXPERIMENT_ID = "example-experiment-1-sentencesplitter-vs-codesplitter"
PROTOCOL_VERSION = "1.0"
PLAN_PATH = SCRIPT_DIR / "plan.json"
FIXTURE_MANIFEST_PATH = SCRIPT_DIR / "fixtures" / "manifest.json"
OUTPUT_DIR = SCRIPT_DIR / "output"
CELLS_DIR = OUTPUT_DIR / "cells"
MANIFESTS_DIR = OUTPUT_DIR / "manifests"
CHECKPOINT_PATH = OUTPUT_DIR / "checkpoint.json"

# Controlled chunk settings (production EffectiveSettings defaults).
CODE_CHUNK_LINES = 40
CODE_CHUNK_LINES_OVERLAP = 15
CODE_MAX_CHARS = 1500
SENTENCE_CHUNK_SIZE = 512
SENTENCE_CHUNK_OVERLAP = 100


def build_cell_matrix() -> list[dict[str, Any]]:
    """Return the two-cell matrix declared by plan.json (order: S then C)."""
    return [
        {"id": "S", "factors": {"chunker": "sentence"}},
        {"id": "C", "factors": {"chunker": "code"}},
    ]


def build_settings() -> EffectiveSettings:
    """Return the controlled settings shared by both cells."""
    return EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
    )


def verify_code_splitter_signature() -> None:
    """Preflight: locked CodeSplitter signature has the repaired parameters."""
    from llama_index.core.node_parser import CodeSplitter

    params = set(inspect.signature(CodeSplitter.__init__).parameters)
    required = {"language", "chunk_lines", "chunk_lines_overlap", "max_chars"}
    missing = required - params
    if missing:
        raise preflight.PreflightError(
            f"locked CodeSplitter signature lacks repaired parameters: {sorted(missing)}"
        )


def load_fixture_manifest() -> dict[str, Any]:
    """Load the pre-registered fixture labels (protocol section 9)."""
    return json.loads(FIXTURE_MANIFEST_PATH.read_text(encoding="utf-8"))


def line_char_offsets(source: str) -> list[int]:
    """Char offset of each line start plus one past-the-end sentinel."""
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def definition_char_spans(
    definitions: list[dict[str, Any]], offsets: list[int]
) -> list[tuple[str, int, int, bool]]:
    """Convert labelled line spans to (name, start_char, end_char, fits) tuples."""
    spans = []
    for definition in definitions:
        start = offsets[definition["start_line"] - 1]
        end = offsets[definition["end_line"]]
        spans.append((definition["name"], start, end, definition["fits_under_ceiling"]))
    return spans


def locate_chunks(source: str, chunk_texts: list[str]) -> list[tuple[int, int]]:
    """Locate each chunk's char span via a monotonic forward search.

    Chunk start offsets strictly increase under both arms (CodeSplitter
    chunks are non-overlapping; SentenceSplitter chunks overlap but each
    starts after its predecessor).  Repetitive fixtures could produce
    identical chunk texts, so duplicate texts abort loudly instead of
    silently mis-locating a span.
    """
    spans: list[tuple[int, int]] = []
    cursor = 0
    seen: set[str] = set()
    for text in chunk_texts:
        if text in seen:
            raise ValueError(f"duplicate chunk text ({len(text)} chars) breaks span location")
        seen.add(text)
        position = source.find(text, cursor)
        if position < 0:
            position = source.find(text)
        if position < 0:
            raise ValueError("chunk text not found in source (post-normalisation drift)")
        spans.append((position, position + len(text)))
        cursor = position + 1
    return spans


def structural_metrics(
    source: str,
    chunk_texts: list[str],
    definitions: list[dict[str, Any]],
    *,
    is_code_cell: bool,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Compute the protocol section 7 structural measures for one file.

    Returns ``(metrics, cut_events, violation_events)`` where cut events
    carry the raw boundary location evidence (protocol section 15) and
    violation events carry per-violation explanation evidence.
    """
    offsets = line_char_offsets(source)
    spans = definition_char_spans(definitions, offsets)
    chunk_spans = locate_chunks(source, chunk_texts)

    boundaries = [start for start, _ in chunk_spans[1:]] if len(chunk_spans) > 1 else []

    cut_events: list[dict[str, Any]] = []
    cut_boundaries: set[int] = set()
    definitions_cut: set[str] = set()
    for boundary in boundaries:
        boundary_line = source.count("\n", 0, boundary) + 1
        for name, ds, de, _fits in spans:
            if ds < boundary < de:
                cut_events.append(
                    {
                        "boundary_offset": boundary,
                        "boundary_line": boundary_line,
                        "definition": name,
                    }
                )
                cut_boundaries.add(boundary)
                definitions_cut.add(name)

    fit_definitions = [(name, ds, de) for name, ds, de, fits in spans if fits]
    covered = sum(
        1
        for name, ds, de in fit_definitions
        if any(cs <= ds and de <= ce for cs, ce in chunk_spans)
    )

    violation_events: list[dict[str, Any]] = []
    if is_code_cell:
        oversized = [(name, ds, de) for name, ds, de, _fits in spans if de - ds > CODE_MAX_CHARS]
        for index, text in enumerate(chunk_texts):
            if len(text) <= CODE_MAX_CHARS:
                continue
            start, end = chunk_spans[index]
            explanation = "unexplained"
            for name, ds, de in oversized:
                if start < de and ds < end:
                    explanation = (
                        f"oversized definition {name!r} "
                        f"(span {de - ds} chars > ceiling {CODE_MAX_CHARS}; documented upstream "
                        "recursion semantics, protocol section 16)"
                    )
                    break
            violation_events.append(
                {
                    "chunk_index": index,
                    "chunk_chars": len(text),
                    "chunk_start_offset": start,
                    "chunk_end_offset": end,
                    "explanation": explanation,
                }
            )

    metrics = {
        "chunk_count": len(chunk_texts),
        "chunk_char_lengths": [len(text) for text in chunk_texts],
        "chunk_text_sha256": [
            hashlib.sha256(text.encode("utf-8")).hexdigest() for text in chunk_texts
        ],
        "total_boundaries": len(boundaries),
        "cut_boundaries": len(cut_boundaries),
        "definitions_total": len(spans),
        "definitions_cut": len(definitions_cut),
        "definitions_fit_under_ceiling": len(fit_definitions),
        "definitions_covered_whole": covered,
        "max_chars_violations": len(violation_events),
        "max_chars_violations_unexplained": sum(
            1 for event in violation_events if event["explanation"] == "unexplained"
        ),
    }
    return metrics, cut_events, violation_events


def aggregate_chunking_observation(observations: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-file chunker observations into the manifest section."""
    effective = {observation["effective"] for observation in observations}
    requested = {observation["requested"] for observation in observations}
    fallbacks = [
        observation["fallback_reason"]
        for observation in observations
        if observation["fallback_reason"]
    ]
    if len(requested) != 1 or len(effective) != 1:
        raise preflight.PreflightError(
            f"inhomogeneous chunker observations: requested={sorted(requested)} "
            f"effective={sorted(effective)}"
        )
    return {
        "requested": requested.pop(),
        "effective": effective.pop(),
        "fallback_reason": fallbacks[0] if fallbacks else None,
    }


def build_cell_manifest(
    cell: dict[str, Any],
    chunking_section: dict[str, Any],
    fixture_count: int,
    languages: list[str],
) -> dict[str, Any]:
    """Build the D13 runtime manifest for one cell (chunker experiment)."""
    return manifest_lib.build_runtime_manifest(
        experiment_id=EXPERIMENT_ID,
        protocol_version=PROTOCOL_VERSION,
        chunking=chunking_section,
        corpus_path=FIXTURE_MANIFEST_PATH,
        extra={
            "cell_id": cell["id"],
            "chunker_factor": cell["factors"]["chunker"],
            "chunking_settings": {
                "code_chunk_lines": CODE_CHUNK_LINES,
                "code_chunk_lines_overlap": CODE_CHUNK_LINES_OVERLAP,
                "code_max_chars": CODE_MAX_CHARS,
                "chunk_size": SENTENCE_CHUNK_SIZE,
                "chunk_overlap": SENTENCE_CHUNK_OVERLAP,
            },
            "metadata_extraction_mode": "disabled",
            "fixture_count": fixture_count,
            "languages": languages,
        },
    )


def atomic_write_json(path: Path, payload: Any) -> None:
    """Serialise to a .tmp file then atomically rename (TDR-014 rule 7)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


async def chunk_fixture(
    fixture: dict[str, Any], cell: dict[str, Any], settings: EffectiveSettings
) -> tuple[list[str], dict[str, Any], float]:
    """Chunk one fixture through the production dispatch path.

    Returns ``(chunk_texts, chunker_observation, wall_seconds)``.  The
    observation for the code cell comes from the production
    ``CodeChunkResult`` diagnostics via ``manifest_lib.observe_chunking``.
    """
    file_path = SCRIPT_DIR / fixture["path"]
    started = time.perf_counter()
    if cell["factors"]["chunker"] == "code":
        result = await read_and_chunk_file_async(
            file_path,
            content_type=f"code/{fixture['language']}",
            settings=settings,
        )
        if not isinstance(result, CodeChunkResult):
            raise preflight.PreflightError(
                f"code cell did not take the CodeSplitter path for {fixture['id']}"
            )
        observation = manifest_lib.observe_chunking(result)
        texts = [node.get_content() for node in result]
    else:
        result = await read_and_chunk_file_async(file_path, settings=settings)
        if isinstance(result, CodeChunkResult):
            raise preflight.PreflightError(
                f"sentence cell unexpectedly took the code path for {fixture['id']}"
            )
        observation = {"requested": "sentence", "effective": "sentence", "fallback_reason": None}
        texts = [node.get_content() for node in result]
    return texts, observation, time.perf_counter() - started


async def run_cell(
    cell: dict[str, Any],
    fixtures: list[dict[str, Any]],
    settings: EffectiveSettings,
    plan: ExperimentPlan,
    *,
    cells_dir: Path,
    manifests_dir: Path,
) -> dict[str, Any]:
    """Execute one cell end to end: preflight, measure, checkpoint."""
    cell_id = cell["id"]
    is_code_cell = cell["factors"]["chunker"] == "code"
    rows: list[dict[str, Any]] = []
    cut_events: list[dict[str, Any]] = []
    violation_events: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    fallback_count = 0

    for fixture in fixtures:
        source_path = SCRIPT_DIR / fixture["path"]
        source = source_path.read_text(encoding="utf-8")
        source_sha256 = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if source_sha256 != fixture["sha256"]:
            raise preflight.PreflightError(
                f"{fixture['id']}: on-disk bytes differ from the pre-registered labels "
                f"({source_sha256} != {fixture['sha256']}); labels are stale or sources drifted"
            )
        texts, observation, wall = await chunk_fixture(fixture, cell, settings)
        observations.append(observation)
        if observation["fallback_reason"] is not None:
            fallback_count += 1
        if is_code_cell and (
            observation["requested"] != "code" or observation["effective"] != "code"
        ):
            raise preflight.PreflightError(
                f"{fixture['id']}: requested={observation['requested']!r} "
                f"effective={observation['effective']!r} — protocol section 13 abort"
            )
        metrics, cuts, violations = structural_metrics(
            source, texts, fixture["definitions"], is_code_cell=is_code_cell
        )
        metrics.update(
            {
                "effective_strategy": observation["effective"],
                "fallback": observation["fallback_reason"] is not None,
                "source_sha256": source_sha256,
                "language": fixture["language"],
                "complexity": fixture["complexity"],
                "source_chars": fixture["source_chars"],
            }
        )
        rows.append(
            {
                "cell_id": cell_id,
                "query_id": fixture["id"],
                "phase": "measured",
                "latency_ms": 0.0,
                "metrics": metrics,
            }
        )
        for event in cuts:
            cut_events.append({"file": fixture["id"], **event})
        violation_events.extend({"file": fixture["id"], **event} for event in violations)
        print(
            f"[{cell_id}] {fixture['id']}: {metrics['chunk_count']} chunks, "
            f"{metrics['cut_boundaries']}/{metrics['total_boundaries']} cut boundaries "
            f"({wall * 1000:.1f} ms)",
            file=sys.stderr,
        )

    stats.validate_per_query_rows(rows)

    if fallback_count:
        raise preflight.PreflightError(
            f"cell {cell_id}: {fallback_count} fixture(s) fell back (protocol section 13)"
        )
    chunking_section = aggregate_chunking_observation(observations)
    manifest = build_cell_manifest(
        cell,
        chunking_section,
        fixture_count=len(fixtures),
        languages=sorted({fixture["language"] for fixture in fixtures}),
    )
    cell_assertions = list(plan.required_manifest_assertions) + [
        {
            "manifest_field": "chunker.requested",
            "operator": "eq",
            "expected": cell["factors"]["chunker"],
        },
        {
            "manifest_field": "chunker.effective",
            "operator": "eq",
            "expected": cell["factors"]["chunker"],
        },
    ]
    preflight.assert_manifest(manifest, cell_assertions)
    preflight.assert_no_fallback(manifest)

    manifests_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(manifests_dir / f"{cell_id}.manifest.json", manifest)

    payload = {
        "cell_id": cell_id,
        "factors": cell["factors"],
        "manifest_path": f"output/manifests/{cell_id}.manifest.json",
        "rows": rows,
        "cut_events": cut_events,
        "violation_events": violation_events,
    }
    atomic_write_json(cells_dir / f"{cell_id}.json", payload)
    return stats.cell_record(status="complete", cell_id=cell_id, row_count=len(rows))


def load_checkpoint() -> set[str]:
    """Return completed cell ids from the checkpoint file."""
    if not CHECKPOINT_PATH.exists():
        return set()
    return set(json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))["completed"])


def save_checkpoint(completed: list[str]) -> None:
    atomic_write_json(CHECKPOINT_PATH, {"completed": completed})


async def run_all(cells_dir: Path, manifests_dir: Path, *, resume: bool) -> list[dict[str, Any]]:
    """Run both cells with plan agreement and controlled-constant preflight."""
    plan = ExperimentPlan.from_json(PLAN_PATH)
    plan.assert_runner_cells(build_cell_matrix())
    verify_code_splitter_signature()
    fixtures = load_fixture_manifest()["fixtures"]

    completed = load_checkpoint() if resume else set()
    settings = build_settings()
    records: list[dict[str, Any]] = []
    manifests_by_cell: dict[str, dict[str, Any]] = {}
    for cell in build_cell_matrix():
        if cell["id"] in completed:
            print(f"skipping completed cell {cell['id']} (--resume)", file=sys.stderr)
            manifest_path = manifests_dir / f"{cell['id']}.manifest.json"
            manifests_by_cell[cell["id"]] = json.loads(manifest_path.read_text(encoding="utf-8"))
            records.append(stats.cell_record(status="complete", cell_id=cell["id"], resumed=True))
            continue
        records.append(
            await run_cell(
                cell, fixtures, settings, plan, cells_dir=cells_dir, manifests_dir=manifests_dir
            )
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
            "chunking_settings.code_chunk_lines",
            "chunking_settings.code_chunk_lines_overlap",
            "chunking_settings.code_max_chars",
            "chunking_settings.chunk_size",
            "chunking_settings.chunk_overlap",
        ],
    )
    return records


async def verify_rerun() -> int:
    """Re-run both cells into a scratch dir and byte-compare cell JSON."""
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
        help="re-execute both cells and byte-compare with the recorded run",
    )
    args = parser.parse_args()

    if args.verify_rerun:
        return asyncio.run(verify_rerun())
    records = asyncio.run(run_all(CELLS_DIR, MANIFESTS_DIR, resume=args.resume))
    print(json.dumps({"cells": records}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
