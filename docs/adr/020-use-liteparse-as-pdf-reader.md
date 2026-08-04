# ADR-020: Adopt LiteParse as Pluggable PDF Reader

**Date:** 2026-06-23
**Status:** Accepted
**Update:** Cloud constraint superseded by ADR-024 — local-first, cloud allowed as opt-in.
**Amended:** 2026-08-04 — Phase 5 relocated the reader factory from `src/rag_mcp/readers/` to `src/rag_mcp/integrations/pdf/`. Factory dispatch behaviour and the `auto` fallback are unchanged. The old `readers/` path resolves via a deprecated re-export shim (removal in v2.0.0). See ADR-036 (Transport Separation).
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The PDF parsing path was the weakest link in the ingestion pipeline.
`llama-index-readers-file` resolved to **pypdf 6.11.0**, which is the
slowest and lowest-quality model-free PDF parser in published benchmarks.
It discards all layout information, producing interleaved garbage on
two-column academic PDFs — the dominant document type in this project's
target corpus.

**LiteParse** (run-llama/liteparse v2.1.1, Rust + PDFium, Apache-2.0) was
selected as the replacement because:

1. **Hard-constraint compatibility** — no PyTorch, no cloud APIs (matches
   AGENTS.md `🚫 Never` rules). Docling, Marker, Unstructured, and MinerU
   are blocked by the PyTorch rule; LlamaParse, Mistral OCR, and Firecrawl
   are blocked by the cloud rule.
2. **Best-in-class for the surviving field** — of the model-free options
   under the constraints (pypdf, pypdfium2, PyMuPDF4LLM, LiteParse), only
   LiteParse produces spatial text with bounding boxes, and only LiteParse
   is Apache-2.0 (PyMuPDF4LLM is AGPL-3 with distribution risk).
3. **Vendor alignment** — same team as LlamaIndex, favourable integration
   ergonomics and long-term maintenance outlook.

### Experiment 11 Results (the validation gate)

Experiment 11 (`experiments/11-liteparse-pdf-quality-2026-06-20/`) compared
pypdf vs LiteParse on a 20-paper academic corpus (895 pages, 25 queries)
across 4 cells (parser × reranker). Results:

| Gate                    | Result  | Evidence                                                                                                                                                                                                   |
| ----------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **H1 — Quality win**    | ✅ PASS | LiteParse nDCG@10 +6.9% over pypdf (3.207 vs 3.000). Hit@5: 100% vs 96%.                                                                                                                                   |
| **H2 — Speed win**      | ❌ FAIL | LiteParse 990.6s vs pypdf 932.8s (+6%). Parsing is 5.5× faster (5.6s vs 30.9s) but embedding dominates at 99% of wall-clock. LiteParse extracts 15% more chunks (3280 vs 2858), increasing embedding cost. |
| **H3 — Reranker helps** | ❌ FAIL | Corpus saturation — Hit@5 already 100% without reranking. Inconclusive, not a LiteParse regression.                                                                                                        |
| **H4 — No regression**  | ✅ PASS | Zero queries lost.                                                                                                                                                                                         |

**Verdict: PARTIAL.** Quality win confirmed; speed win failed because
LiteParse extracts _more_ text (a positive signal misread as a speed
regression by the total-wall-clock gate). H3 is a saturation artefact.

### Key insight on H2

The speed "failure" is misleading. LiteParse is 5.5× faster at parsing.
The total ingest is 6% slower because LiteParse produces 15% more chunks
(better text extraction → more content to embed). The embedding bottleneck
is Ollama, not the parser. Trading marginally longer ingest for measurably
better retrieval is the right trade.

## Decision

**Adopt LiteParse** as the default-when-installed PDF parser via a
pluggable reader factory (`src/rag_mcp/integrations/pdf/`, relocated
from `src/rag_mcp/readers/` in Phase 5 — ADR-020 amended). The factory
is controlled by the `PDF_READER` environment variable with values
`auto | liteparse | pypdfium2 | pypdf`.

**Until a follow-on change flips the default:** `PDF_READER=pypdf` remains
the implicit default. Users opt in via `uv sync --extra pdf-liteparse` and
`PDF_READER=liteparse` (or `PDF_READER=auto` once promoted).

**LiteParse is NOT a core dependency.** It is gated behind the
`[pdf-liteparse]` optional-dependency extra. Baseline `uv sync` does not
install it.

## Consequences

### Positive

- **Retrieval quality improved** by 6.9% nDCG@10 on the academic corpus.
- **Parsing speed improved** 5.5× (5.6s vs 30.9s for 20 PDFs).
- **Bounding-box metadata** captured on every LiteParse-emitted Document
  for future spatial RAG capabilities (citation highlighting, layout-aware
  retrieval, figure-caption linking).
- **Factory architecture** supports future parser swaps (pypdfium2, spdf,
  docling-onnx) without re-architecting.
- **pypdf remains available** as the always-installed fallback. Full
  rollback: `PDF_READER=pypdf`.

### Negative

- **Native build dependency.** LiteParse pulls a PDFium binary via
  pyo3/maturin. If the build fails on a platform, `auto` resolution falls
  back to pypdfium2 or pypdf.
- **Total ingest is 6% slower** because LiteParse extracts more text →
  more chunks → more embedding calls. This is a quality-cost trade, not a
  parser inefficiency.
- **H2 speed gate not met.** Future optimisation should target the
  embedding bottleneck (batched Ollama calls, smaller embedding model for
  draft indexing), not the parser.
- **H3 inconclusive due to corpus saturation.** The follow-on `auto`
  promotion change should validate reranker behaviour on a harder corpus
  (e.g. FreshStack, Qasper).

### Neutral

- `PDF_READER` default stays `pypdf` until a follow-on change flips to
  `auto`. This change ships the factory; promotion is separate.
- OCR is disabled by default (`LITEPARSE_OCR_ENABLED=False`). The corpus
  has no scanned PDFs; enabling OCR adds ~16s/file overhead.

## Alternatives Considered

| Option                       | Rejected Because                                                                                                                                                                                        |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **PyMuPDF4LLM**              | AGPL-3 licence incompatible with self-hosted distribution. Blocked by hard constraint.                                                                                                                  |
| **pypdfium2 only**           | Same PDFium engine as LiteParse but no bounding-box metadata, no column-aware reading order. Useful as a fallback tier (shipped as `[pdf-pypdfium2]` extra) but not as the primary parser.              |
| **Docling**                  | Requires PyTorch at runtime. Blocked by hard constraint (`🚫 Never: PyTorch at runtime`).                                                                                                               |
| **spdf**                     | MIT-licensed Rust clone of LiteParse, but immature (few users, limited track record). Worth re-evaluating if it stabilises.                                                                             |
| **Keep pypdf**               | 6.9% quality regression on academic PDFs. Two-column reading order is broken. Not acceptable for this project's corpus.                                                                                 |
| **Adopt without experiment** | Third-party benchmarks report two-column reading-order regressions on some layouts. Without our own measurement, we cannot distinguish "LiteParse helped" from "LiteParse hurt on our specific corpus". |

## References

- Experiment 11: `experiments/11-liteparse-pdf-quality-2026-06-20/`
- Experiment 11 results: `experiments/11-liteparse-pdf-quality-2026-06-20/results.md`
- OpenSpec change: `openspec/changes/use-liteparse-as-pdf-reader/`
- Spec: `openspec/changes/use-liteparse-as-pdf-reader/specs/pdf-reader/spec.md`
- ADR-005: Cross-Encoder Reranker with ONNX Runtime
- ADR-021: Reranker Inference Optimisation (discovered during Experiment 11)
- LiteParse: https://github.com/run-llama/liteparse
- LlamaIndex blog (LiteParse benchmarks): https://www.llamaindex.ai/blog/markdown-comes-to-liteparse
