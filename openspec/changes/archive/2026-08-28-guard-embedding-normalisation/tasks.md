# Tasks: guard-embedding-normalisation

## 1. Spec and record

- [x] 1.1 Ratify design decisions D1 (guard not normalise), D2 (fail-closed ingest / warn-and-continue query), and D3 (tolerance defaults) with the user; record any amendments in design.md.
- [x] 1.2 Confirm the 2026-08-23 investigation note has merged with the harden-pipeline branch and link it from this change's ADR; if the note is still uncommitted, surface that to the user first.
  - Surfaced: the note is NOT in the repository (its parent change archived
    without it). ADR-053 restates the evidence inline and re-verifies the
    llama.cpp path empirically (task 3.1).

## 2. Implementation (test-first throughout)

- [x] 2.1 Write failing unit tests for the norm helper: within-tolerance pass, 0.7 fail, 1.4 fail, tolerance boundary inclusive, empty vector handling.
- [x] 2.2 Implement the shared norm-guard module in `core/` (pure functions, injected settings, no singleton imports — repo invariant #9).
- [x] 2.3 Write failing tests for the ingest boundary: abort before `write_nodes` on violation, previous version stays searchable (failure-safe ordering), error names model/norm/tolerance/setting, norm band recorded in the ingest report.
- [x] 2.4 Wire the guard into `core/ingestion/replacement.py` (embed step, before write).
- [x] 2.5 Write failing tests for the query boundary: warn once per process per model, results still returned, `norm_guard` diagnostic only when diagnostics enabled, silent when within tolerance.
- [x] 2.6 Wire the guard into `core/retrieval/dense.py` (after the query-embedding cache so cached hits cost nothing extra beyond the cached norm).
- [x] 2.7 Add the nested settings (enable flag default true, tolerance default 0.001) with startup logging when disabled; document both in `.env.example` and the configuration guide, with a documentation-drift grep for related guides.

## 3. Validation and record

- [x] 3.1 Probe the llama.cpp path: embed one query through a local llama-server with the production GGUF, record the observed norm in the ADR (closes audit §11 for the second provider path).
  - Recorded in ADR-053 Evidence: Qwen3-Embedding-0.6B-Q8_0.gguf,
    1024-dim, norms 0.99999995 / 0.99999997 (deviation ≤ 4.8e-08).
- [x] 3.2 Run `uv run pytest -m "not slow" --cov=rag_mcp` at coverage floors for touched modules (core tier ≥95%).
  - 1834 passed, 0 failed; new/changed lines fully covered (missed lines
    in replacement.py are pre-existing shutdown/error branches).
- [x] 3.3 Run `ruff check`, `ruff format --check`, and `uv run lint-imports` (the new module must not create ingestion/retrieval cross-imports).
  - ruff clean; 8/8 import-linter contracts kept (no ingestion/retrieval
    cross-import; EmbeddingSettings lives in core/settings.py after the
    providers-quarantine discovery, see ADR-053 Decision 4).
- [x] 3.4 Write the ADR (guard vs normalise vs metric switch, with the investigation evidence and the D17 independence argument) and run `openspec validate guard-embedding-normalisation --strict`.
  - ADR-053 written and accepted; validation valid at PR time.
- [x] 3.5 Archive the change (`/opsx-archive`) after PR #70 merges.

## 4. Out-of-scope register

- Vector normalisation, LanceDB metric switch, re-embedding, and reranker policy: all explicitly out of scope; the ADR records them as rejected alternatives with revisit conditions.
