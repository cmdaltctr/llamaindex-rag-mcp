# ADR-063: Model-Token-Aware Markdown Chunking

**Date:** 2026-09-07
**Accepted:** 2026-09-09
**Status:** Accepted (task 5.5 promotion; evidence: Experiment 25, all four frozen gates PASS)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

Stage 3 Markdown chunking previously budgeted chunk size with a
four-characters-per-token approximation (`MarkdownNodeParser`/`SentenceSplitter`).
That estimate drifts from the token count the configured embedding model's
own tokenizer actually reports, which risks over-budget chunks at embedding
time and under-filled chunks that waste retrieval context — the property
Stage 5 evaluation exists to measure.

`semantic-text-splitter` (Rust-backed, `benbrandt/text-splitter`) can split
Markdown against a real Hugging Face tokenizer via
`MarkdownSplitter.from_huggingface_tokenizer`, preferring structural
boundaries — headings, paragraphs, tables, lists — before falling back to
smaller splits. Embedding inference and token counting are separate
concerns: Qwen inference may run through Ollama or another provider while
the tokenizer used for budgeting is resolved independently through
`EMBEDDING__TOKENIZER_MODEL`/`EMBEDDING__TOKENIZER_REVISION`, never guessed
from an inference-server alias.

Adopting an exact tokenizer changes chunk boundaries, `header_path`
derivation, the overlap contract, and what participates in index identity —
this reshapes the ingestion pipeline's chunking contract, not a local
workaround.

## Decision

1. **Model-token-aware Markdown splitting with `semantic-text-splitter`.**
   When a model-matched tokenizer is configured and resolves, Markdown
   documents route through the Rust-backed `MarkdownSplitter`, budgeted in
   the real embedding tokenizer's units (`CHUNKING__MARKDOWN_CHUNK_SIZE`),
   preferring headings/paragraphs/tables/lists before recursive smaller
   splits (design D4).

2. **Legacy fallback when the configured tokenizer cannot resolve.**
   `resolve_markdown_chunking()` resolves the tokenizer once per operation.
   If `EMBEDDING__TOKENIZER_MODEL`/`EMBEDDING__TOKENIZER_REVISION` are unset,
   or resolution fails (missing cache entry, no network access, unknown
   revision), the existing `MarkdownNodeParser`/`SentenceSplitter` path with
   character-based budgeting is used instead, with a warning naming the
   failure — the system never claims exact token accounting it does not
   have (design D4, spec: "Missing tokenizer preserves the existing path").

3. **The final token cap includes prepended heading text.** The cap governs
   the chunk text as finalised for embedding, not the raw structural chunk
   (design D4.3). When heading prepend is enabled, the splitter is given a
   capacity reduced by the prefix's token length so a prepended chunk cannot
   exceed the cap. If that reservation would leave no room for the
   configured overlap, the operation fails for that source naming
   `CHUNKING__MARKDOWN_CHUNK_SIZE`, `CHUNKING__CHUNK_OVERLAP`, and
   `CHUNKING__MARKDOWN_HEADING_PREPEND`, rather than silently clamping the
   overlap to whatever capacity remained (design D4.2, the review-fix
   commit `d713df0`'s central defect).

4. **Structured per-file failure for unreducible chunks.** A chunk that
   cannot be reduced below the cap through further splitting raises
   `ValueError` naming `CHUNKING__MARKDOWN_CHUNK_SIZE`. This is caught by
   the existing per-file ingestion failure path (`pipeline.py`'s per-file
   exception handler), so one Markdown structure that cannot fit reports
   that source as `status="failed"` while the rest of the ingestion batch
   continues — the pipeline never emits an over-budget chunk, and a raw
   splitter recursion-limit or library exception never escapes to the
   caller (design D4.3, spec: "A chunk that cannot be reduced fails instead
   of exceeding the cap").

5. **Resolved tokenizer and splitter state enters source identity.**
   `build_index_identity()` includes both the resolved tokenizer
   (`{model, revision}`) and `resolved_splitter`
   (`model_token_aware`/`legacy_fallback`) for every source
   (`source_state.py::build_index_identity`). Because these are resolved
   **once per ingestion operation**, not per file, and are baked into every
   processed source's identity, a change in tokenizer availability —
   populating or losing the cache, changing the configured model or
   revision — changes the recorded identity for every Markdown source
   touched by that operation. All of them reprocess on the next run even
   though their content did not change. This is deliberate: reprocessing is
   safer than silently mixing chunk boundaries and `header_path` derivation
   strategies within one collection.

6. **The `tokenizers>=0.20` floor caveat.** `pyproject.toml` declares
   `tokenizers>=0.20`; `tests/test_dependency_floors.py` carries an explicit
   exemption for it ("existing reranker/chunking API supports >=0.20; lower
   floor retained", ADR-042). Stage 3 close-out research (2026-09-07) found
   this floor is not validated end to end: this repository's lock file and
   CI exercise `tokenizers==0.22.2` only, and a
   `uv sync --resolution lowest-direct` run resolved `tokenizers==0.22.1` —
   still well short of `0.20.x`. `semantic-text-splitter` v0.32.0 itself
   declares no runtime `tokenizers` dependency in its wheel metadata (only
   under its own `test` extra), and its bundled Rust `tokenizers` crate has
   already moved to `^0.23` as of v0.31.0. The `>=0.20` floor is therefore
   an unproven convenience floor, not an upstream-guaranteed compatibility
   boundary. It is accepted as-is by this ADR; raising it is a separate,
   deliberately out-of-scope decision.

## Consequences

### Positive

- Chunk sizes are exact in the embedding model's own token units instead of
  a four-characters-per-token estimate, removing a source of
  retrieval-quality drift from over/under-sized chunks.
- Measured at promotion (Experiment 25): embedded request tokens −2.5%
  (0.975 × baseline), largest chunk halved (2,087 → 1,120 EMBED payload
  tokens), retrieval neutral (mean R@5 −2.0 pp, inside the frozen ±2.48 pp
  noise band; identifier-heavy R@10 −0.14 pp). The benefit is cost and
  input-contract correctness, not a quality win.
- `header_path` is derived directly from source-Markdown character offsets,
  correct for nested and skipped heading levels and immune to fenced-code
  false positives, without depending on a LlamaIndex parent-node
  relationship the Rust splitter does not produce.
- Failures are contained per source: a Markdown structure the splitter
  cannot fit fails that file, never the batch.
- The token cap, overlap, and heading-prepend contract are internally
  consistent — nothing is silently emitted outside the configured budget or
  below the configured overlap.

### Negative

- A tokenizer-availability change forces reprocessing of every Markdown
  source touched by that ingestion operation, not only the ones whose
  content changed — an operational cost operators must anticipate before
  rotating tokenizer configuration.
- Two Markdown code paths (model-token-aware and legacy character-based)
  must be kept correct and tested. This is deliberate (design D4: "preserve
  the current path rather than silently pretending"). Experiment 25
  promoted the model-token path to the shipped packaged default
  (2026-09-09); the legacy path remains as the explicit operator opt-out
  and the cache-miss fallback, so the added maintenance surface stays.
- Known latency cost of the promotion: mean query latency rose from
  1,023 ms to 1,593 ms in Experiment 25 (fewer, fuller chunks cost more to
  score per query); p95 2,183 ms stays inside the frozen 2,850 ms cap. If
  interactive agents find this too slow, the remedy is a smaller
  `CHUNKING__MARKDOWN_CHUNK_SIZE`, not a return to character budgeting.
- The `tokenizers>=0.20` floor is unproven below the locked `0.22.2`; an
  environment that resolves close to `0.20.0` has no verified guarantee of
  correct `from_huggingface_tokenizer()`/`no_truncation()` behaviour.

### Neutral

- Metadata-payload token overhead (`file_name`, `header_path`, `category`,
  `keywords`, `summary`, `document_title`, `content_type`) is measured by
  the chunking experiment but deliberately not folded into the enforced
  token cap, since it is not known when the splitter runs (design D4.3).

## Alternatives Considered

| Option | Rejected Because |
|---|---|
| **Character-based budgeting only (status quo, ~4 chars/token)** | Retained as the legacy fallback, but not promoted as the default: it is a coarse estimate that drifts from the real embedding tokenizer, which is the defect this ADR closes. |
| **Hard-fail ingestion when no model-matched tokenizer is configured** | Would break every deployment that has not set `EMBEDDING__TOKENIZER_MODEL`/`EMBEDDING__TOKENIZER_REVISION`; the fallback preserves current behaviour and only withholds the "exact" claim. |
| **Silently clamp overlap or emit an oversized chunk when a heading prefix crowds the budget** | This was the pre-fix behaviour (before commit `d713df0`); it lets the emitted chunking quietly diverge from the configured contract with no signal — the exact defect the token-cap/overlap contract in this ADR closes. |
| **Recover `header_path` via the existing `ensure_heading_metadata` helper** | That helper copies heading metadata from a parent LlamaIndex node; the Rust splitter emits plain strings with no parent node, so there is nothing for it to copy on this path (design D4.1). |
| **Fold retained metadata token overhead into the enforced cap** | Couples the chunker to the extraction pipeline's output, which is not known when the splitter runs; measured instead and reported as experiment evidence (design D4.3). |

## Evidence

- **Experiment 25** (`experiments/25-token-chunking-ablation-2026-09-08/`,
  task 5.2): rebuilt the Experiment 22 FreshStack index with this chunker
  (22,281 chunks vs 32,631) and evaluated the identical 223 raw queries
  under identical hybrid retrieval. All four frozen gates PASSED — quality
  R@5 0.2362 ≥ 0.2310; identifier-heavy R@10 0.2775 ≥ 0.2583; token ratio
  0.9749 ≤ 1.15; query p95 2,183 ms ≤ 2,850 ms. Full discussion in the
  experiment's `results.md`.
- Caveat carried forward: the R@5 point estimate sits 2.0 pp below
  baseline, inside the ±2.48 pp bootstrap noise band. One non-inferiority
  result is evidence of a wash; a second measurement below baseline should
  be treated as a trend, not luck.
- **Promotion action (task 5.5, 2026-09-09):** the packaged defaults became
  `EMBEDDING__TOKENIZER_MODEL=Qwen/Qwen3-Embedding-4B` and
  `EMBEDDING__TOKENIZER_REVISION=5cf2132abc99cad020ac570b19d031efec650f2b`
  in `core/settings.py`. The Qwen3 embedding family shares one
  151,669-token vocabulary, so the identity is model-matched for every
  shipped embedding size (0.6b local, 4b cloud). Explicit empty values opt
  back into the legacy path. Operational consequence: existing Markdown
  sources re-chunk on the next ingest, because the resolved splitter
  participates in the source index identity (decision 5).

## References

- `src/omrg/core/chunking/model_token.py`
- `src/omrg/core/ingestion/source_state.py` (`build_index_identity`)
- `src/omrg/core/ingestion/pipeline.py` (per-file failure handling)
- `openspec/changes/improve-rag-input-quality-5/design.md` (D4–D4.4)
- `openspec/changes/improve-rag-input-quality-5/specs/markdown-aware-chunking/spec.md`
- `tests/test_model_token_markdown_chunking.py`, `tests/test_markdown_chunking_pipeline.py`
- `tests/test_dependency_floors.py` (`tokenizers` exemption)
- ADR-042: Dependency Floor Integrity
- Review-fix commit `d713df0`: "fix: enforce the Markdown token cap and heading ancestry contract"
