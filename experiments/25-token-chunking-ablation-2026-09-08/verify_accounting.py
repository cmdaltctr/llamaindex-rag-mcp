"""Experiment 25 RETROSPECTIVE accounting: verify built indexes, count real payloads.

Retrospective verification of COMPLETED builds — it can never authorise a
future paid build (that path is disabled in build_index.py until a corrected
pre-spend estimator exists; see TDR-022).

Definitive method: each stored row carries the serialised pre-store node in
metadata["_node_content"] (adapter-injected). Deserialising it recovers the
real metadata, excluded-key sets, and templates the pipeline embedded — no
reconstruction. Reconstruction from row text+metadata is NOT equivalent:
null-valued retained keys (e.g. "content_type": None on 19,361 baseline
nodes, "header_path": None on all candidate nodes) render into a rebuilt
payload and inflate totals by ~0.7-1.2%.

Per-file cross-check: grouped chunk counts must match the build's recorded
file_details exactly. Strict rejection: missing index, missing build record,
missing _node_content, per-file mismatch, tokenizer fallback, or incomplete
coverage.

payload_tokens/max_payload_tokens count MetadataMode.EMBED text before the
adapter. request_tokens/max_request_tokens count that text after the installed
OpenAI batch helpers replace each newline with a space. Both use the pinned
local tokenizer without special tokens; neither verifies provider billing or retries.

Usage:
    uv run python verify_accounting.py --side baseline
    uv run python verify_accounting.py --side candidate
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
TOKENIZER_MODEL = "Qwen/Qwen3-Embedding-4B"
TOKENIZER_REVISION = "5cf2132abc99cad020ac570b19d031efec650f2b"
GATE_CAP = 1.15  # frozen plan.json cost gate, unrounded

SIDES = {
    "baseline": {
        "uri": Path.home() / "Development/DATA/omrg/experiments/exp22-lancedb",
        "table": "exp22",
        "build": PROJECT_ROOT
        / "experiments/22-raw-query-qwen4b-baseline-2026-09-07/output/build_done.json",
    },
    "candidate": {
        # Preserved outside the worktree (2026-09-08); a symlink at
        # output/lancedb keeps the build runner's paths working.
        "uri": Path.home() / "Development/DATA/omrg/experiments/exp25-lancedb",
        "table": "exp25_model_token",
        "build": EXP_DIR / "output/build_done.json",
    },
}

sys.path.insert(0, str(PROJECT_ROOT / "src"))

parser = argparse.ArgumentParser()
parser.add_argument("--side", choices=["baseline", "candidate"], required=True)
args = parser.parse_args()


def main() -> None:
    """Verify one side's index and count its true embedding payloads."""
    import lancedb
    from llama_index.core.schema import MetadataMode, TextNode

    from omrg.integrations.tokenizer import load_tokenizer

    side = SIDES[args.side]
    if not side["uri"].exists():
        sys.exit(f"[verify] index missing: {side['uri']}")
    build = json.loads(side["build"].read_text(encoding="utf-8"))
    tokenizer = load_tokenizer(TOKENIZER_MODEL, TOKENIZER_REVISION)  # raises on fallback

    table = lancedb.connect(str(side["uri"])).open_table(side["table"])
    rows = table.to_arrow().to_pylist()

    payload_tokens = 0
    max_payload_tokens = 0
    request_tokens = 0
    max_request_tokens = 0
    per_file_chunks: Counter[str] = Counter()
    for row in rows:
        metadata = row.get("metadata") or {}
        node_content = metadata.get("_node_content")
        if node_content is None:
            sys.exit("[verify] row without _node_content — cannot recover real payload")
        node = TextNode.from_json(node_content)
        payload = node.get_content(metadata_mode=MetadataMode.EMBED)
        count = len(tokenizer.encode(payload, add_special_tokens=False).ids)
        payload_tokens += count
        max_payload_tokens = max(max_payload_tokens, count)
        # OpenAILikeEmbedding inherits this transformation in sync/async batch helpers.
        request_count = len(
            tokenizer.encode(payload.replace("\n", " "), add_special_tokens=False).ids
        )
        request_tokens += request_count
        max_request_tokens = max(max_request_tokens, request_count)
        per_file_chunks[str(node.metadata.get("file_path", "unknown"))] += 1

    # Per-file cross-check against the build's own record.
    recorded: Counter[str] = Counter()
    for pack in build["packs"].values():
        for detail in pack.get("file_details", []):
            if detail.get("status") == "indexed":
                recorded[detail["file"]] += detail.get("chunks", 0)
    mismatches = []
    grouped = Counter()
    for path, chunks in per_file_chunks.items():
        grouped[Path(path).name] += chunks
    for name, expected in recorded.items():
        if grouped.get(name, 0) != expected:
            mismatches.append({"file": name, "recorded": expected, "counted": grouped.get(name, 0)})

    files_covered = len(per_file_chunks)
    stored_total = len(rows)
    result = {
        "side": args.side,
        "method": "deserialised _node_content (real pre-store nodes)",
        "tokenizer": {"model": TOKENIZER_MODEL, "revision": TOKENIZER_REVISION},
        "files": files_covered,
        "chunks": stored_total,
        "token_definitions": {
            "payload_tokens": "sum of MetadataMode.EMBED text tokens before the adapter",
            "max_payload_tokens": "largest per-node EMBED text token count",
            "request_tokens": "sum after EMBED text.replace('\\n', ' ') in the adapter",
            "max_request_tokens": "largest per-node normalised request text token count",
            "scope": "local tokenizer, no special tokens; excludes provider billing and retries",
        },
        "payload_tokens": payload_tokens,
        "max_payload_tokens": max_payload_tokens,
        "request_tokens": request_tokens,
        "max_request_tokens": max_request_tokens,
        "per_file_mismatches": mismatches[:10],
        "mismatch_count": len(mismatches),
        "recorded_files": len(recorded),
    }
    out = EXP_DIR / f"output/verify_accounting_{args.side}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result, indent=2), encoding="utf-8")
    tmp.replace(out)

    print(json.dumps({k: v for k, v in result.items() if k != "per_file_mismatches"}, indent=2))
    if mismatches:
        sys.exit(
            f"[verify] {args.side}: {len(mismatches)} per-file mismatch(es)"
            " — investigate before trusting"
        )
    if files_covered != len(recorded):
        sys.exit(
            f"[verify] {args.side}: {files_covered} files in index vs "
            f"{len(recorded)} recorded — incomplete accounting"
        )
    print(f"[verify] {args.side}: per-file counts reconcile exactly", flush=True)


if __name__ == "__main__":
    main()
