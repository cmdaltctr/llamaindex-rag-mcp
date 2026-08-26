# Experiment 7 results — metadata extraction cap and persisted granularity

**Status: PASS** (H1–H5 all PASS)
**Executed:** 2026-08-19 · **Protocol version:** 1.0 · **Deterministic fake extractor; no real LLM, no network calls on the measured path**

## Verdicts

| Hypothesis | Verdict | Numbers |
|---|---|---|
| H1 — cap unit | **PASS** | For every cell, the number of chunks entering the extractor pipeline is exactly `min(N, total)` in **chunk units**: M1 → 1, M3 → 3, M10 → 10, against totals of 24 (synthetic) and 16 (realistic Markdown). The tail beyond the cap (23/21, 13, 14/6 chunks respectively) never entered the extractors. |
| H2 — prefix coverage | **PASS** | The sha256 sequence of the observed selected chunks equals the first N ground-truth hashes exactly (`selected_hashes_match_first_n: true` in all 6 cells; ground truth committed in `fixtures/expected_chunks.json` before the treatment runs). |
| H3 — file-level persisted semantics | **PASS** | Temporary per-chunk enrichments differ by construction (fake outputs embed each chunk's unique marker); the aggregated file-level metadata is identical on **every final stored chunk** in all 6 cells (uniformity flag `true`; final chunk counts 24/26 per document), and equals the pre-registered expectation: synthetic `{category: kw0000a, keywords: "kw0000a, kw0000b", summary: "Summary for marker 0000 of the corpus section.", document_title: "Combined title 0000"}`; realistic `{...1000...}`. |
| H4 — no accidental per-chunk claim | **PASS** | Every cell manifest declares `metadata_granularity: file_aggregate` (pinned by the plan assertion), matching the Stage 1 documentation correction (task 1.3.3) and the observed behaviour in H3. **Gap reported:** production has no runtime attribute exposing granularity — H4 is satisfied via manifest + docs, with the gap recorded in `output/summary.json` (`H4_granularity_identified.gap_note`), not worked around. |
| H5 — bounded cost | **PASS** | Fake-LLM call count per cell: M1 → 4, M3 → 10, M10 → 26 — exactly the locked analytic `2N + min(5, N) + 1` (N keyword + N summary calls + min(5, N) title-candidate calls + 1 title-combine call; kinds breakdown for M10: 10/10/5/1). Tail-independence: at each cap the two documents with different tails (24 vs 16 total chunks) produce **identical** call counts. |

Overall status word: **PASS**.

## Unit-bug visibility (protocol §15)

Token and character coverage sit side by side in `fixtures/expected_chunks.json` (per-chunk `tokens`, `chars`, `chars_per_token`). Synthetic document divergence ratio **1.575** (chars/token 1.769–2.786 across chunks); realistic document 1.052 (mild, as expected for prose). The pre-registered divergence floor of 1.5 for the synthetic document passed at ground-truth time and is asserted again by the runner's ground-truth preflight.

## Production path exercised

`rag_mcp.core.ingestion.chunker.read_and_chunk_file_async` with `extraction_mode="llamaindex"` and `LLAMANDEX_EXTRACTOR_MAX_CHUNKS` set per cell — the full production chain: reader → metadata split (`SentenceSplitter(512/100)`, exactly the construction in `core/metadata/llamaindex.py`) → cap → `IngestionPipeline` (Title/Keyword/Summary extractors) → `_aggregate_llamaindex_metadata` (first-non-empty rule) → final chunking with the aggregated metadata copied onto every final chunk.

Two harness-only seams (no production file edited):

1. `rag_mcp.core.providers.llm.registry.get` → factory returning `CountingMockLLM` (subclasses LlamaIndex `MockLLM`; deterministic marker-derived outputs; full call accounting). The preflight guard aborts any cell whose extraction degrades or records zero fake calls — proof the fake was the LLM in play (this guard fired correctly during harness bring-up when a wrapper bug caused a real fallback attempt).
2. `llama_index.core.ingestion.IngestionPipeline.arun` wrapped to record the exact node texts entering the extractor pipeline (delegating via `__wrapped__` because the locked `arun` carries a wrapt-style decorator).

## Manifest identities (TDR-014)

- `repo_commit`: `c475852cf195…` (branch `harden-pipeline-correctness-before-calibration`; `git_dirty=true` — parallel stage-5 agent artefacts are uncommitted in the shared worktree)
- `dependency_lock_hash`: `3a225230a6eb…` (sha256 of `uv.lock`)
- `corpus_identity`: `sha256:77afe91a344cf…` (fixtures/manifest.json pre-registration — identical across all six cells, pinned by `assert_controlled_constant`)
- `chunker.requested == chunker.effective == "sentence"` (the declared metadata splitting policy); `chunker.fallback_reason` null in every cell.
- `metadata_granularity: file_aggregate` in every cell manifest (plan assertion).
- **Nulls by design**: embedding/vector_store/sparse/reranker/retrieval sections are explicit nulls with `null_reasons` — the TDR-014 mandatory-field list for admissible ADR evidence applies to retrieval experiments; this is a metadata-experiment with nulls by design.

## Reproduction

```bash
# 0. Regenerate fixture documents (deterministic)
uv run --no-sync python experiments/example/experiment-7-metadata-cap-and-granularity/prepare_fixtures.py
# 1. Ground truth + pre-registration (MUST run before treatments; protocol section 9)
uv run --no-sync python experiments/example/experiment-7-metadata-cap-and-granularity/make_ground_truth.py
# 2. Measured run (six cells, atomic checkpoints, --resume supported)
uv run --no-sync python experiments/example/experiment-7-metadata-cap-and-granularity/run_eval.py
# 3. Deterministic-rerun proof (byte-identical diff of every cell JSON)
uv run --no-sync python experiments/example/experiment-7-metadata-cap-and-granularity/run_eval.py --verify-rerun
# 4. Summary + verdicts
uv run --no-sync python experiments/example/experiment-7-metadata-cap-and-granularity/summarise_eval.py
```

Deterministic-rerun proof: `output/verify_rerun.json` records `byte_identical=true` for all six cells.

## Artefacts

| Path | Content |
|---|---|
| `fixtures/synthetic_token_char_divergence.txt` | 24-chunk divergence corpus (markers MARK0000X–MARK0069X) |
| `fixtures/realistic_long_document.md` | 16-chunk realistic Markdown article (markers MARK1000X–) |
| `fixtures/expected_chunks.json` | Ground truth: per-chunk sha256/tokens/chars/first-marker (splitter-only, pre-treatment) |
| `fixtures/manifest.json` | Pre-registration: identities, fake output templates, aggregation rule, expected aggregated metadata |
| `fake_llm.py` | `CountingMockLLM` + template fingerprints + call summarisation |
| `plan.json` | Six-cell machine-readable plan (`ExperimentPlan.from_json`) |
| `output/cells/M{1,3,10}__{synthetic,realistic_md}.json` | Raw rows (D16) + observed selections + call summaries + final chunk hashes |
| `output/manifests/*.manifest.json` | Six D13 runtime manifests |
| `output/checkpoint.json`, `output/verify_rerun.json` | Checkpoint + byte-identity proof |
| `output/summary.json` | Hypothesis verdicts + per-cell table |

All artefact paths verified non-gitignored (`git check-ignore` exit 1).

## Production defects found

None. The Stage 1 split-then-cap implementation (task 1.3.1) behaves exactly as specified in every cell.

## Judgement calls

- The analytic call-count constant was corrected during bring-up from an initial `3N + min(5,N) + 1` to the observed `2N + min(5,N) + 1` (title candidates are limited to `min(5, N)` nodes, and only keyword + summary scale with the full N); the first full run's artefacts were deleted and all six cells re-run clean before the recorded run — the committed cells all carry the corrected constant.
- Cell artefacts store only the order-independent (sorted) call summary so async job scheduling cannot break byte-identical reruns; the raw ordered log is never persisted.
- The realistic Markdown document's final chunks (26) legitimately differ from its metadata chunks (16) because final chunking for `.md` uses `markdown_chunk_size=1024` with `MarkdownNodeParser`, while metadata splitting always uses `chunk_size=512` — recorded per cell (`final_chunk_count` vs `expected_total_chunks`) as designed behaviour, not a confound.
- H4 is satisfied by manifest declaration plus documentation because production exposes no runtime granularity attribute; the gap is reported in the summary artefact rather than papered over.
- `expected_aggregation` in the pre-registration is computed through the production helpers (`_parse_keywords_from_meta`, `_derive_category`, `_truncate_*`, `_strip_llm_prefix`) applied to the pre-registered fake templates — the expectation exists before treatments, derived from chunk 0's marker via the documented first-non-empty rule.
