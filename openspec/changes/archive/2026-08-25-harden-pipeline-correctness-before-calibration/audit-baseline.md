# Audit baseline: harden-pipeline-correctness-before-calibration

**Recorded:** 2026-08-18  
**Parent branch:** `v3`  
**Parent / branch-start commit:** `ee0d256b91a00c4b7dd3a441a5d576fff612a4cb`  
**Hardening branch:** `harden-pipeline-correctness-before-calibration`

## Purpose

This file pins the provenance boundary for the pre-calibration hardening work.
Findings below refer to the production code present at the branch-start commit,
not to later fixes on this branch.

## Dependency/runtime provenance

The repository declares these relevant floors at the branch-start commit:

- Python `>=3.11` (normal CI uses Python 3.12);
- `llama-index>=0.14.5`;
- `chromadb>=1.0.0`;
- `llama-index-vector-stores-lancedb>=0.5.0`;
- `lancedb>=0.37`;
- `onnxruntime>=1.20.0`;
- `tokenizers>=0.20`;
- optional `sentence-transformers>=5.0` / `transformers>=5.0.0` for the Torch reranker.

### Recorded at Gate 0 (local worktree, 2026-08-18)

Python and locked package versions of the audit environment, captured from the
real worktree with `uv run python` (resolution via `uv.lock`):

| Package | Locked version |
| --- | --- |
| Python (CPython) | 3.12.10 |
| `llama-index` / `llama-index-core` | 0.14.23 |
| `chromadb` | 1.5.9 |
| `lancedb` | 0.37.1 |
| `onnxruntime` | 1.28.0 |
| `tokenizers` | 0.22.2 |
| `torch` | not installed (optional extra absent) |
| `sentence-transformers` | not installed (optional extra absent) |

The exact versions can be re-verified with:

```bash
python --version
uv tree --depth 1
uv run python - <<'PY'
import importlib.metadata as m
for name in [
    "llama-index-core",
    "chromadb",
    "lancedb",
    "onnxruntime",
    "tokenizers",
    "sentence-transformers",
    "torch",
]:
    try:
        print(name, m.version(name))
    except m.PackageNotFoundError:
        print(name, "not installed")
PY
```

For the CodeSplitter API decision, the audit independently checked the tagged
LlamaIndex v0.14.5 source and current 0.14.x documentation: CodeSplitter uses
`chunk_lines`, `chunk_lines_overlap`, and `max_chars`, whereas
SentenceSplitter uses `chunk_size` and `chunk_overlap` tokenizer units.

## Archived OpenSpec interpretation

For this hardening change, **archive status is not implementation evidence**.
The current production source and executable tests are authoritative.

Confirmed example: the archived `add-ingestion-change-detection` proposal
explains a desirable design, but its archived task list remained unchecked and
the branch-start ingestion pipeline still used delete/re-embed behaviour.
Treat similar archived changes as one of:

1. **confirmed implementation history** — current source/tests implement the
   contract;
2. **design intent only** — useful rationale, but current source does not
   implement it; or
3. **superseded/historical experiment** — preserve for provenance only.

Do not mark a hardening task complete solely because a related change lives
under `openspec/changes/archive/`.

## Baseline audit defects represented by regression tests

The first remote audit-test commit added lightweight regressions for:

- CodeSplitter constructor/unit mismatch;
- metadata `max_chunks × token-size` character slicing;
- Experiment 10b protocol/runner treatment mismatch;
- Experiment 13 threshold policy being bypassed by explicit `rerank=True`;
- Experiment 14 not parsing real PDFs in its alleged parser A/B path.

The remaining Stage 0 retrieval/store regressions are still intentionally
unchecked in `tasks.md` and must be added before Gate 0 is considered complete.

## Remote-work caveat

Remote GitHub edits cannot run the repository's local test/lint/OpenSpec tool
chain. No PASS/FAIL claim in this baseline should be inferred from a committed
file alone. `tasks.md` deliberately leaves execution gates unchecked until the
worktree is validated locally.
