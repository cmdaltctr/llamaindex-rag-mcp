# Tasks: guard-embedding-normalisation

## 1. Spec and record

- [ ] 1.1 Ratify design decisions D1 (guard not normalise), D2 (fail-closed ingest / warn-and-continue query), and D3 (tolerance defaults) with the user; record any amendments in design.md.
- [ ] 1.2 Confirm the 2026-08-23 investigation note has merged with the harden-pipeline branch and link it from this change's ADR; if the note is still uncommitted, surface that to the user first.

## 2. Implementation (test-first throughout)

- [ ] 2.1 Write failing unit tests for the norm helper: within-tolerance pass, 0.7 fail, 1.4 fail, tolerance boundary inclusive, empty vector handling.
- [ ] 2.2 Implement the shared norm-guard module in `core/` (pure functions, injected settings, no singleton imports — repo invariant #9).
- [ ] 2.3 Write failing tests for the ingest boundary: abort before `write_nodes` on violation, previous version stays searchable (failure-safe ordering), error names model/norm/tolerance/setting, norm band recorded in the ingest report.
- [ ] 2.4 Wire the guard into `core/ingestion/replacement.py` (embed step, before write).
- [ ] 2.5 Write failing tests for the query boundary: warn once per process per model, results still returned, `norm_guard` diagnostic only when diagnostics enabled, silent when within tolerance.
- [ ] 2.6 Wire the guard into `core/retrieval/dense.py` (after the query-embedding cache so cached hits cost nothing extra beyond the cached norm).
- [ ] 2.7 Add the nested settings (enable flag default true, tolerance default 0.001) with startup logging when disabled; document both in `.env.example` and the configuration guide, with a documentation-drift grep for related guides.

## 3. Validation and record

- [ ] 3.1 Probe the llama.cpp path: embed one query through a local llama-server with the production GGUF, record the observed norm in the ADR (closes audit §11 for the second provider path).
- [ ] 3.2 Run `uv run pytest -m "not slow" --cov=rag_mcp` at coverage floors for touched modules (core tier ≥95%).
- [ ] 3.3 Run `ruff check`, `ruff format --check`, and `uv run lint-imports` (the new module must not create ingestion/retrieval cross-imports).
- [ ] 3.4 Write the ADR (guard vs normalise vs metric switch, with the investigation evidence and the D17 independence argument), run `openspec validate guard-embedding-normalisation --strict`, then archive the change.

## 4. Out-of-scope register

- Vector normalisation, LanceDB metric switch, re-embedding, and reranker policy: all explicitly out of scope; the ADR records them as rejected alternatives with revisit conditions.
