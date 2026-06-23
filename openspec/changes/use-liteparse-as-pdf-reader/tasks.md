# Implementation Tasks: use-liteparse-as-pdf-reader

> **Workflow summary.** Branch → Experiment 11 validates the hypothesis → if PASS, implement the factory + LiteParse adapter → ADR-020 captures the decision → validate → PR → post-merge archive. If Experiment 11 FAILs, stop at task 5.2 and write ADR-020 recording the negative result.

## 1. Branch setup

- [x] 1.1 Create branch `feat/use-liteparse-as-pdf-reader` from `master` (`git switch -c feat/use-liteparse-as-pdf-reader`)
- [x] 1.2 Scaffold OpenSpec change via `openspec new change "use-liteparse-as-pdf-reader"`
- [x] 1.3 Draft proposal.md, design.md, specs/pdf-reader/spec.md, tasks.md
- [x] 1.4 Run `openspec validate use-liteparse-as-pdf-reader --strict` and resolve any reported issues
- [x] 1.5 Commit the OpenSpec artifacts: `git add openspec/changes/use-liteparse-as-pdf-reader && git commit -m "docs(openspec): propose use-liteparse-as-pdf-reader"`

## 2. Experiment 11 scaffold

> Creates the validation gate per `/s-experiment` skill phases 1–3. No code under `src/` changes yet.

- [x] 2.1 Create experiment directory: `mkdir -p experiments/11-liteparse-pdf-quality-2026-06-20/{corpus,output}`
- [x] 2.2 Copy full protocol template: `cp .opencode/skills/s-experiment/references/protocol-template.md experiments/11-liteparse-pdf-quality-2026-06-20/protocol.md`
- [x] 2.3 Fill `protocol.md` sections: hypothesis, single variable under test (PDF parser), pass gates (see design.md Decision 6), cells matrix (`{pypdf, liteparse} × {rerank-on, rerank-off}`), corpus requirement (≥20 academic PDFs with two-column layouts)
- [x] 2.4 Write `experiments/11-liteparse-pdf-quality-2026-06-20/ground_truth.json` stub with at least 15 queries spanning single-column, two-column, and table-heavy cases. Each entry: `{"query": str, "expected_files": [str], "expected_pages": [int], "category": str}`. Mark with `// TODO: expand to 25+ queries after corpus assembly`
- [x] 2.5 Write `experiments/11-liteparse-pdf-quality-2026-06-20/build_indexes.py` per the eval-runner-pattern: builds two isolated ChromaDB dirs (`output/chroma_pypdf_baseline`, `output/chroma_liteparse`) using `CHROMA_PERSIST_DIR` env override; uses the `_read_and_chunk_file_async` helper to ensure both indexes use identical chunking
- [x] 2.6 Write `experiments/11-liteparse-pdf-quality-2026-06-20/run_eval.py` per the canonical eval-runner-pattern.md: iterates cells, supports `--modes pypdf,liteparse --rerank-cross --k-values 5,10,20,50 --resume`, writes atomic checkpoint per cell, calls `_cached_query_embedding.cache_clear()` between cells
- [x] 2.7 Write `experiments/11-liteparse-pdf-quality-2026-06-20/summarise_eval.py` per summarise-pattern.md: loads `eval_results.json`, computes nDCG@10 per cell, evaluates all four pass gates, writes `eval_results.summary.json` and `results.md`
- [x] 2.8 Add `.gitkeep` to `experiments/11-liteparse-pdf-quality-2026-06-20/corpus/` so the empty directory is tracked
- [x] 2.9 Add `experiments/11-liteparse-pdf-quality-2026-06-20/output/` to `.gitignore` (or rely on the existing global output ignore) so generated artifacts are not committed
- [x] 2.10 Update `experiments/EXP_README.md` index table with the new entry; status `PLANNED`
- [x] 2.11 Commit the scaffold: `git add experiments/ && git commit -m "exp(11): scaffold liteparse pdf quality experiment"`

## 3. User supplies corpus

> Manual step. Operator (user) populates `experiments/11-liteparse-pdf-quality-2026-06-20/corpus/` with ≥20 academic PDFs.

- [x] 3.1 Operator adds ≥20 academic PDFs to `experiments/11-liteparse-pdf-quality-2026-06-20/corpus/`. Suggested mix: 12 two-column papers (e.g. NeurIPS/ICML/ACL style), 5 single-column (e.g. arXiv preprints), 3 table-heavy (e.g. survey papers, financial reports)
- [x] 3.2 Operator expands `ground_truth.json` from stub to ≥25 queries with known-good answers drawn from the supplied corpus
- [x] 3.3 Commit the corpus (if licence permits) or add `corpus/*.pdf` to `.gitignore` and document the corpus manifest in `corpus/MANIFEST.md` listing each PDF's source URL and licence

## 4. Run Experiment 11

> Per `/s-experiment` skill phases 4–5. Operator runs this manually; long-running.

- [x] 4.1 Install the LiteParse backend in the experiment venv: `uv sync --extra pdf-liteparse`. The experiment exercises only `pypdf` and `liteparse` cells; pypdfium2 is not a cell in this experiment.
- [x] 4.2 Build indexes for both cells: `CHROMA_PERSIST_DIR=./experiments/11-liteparse-pdf-quality-2026-06-20/output/chroma_pypdf PDF_READER=pypdf uv run python experiments/11-liteparse-pdf-quality-2026-06-20/build_indexes.py` and the equivalent with `PDF_READER=liteparse` for the candidate
- [x] 4.3 Run evaluation with checkpoint/resume: `PYTHONUNBUFFERED=1 uv run python -u experiments/11-liteparse-pdf-quality-2026-06-20/run_eval.py --modes pypdf,liteparse --rerank-cross --k-values 5,10,20,50 --resume 2>&1 | tee experiments/11-liteparse-pdf-quality-2026-06-20/output/run_eval.log`
- [x] 4.4 If interrupted, re-run with `--resume` to pick up from the last checkpoint
- [x] 4.5 Commit raw results: `git add experiments/11-liteparse-pdf-quality-2026-06-20/output/eval_results.json experiments/11-liteparse-pdf-quality-2026-06-20/output/run_eval.log && git commit -m "exp(11): run evaluation raw results"`

## 5. Summarise and decide

> Per `/s-experiment` skill phases 6–7. Produces the pass/fail verdict.

- [x] 5.1 Run summariser: `uv run python experiments/11-liteparse-pdf-quality-2026-06-20/summarise_eval.py`
- [x] 5.2 Verify all four pass gates from design.md Decision 6 are reported in `results.md`:
  - Quality win: nDCG@10 candidate-B ≥ baseline-A + 5% relative
  - Speed win: ingest wall-clock candidate-B ≤ baseline-A × 0.80
  - Regression guard A: candidate-B-r ≥ candidate-B (reranker still helps)
  - Regression guard B: zero queries move from "found" to "not found"
- [ ] 5.3 Update `experiments/EXP_README.md` with status `PASS` or `FAIL` and a one-line summary
- [x] 5.4 **DECISION GATE.** If Experiment 11 status is PASS → continue to task 6. If FAIL → jump to task 10.2 (write ADR-020 recording negative result) and stop. Do not implement the factory change on a failed experiment.
- [x] 5.5 Commit summary: `git add experiments/11-liteparse-pdf-quality-2026-06-20/{results.md,output/eval_results.summary.json} experiments/EXP_README.md && git commit -m "exp(11): summarise results, status=<PASS|FAIL>"`

## 6. Implementation: config plumbing

> Only execute if Experiment 11 PASSED.

- [x] 6.1 Add `PDF_READER` env var to `src/rag_mcp/config.py` with default `"pypdf"` (NOT `"auto"` — promotion to `auto` is a follow-on change after this one merges)
- [x] 6.2 Add accepted-values validation: `{"auto", "liteparse", "pypdfium2", "pypdf"}`; unknown values log warning and fall back to `auto` resolution per spec. PyMuPDF is NOT an accepted value (AGPL-3 exclusion).
- [x] 6.3 Add `_resolve_pdf_reader()` private function mirroring `_resolve_sparse_backend()` at `config.py:138-160` — probes imports in order `liteparse → pypdfium2 → pypdf`, falls back to `pypdf` on any failure
- [x] 6.4 Expose `RESOLVED_PDF_READER` module-level constant
- [x] 6.5 Add `LITEPARSE_NUM_WORKERS` and `LITEPARSE_OCR_ENABLED` env vars (default `None` and `False`) for future LiteParse constructor configuration
- [x] 6.6 Document the new env vars in `.env.example` with inline comments referencing the experiment and ADR

## 7. Implementation: readers module

- [x] 7.1 Create `src/rag_mcp/readers/__init__.py` exposing `get_pdf_reader`
- [x] 7.2 Create `src/rag_mcp/readers/base.py` defining `BaseReader` protocol: a `__call__(self, file_path: Path) -> list[Document]` shape compatible with LlamaIndex's `file_extractor` mapping
- [x] 7.3 Create `src/rag_mcp/readers/pypdf_reader.py` wrapping the current `SimpleDirectoryReader` path as a callable adapter (no behaviour change — pure refactor of the existing logic)
- [x] 7.4 Create `src/rag_mcp/readers/pypdfium_reader.py` adapter using `pypdfium2` (fallback tier; lazy-imported)
- [x] 7.5 Create `src/rag_mcp/readers/liteparse_reader.py` adapter: lazy-imports `liteparse`, instantiates `LiteParse()` with constructor defaults, calls `parser.parse(str(file_path))`, converts `result.pages` → LlamaIndex `Document` objects with bbox metadata per spec requirement, wraps every exception in a structured error dictionary per the MCP error contract
- [x] 7.6 Create `src/rag_mcp/readers/factory.py` with `get_pdf_reader()` returning the adapter based on `RESOLVED_PDF_READER`. Use a dict mapping `{"pypdf": pypdf_reader, "pypdfium2": pypdfium_reader, "liteparse": liteparse_reader}`. Unknown values raise `ValueError` (this should be unreachable because config validates). No pymupdf entry — AGPL-3 excluded.
- [x] 7.7 Add `from __future__ import annotations` to every new module
- [x] 7.8 Add Google-style docstrings to every public function/class

## 8. Implementation: ingestion integration

- [x] 8.1 In `src/rag_mcp/ingestion.py:257`, modify the `SimpleDirectoryReader` construction to pass `file_extractor={".pdf": get_pdf_reader()}`. No other change to `_read_sync()`.
- [x] 8.2 Verify `_read_and_chunk_file_async` still returns `list[Node]` with metadata attached; the only difference is PDF-sourced Documents now carry bbox metadata
- [x] 8.3 Add a `logger.info` line at first reader resolution showing `RESOLVED_PDF_READER` so users see which backend is active
- [x] 8.4 Verify no circular imports between `readers/` and `ingestion.py` (readers should import only from `config.py`, never from `ingestion.py` — matches the existing ingestion/retrieval isolation rule)

## 9. Implementation: dependencies and packaging

- [x] 9.1 Add `[project.optional-dependencies]` section to `pyproject.toml` (or extend existing) with two extras: `pdf-liteparse = ["liteparse>=2.0.0"]` and `pdf-pypdfium2 = ["pypdfium2>=4.0.0"]`
- [x] 9.2 Run `uv lock` to update `uv.lock`
- [ ] 9.3 Verify `uv sync` (no extras) still works and neither `liteparse` nor `pypdfium2` is importable
- [x] 9.4 Verify `uv sync --extra pdf-liteparse` installs LiteParse and the native PDFium binary builds successfully on macOS arm64
- [ ] 9.5 Document the `[pdf-liteparse]` flag in the README "Quick install" section, alongside the existing optional hybrid retrieval flag

## 10. ADR-020

> Written regardless of Experiment 11 outcome.

- [x] 10.1 If Experiment 11 PASSED: draft `docs/adr/020-use-liteparse-as-pdf-reader.md` with Status=Accepted, Context (pypdf problem, LiteParse selection rationale), Decision (adopt LiteParse via factory), Alternatives (pymupdf4llm/AGPL, pypdfium2/no-bbox, spdf/immature, docling/PyTorch-blocked), Consequences (bbox metadata available, native build dep, AGPL avoidance), References (Experiment 11 results, this OpenSpec change)
- [ ] 10.2 If Experiment 11 FAILED: draft `docs/adr/020-use-liteparse-as-pdf-reader.md` with Status=Declined, Context (same), Decision (reject LiteParse adoption; retain factory architecture for future use), Negative Result (what specifically failed — quality, speed, or both), Follow-on (pypdfium2 as smaller upgrade, or wait for spdf maturity)
- [x] 10.3 Update `docs/adr/ADR_README.md` index with the new entry, following the existing format
- [ ] 10.4 Cross-reference the ADR from `experiments/EXP_README.md` Experiment 11 row

## 11. Tests

- [x] 11.1 `tests/unit/test_pdf_reader_factory.py` — factory resolution: each `PDF_READER` value (`auto`, `liteparse`, `pypdfium2`, `pypdf`), fallback chain, `auto` order, unknown value warns and falls back, pymupdf value rejected with clear error
- [x] 11.2 `tests/unit/test_pypdf_reader.py` — pypdf adapter preserves semantically equivalent Document output vs pre-change behaviour (regression guard; not byte-identical because PDF parsing is non-deterministic across library versions, per spec.md)
- [x] 11.3 `tests/unit/test_liteparse_reader.py` — LiteParse adapter: successful parse emits Documents with `pdf_reader="liteparse"` metadata and bbox fields; two-column fixture produces `column` metadata; corrupt PDF returns structured error dict (not exception); LiteParse not installed → graceful failure when explicitly requested
- [x] 11.4 `tests/unit/test_pypdfium_reader.py` — pypdfium2 adapter: successful parse, missing-import handling
- [x] 11.5 `tests/unit/test_ingestion_pdf_extractor.py` — integration: `_read_and_chunk_file_async` uses the factory; bbox metadata propagates to Node.metadata for LiteParse path; pypdf path unchanged
- [x] 11.6 Mark all LiteParse-path tests with `@pytest.mark.slow` (they require `[pdf-liteparse]` extra and the native binary); ensure default `pytest -m "not slow"` skips them
- [ ] 11.7 Add CI matrix job that installs `[pdf-liteparse]` and runs the slow tests on macOS arm64 and Linux x86_64
- [ ] 11.8 Run `uv run pytest -m "not slow" --cov=rag_mcp` and verify overall coverage stays ≥90% (per AGENTS.md coverage thresholds); new modules in `readers/` target ≥95% (core-logic tier)

## 12. Documentation

- [ ] 12.1 Update `docs/guides/ingestion.md` (or equivalent) with a "PDF reader configuration" section: explain `PDF_READER` env var, `auto` resolution, `[pdf-liteparse]` extra, fallback behaviour
- [ ] 12.2 Update `README.md` MCP Tools table — no tool changes, but add a footnote on the `ingest_documents` row linking to the PDF reader guide
- [x] 12.3 Update `.env.example` with `PDF_READER`, `LITEPARSE_NUM_WORKERS`, `LITEPARSE_OCR_ENABLED` entries with explanatory comments
- [x] 12.4 Update `AGENTS.md` "Critical Gotchas" with: "The PDF reader is now a factory. Tests that pin reader behaviour MUST set `PDF_READER=pypdf` (or mock the factory) to stay deterministic. Default CI runs on pypdf."
- [ ] 12.5 Verify all doc claims by reading the actual source (per the user's documentation-as-contract preference)

## 13. Validation

- [x] 13.1 `uv run pytest -m "not slow" -v` — all existing tests still pass
- [ ] 13.2 `uv run pytest -m "slow" -v` — LiteParse-path tests pass when `[pdf-liteparse]` installed
- [ ] 13.3 `uv run pytest --cov=rag_mcp` — coverage thresholds met (≥90% overall, ≥95% for `readers/` and `config.py`)
- [ ] 13.4 `openspec validate use-liteparse-as-pdf-reader --strict` — no schema issues
- [ ] 13.5 `openspec validate --all --strict` — entire project OpenSpec is consistent
- [ ] 13.6 Manual smoke test: `uv run rag-mcp ingest ./experiments/11-liteparse-pdf-quality-2026-06-20/corpus --collection liteparse_smoke` with `PDF_READER=liteparse` set; verify chunks have bbox metadata
- [ ] 13.7 Manual smoke test: same with `PDF_READER=pypdf`; verify NO bbox metadata (only `pdf_reader="pypdf"` diagnostic)

## 14. Commit, push, open PR

- [ ] 14.1 Stage all implementation commits in logical groups (per AGENTS.md Conventional Commits):
  - `feat(readers): add pluggable pdf reader factory`
  - `feat(config): add PDF_READER env var and resolver`
  - `feat(ingestion): wire pdf reader factory into SimpleDirectoryReader`
  - `feat(pyproject): add pdf-liteparse optional extra`
  - `test(readers): add unit tests for pdf reader factory and adapters`
  - `docs(adr): add ADR-020 use-liteparse-as-pdf-reader`
  - `docs(guides): document PDF_READER configuration`
- [ ] 14.2 `git push -u origin feat/use-liteparse-as-pdf-reader`
- [ ] 14.3 `gh pr create --base master --head feat/use-liteparse-as-pdf-reader --title "feat: use LiteParse as pluggable PDF reader (gated by Experiment 11)" --body-file <(cat <<'EOF'\n## Summary\n- Introduces pluggable PDF reader factory (`src/rag_mcp/readers/`) with `PDF_READER` env var\n- LiteParse activated as default-when-installed, gated by Experiment 11 PASS\n- pypdf remains the implicit default until a follow-on change flips to `auto`\n- Bbox metadata captured on LiteParse-emitted Documents for future retrieval-side consumption\n- ADR-020 records the decision\n\n## Validation\n- Experiment 11 status: <PASS|FAIL>\n- Test coverage: <X%>\n- `openspec validate --all --strict`: <result>\n\n## Risk\n- Native build flakiness mitigated by `[pdf-liteparse]` extra isolation\n- Two-column reading order validated by Experiment 11\n- Full rollback: `PDF_READER=pypdf`\n\n## Follow-on changes (out of scope)\n- Flip `PDF_READER` default from `pypdf` to `auto` (post-merge)\n- `use-liteparse-for-office-docs` (Experiment 12)\n- `add-image-support-via-liteparse` (Experiment 13)\nEOF)"`
- [ ] 14.4 Wait for CI; fix any failures on the same branch and push again
- [ ] 14.5 Once CI is green and review is approved, squash-merge via GitHub UI or `gh pr merge --squash --delete-branch`

## 15. Post-merge: archive and sync

- [ ] 15.1 `git switch master && git pull origin master`
- [ ] 15.2 Delete local branch: `git branch -d feat/use-liteparse-as-pdf-reader`
- [ ] 15.3 Invoke the openspec-archive-change skill: `/opsx-archive` with `use-liteparse-as-pdf-reader`. This moves `openspec/changes/use-liteparse-as-pdf-reader/` → `openspec/changes/archive/<date>-use-liteparse-as-pdf-reader/` and syncs `openspec/specs/pdf-reader/spec.md` into the living specs
- [ ] 15.4 Verify `openspec validate --all --strict` still passes post-archive
- [ ] 15.5 Commit the archive move: `git add openspec/ && git commit -m "chore(openspec): archive use-liteparse-as-pdf-reader"`
- [ ] 15.6 If ADR-020 status is Accepted and follow-on promotion makes sense, open a new branch `feat/flip-pdf-reader-default-auto` for the `pypdf → auto` flip change referencing this merged change and ADR-020
- [ ] 15.7 Run `graphify update .` to refresh the knowledge graph with the new `readers/` module (per AGENTS.md graphify protocol)
