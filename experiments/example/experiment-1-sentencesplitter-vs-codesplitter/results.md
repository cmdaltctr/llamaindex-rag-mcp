# Experiment 1 results — SentenceSplitter vs CodeSplitter structural integrity

**Status: PASS** (H1, H2, H3 all PASS; H4 not run — optional arm)
**Executed:** 2026-08-19 · **Protocol version:** 1.0 · **Structural-only execution**

## Verdicts

| Hypothesis | Verdict | Numbers |
|---|---|---|
| H1 — execution | **PASS** | 18/18 fixture files report `requested=code`, `effective=code`, zero fallbacks; every file dispatched through the production `content_type` code path (`core/ingestion/chunker.py`) with the mapped tree-sitter language (python/javascript/typescript). |
| H2 — structural integrity | **PASS** | `structural_cut_rate(C)=0.2326` (10 cut boundaries / 43) vs `structural_cut_rate(S)=0.375` (15/40). Stricter reading: **C cut 0 definitions that fit under the 1500-char ceiling; S cut 6.** All 10 C cuts fell inside the five definitions whose spans exceed the ceiling (1544–2357 chars) — the documented upstream recursion semantics (protocol §16). Paired per-file bootstrap CI on cut-boundary counts (C − S): delta = −0.278, 95% CI [−0.556, 0.0], n = 18, seed 20260819. |
| H3 — boundedness | **PASS** | 0 chunks exceeded `code_max_chars=1500` in the code cell (so zero unexplained violations). Recursive splitting of the five over-ceiling definitions produced segments within the ceiling. |
| H4 — retrieval sanity | **NOT RUN** | Optional arm; requires embedding runtime; H1–H3 are the correctness gates (see protocol §2). |

Overall status word: **PASS**.

## Per-stratum results (protocol §6/§15)

Paired per-file differences are in `output/summary.json` (`cells/{S,C}/by_language` and `by_complexity`). Headline strata:

- **python** (12 files): S cut rate 0.4138 (12/29 boundaries), C 0.2500 (8/32).
- **javascript** (4 files): S 0.3333 (3/9), C 0.2222 (2/9); **typescript** (2 files): 0 cuts in both arms.
- **complexity=simple**: both arms 0 cuts — the no-cut baseline stratum.
- **complexity=nested**: S 3/16 cut boundaries, C 0/13 — the AST splitter kept every (fitting) nested definition intact.
- **complexity=boundary**: S 9/10, C 8/16 — concentrates the documented over-ceiling cuts (see the five definitions named below).
- **complexity=long-body**: S 3/11, C 2/11.

Full raw boundary locations for every cut and violation are in `output/cells/{S,C}.json` (`cut_events`, `violation_events`) per protocol §15.

## Documented upstream semantics observed (protocol §16)

- A definition whose span exceeds `max_chars` is legitimately split by CodeSplitter's recursive descent (`llama_index/core/node_parser/text/code.py::_chunk_node`): the oversized child is re-chunked at its own children boundaries. The five over-ceiling fixture definitions (`at_ceiling` 1544, `long_body_0` 1584, `oversizedJs` 2191, `boundary_engine` 2242, `oversized` 2357) were split this way; every resulting segment respected the 1500-char ceiling.
- The installed LlamaIndex 0.14.23 `CodeSplitter.split_text` records but does not use `chunk_lines`/`chunk_lines_overlap` — boundaries are driven by `max_chars` alone. The settings are still recorded in the runtime manifest (`chunking_settings`) exactly as configured; this is an upstream observation, not a defect in the repaired adapter (which passes the parameters the locked API accepts).

## Manifest identities (TDR-014)

- `repo_commit`: `c475852cf195…` (branch `harden-pipeline-correctness-before-calibration`; `git_dirty=true` — experiment artefacts from parallel stage-5 agents are uncommitted in the shared worktree)
- `dependency_lock_hash`: `3a225230a6eb…` (sha256 of `uv.lock`)
- `corpus_identity`: `sha256:4f0bb34201491…` (fixtures/manifest.json — identical across both cells, pinned by `assert_controlled_constant`)
- `chunker.requested == chunker.effective` per cell (`sentence`/`code`); `chunker.fallback_reason` null in both.
- **Nulls by design**: embedding/vector_store/sparse/reranker/retrieval manifest sections are explicit nulls with `null_reasons`. TDR-014's mandatory-field list for admissible ADR evidence applies to retrieval experiments; this is a chunker experiment with nulls by design.

## Reproduction

```bash
# 1. Regenerate fixtures + frozen labels (source-only; ruff-formatted, byte-stable)
uv run --no-sync python experiments/example/experiment-1-sentencesplitter-vs-codesplitter/prepare_fixtures.py
# 2. Measured run (both cells, atomic checkpoints, --resume supported)
uv run --no-sync python experiments/example/experiment-1-sentencesplitter-vs-codesplitter/run_eval.py
# 3. Deterministic-rerun proof (byte-identical diff of cell JSON)
uv run --no-sync python experiments/example/experiment-1-sentencesplitter-vs-codesplitter/run_eval.py --verify-rerun
# 4. Summary + verdicts
uv run --no-sync python experiments/example/experiment-1-sentencesplitter-vs-codesplitter/summarise_eval.py
```

Deterministic-rerun proof: `output/verify_rerun.json` records `byte_identical=true` for both cells (S sha256 `702b754f…`, C sha256 `d38c4597…`). Row `latency_ms` is 0.0 by design so structural output is the only content; wall-clock timings went to stderr only.

## Artefacts

| Path | Content |
|---|---|
| `fixtures/manifest.json` | Pre-registered labels: sha256, language, complexity, definition line spans, fit-under-ceiling flags (written before treatments) |
| `fixtures/src/*.{py,js,ts}` | 18 committed synthetic fixtures (12 Python, 4 JavaScript, 2 TypeScript) |
| `plan.json` | Machine-readable 2-cell plan (loadable via `ExperimentPlan.from_json`) |
| `output/cells/S.json`, `output/cells/C.json` | Raw per-file rows (D16 contract) + cut/violation events |
| `output/manifests/{S,C}.manifest.json` | D13 runtime manifests |
| `output/checkpoint.json` | Atomic cell checkpoint (`--resume`) |
| `output/verify_rerun.json` | Deterministic-rerun byte-identity proof |
| `output/summary.json` | Aggregates, strata, hypothesis verdicts |

All artefact paths verified non-gitignored (`git check-ignore` exit 1).

## Preflight performed per cell (TDR-014)

1. `plan.assert_runner_cells(build_cell_matrix())` before measured work.
2. `verify_code_splitter_signature()` — locked `CodeSplitter.__init__` contains `language`/`chunk_lines`/`chunk_lines_overlap`/`max_chars`.
3. Per-cell `assert_manifest` (plan assertions + cell-specific `chunker.requested`/`effective` equality) and `assert_no_fallback`.
4. Per-fixture byte-identity: on-disk sha256 must equal the pre-registered label sha256 in every cell (labels frozen before treatments, protocol §9/§13).
5. Cross-cell `assert_controlled_constant` over `corpus_identity`, `dependency_lock_hash`, and all five chunking settings.

## Production defects found

None. The repaired adapter and dispatch path behaved exactly as the Stage 1 contract specifies on all 18 fixtures.

## Judgement calls

- `latency_ms` is 0.0 in raw rows (allowed by the D16 harness brief) so `--verify-rerun` can byte-compare; wall-clock per-file timings were printed to stderr during the run and are not artefacts.
- `run_eval.py` is 549 lines — above the ~500 convention but the `tests/test_file_size_ceiling.py` ceiling governs `src/rag_mcp/` only (same precedent as the Stage 4 runners at 650/690 lines).
- Generated `.py` fixtures are ruff-formatted inside `prepare_fixtures.py` before labelling so committed bytes, labels, and `ruff format --check` can never disagree; regenerating is idempotent.
- Cell S reaches SentenceSplitter via the production generic document path (`content_type=None`, extraction disabled) rather than a synthetic splitter call — the control arm therefore shares the exact reader/metadata machinery of the treatment arm except the dispatch branch itself. The code cell additionally stamps `content_type` metadata onto nodes (inherent to the production code-dispatch branch).
- H2's primary gate is the protocol's literal `structural_cut_rate(C) < structural_cut_rate(S)`; the fit-vs-oversized cut classification is reported as the stricter "ideally zero" reading of protocol §14.
