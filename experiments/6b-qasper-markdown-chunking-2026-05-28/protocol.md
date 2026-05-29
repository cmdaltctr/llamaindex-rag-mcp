# Experiment 6b: Evidence-Level Markdown Chunking on Qasper

**ID**: `qasper-evidence-markdown-chunking-2026-05-28`
**Date**: 2026-05-28
**Operator**: Dr Muhammad Aizat Bin Md Hawari with build agent
**Status**: COMPLETE — `--source qasper` is the canonical run. HiCBench was investigated and found unavailable; it is retained only as historical context, not as the active corpus.
**Related OpenSpec change**: `2-rag-retrieval-quality-improvements`

---

## What this experiment fixes

Experiment 6 used a 5-document, 5-topic Markdown corpus. The metric was source-file Hit@K, baseline Hit@1 saturated at 100%, and the chunker change had no headroom to show. That is the classic **evidence sparsity** failure mode (Lu et al. 2025, HiCBench paper): a benchmark that scores at the document level cannot tell good chunkers from bad ones.

Experiment 6b corrects three things:

1. **Corpus**: 20 NLP research papers (Allen AI Qasper, dev split). Single domain, overlapping vocabulary, multiple sections per paper, real evidence labels at sentence granularity.
2. **Metric**: evidence-level (Evidence Recall@K, MRR, nDCG@5) with source Hit@1 demoted to a diagnostic.
3. **Methodology**: two-stage. Pass A isolates the chunker (reranker off). Pass B reproduces production shape (reranker on).

---

## Corpus and acquisition: Qasper, not HiCBench

The HiChunk paper (Lu et al. 2025, arXiv:2509.11552) prints `https://huggingface.co/datasets/Youtu-RAG/HiCBench` as the canonical dataset URL. As of 2026-05-28 that URL returns HTTP 404 to authenticated and unauthenticated callers, the `Youtu-RAG` and `TencentCloudADP` author namespaces on Hugging Face host zero datasets, and the paper has been withdrawn from ICLR 2026. We logged the dead-link evidence in this directory's git history.

The same paper's reproduction recipe (`TencentCloudADP/hichunk` README) lists **Qasper, Gov-report, and wiki-727k** as the public datasets HiChunk uses for in-domain training and evaluation. Qasper is the only one of the three that ships native evidence-bearing question/answer/evidence triples ready to load — exactly the shape Experiment 6b needs.

We therefore evaluate on Qasper as the canonical 6b corpus. HiCBench is no longer part of the active 6b workflow; the adapter remains in `prepare_dataset.py` only as historical compatibility with the original HiChunk schema.

### Qasper acquisition

```bash
uv run python experiments/6b-qasper-markdown-chunking-2026-05-28/prepare_dataset.py \
  --source qasper \
  --qasper-split dev \
  --qasper-max-papers 20 \
  --qasper-max-queries 80
```

The adapter:

1. Downloads `https://qasper-dataset.s3.us-west-2.amazonaws.com/qasper-train-dev-v0.3.tgz`.
2. Extracts the `qasper-dev-v0.3.json` file.
3. Renders each paper to Markdown with H1 (title), H2 (section), H3 (subsection) hierarchy.
4. Builds `ground-truth.json` from QA records that carry at least one `evidence` sentence — QA without evidence are dropped to enforce evidence density.
5. Maps QA fields to the local schema:

   | Qasper QA field                                            | Adapter target          | Notes                                                                                |
   | ---------------------------------------------------------- | ----------------------- | ------------------------------------------------------------------------------------ |
   | `question`                                                 | `query`                 | Required.                                                                            |
   | `answers[].answer.evidence`                                | `evidence_snippets`     | Verbatim evidence sentences. Primary signal for Evidence Recall@K.                   |
   | `answers[].answer.free_form_answer` / `extractive_spans`   | `expected_answer`       | First non-empty answer string.                                                       |
   | derived from longest matching paragraph                    | `expected_section`      | Last hierarchy element where the evidence sentence appears.                          |
   | derived from path                                          | `hierarchy_path`        | Section path from H1 down to the matching paragraph.                                 |
   | `paper_id`                                                 | `expected_source`       | Mapped to the `NNN-{paper_id}.md` filename written into `corpus/`.                   |

### Historical HiCBench adapter

`prepare_dataset.py` still contains `_normalise_hicbench` because 6b was originally scoped against the HiChunk / HiCBench schema (`input` / `_id` / `answers` / `evidences` / `facts` / `all_classes`). The upstream dataset URL was unavailable, so this path is not part of the active reproduction workflow. The canonical 6b command is `--source qasper`.

---

## Methodology: two-stage reranker pass

The reranker is enabled by default in production (`RERANK_ENABLED=true` in `.env.example`). A single number with reranker on or off in isolation can mislead. Pass A and Pass B answer different questions:

- **Pass A — chunker isolation (reranker disabled).**
  Answers: "does Markdown-aware chunking change retrieval quality, holding everything else constant?". This is the ablation HiChunk and Pham & Luong 2025 themselves report; it isolates the chunker from the cross-encoder. No production claims are made from Pass A alone.

- **Pass B — production shape (reranker enabled).**
  Answers: "in our deployed configuration, does the heading-aware chunker beat the bare splitter end to end?". Uses the rerank-fetch-pool defaults shipped in this OpenSpec change (`RERANK_MAX_FETCH=50`, `RERANK_FETCH_MULTIPLIER=10`). This is the number a deployment decision should be made on.

Both passes use the same Markdown corpus, the same QA set, the same embedding model, the same `top_k`, and the same `chunk_size` / `chunk_overlap`. The only delta between A and B is the reranker.

### Indexes

Two ChromaDB persist directories, both built from the same Markdown corpus:

- `chroma_baseline/` — `SentenceSplitter(chunk_size=512, chunk_overlap=100)` only.
- `chroma_candidate/` — `MarkdownNodeParser → SentenceSplitter(chunk_size=512, chunk_overlap=100)`.

```bash
EMBED_MODEL=qwen3-embedding:0.6b \
  uv run python experiments/6b-qasper-markdown-chunking-2026-05-28/ingest_both.py
```

### Eval invocations

```bash
# Pass A — chunker isolation (reranker disabled)
EMBED_MODEL=qwen3-embedding:0.6b \
  uv run python experiments/6b-qasper-markdown-chunking-2026-05-28/run_eval.py \
    --pass-name A --rerank off --output eval_results.passA.json

# Pass B — production shape (reranker enabled)
EMBED_MODEL=qwen3-embedding:0.6b \
  uv run python experiments/6b-qasper-markdown-chunking-2026-05-28/run_eval.py \
    --pass-name B --rerank on --output eval_results.passB.json
```

The evaluator reads the same ChromaDBs, the same `ground-truth.json`, and writes one JSON per pass plus an aggregated `eval_results.json` summary.

---

## Metrics

Primary (per category, computed on both passes):

1. **Evidence Recall@1 / @3 / @5** — fraction of queries where any retrieved chunk up to rank `k` contains a verbatim evidence sentence (or the expected answer when no evidence list is present).
2. **Evidence MRR** — reciprocal rank of the first evidence-bearing chunk, averaged.
3. **Section / hierarchy Match@1** — top-1 chunk matches the expected section/hierarchy. Reads structured chunk metadata first; falls back to regex on chunk text only when metadata is missing.
4. **nDCG@5** — graded relevance over top 5: `2` evidence/section match, `1` same source document only, `0` other.

Diagnostic (reported, not gated):

- Source Hit@1 — kept only to expose source-level saturation. Must NOT be used as the primary success criterion.
- Chunk count / mean / P95 / max token estimate per index.
- Heading metadata coverage on candidate chunks.

---

## Evidence-density guard

`run_eval.py` validates the QA set before retrieval starts:

- ≥80% of QA records must contain `evidence_ids`, `evidence_snippets`, or a verifiable `expected_answer`.
- Every QA must have an `expected_source` (used as a diagnostic only).
- Hierarchy-targeted QAs must carry `expected_section` or `hierarchy_path`.
- Source-level Hit@K cannot be the only success signal.

If any of these fail, the evaluator stops with an evidence-sparsity error.

---

## Pass criteria

Experiment 6b passes if **both Pass A and Pass B** clear these thresholds on the heading/hierarchy-targeted QA split:

| Criterion                                                        | Threshold                                |
| ---------------------------------------------------------------- | ---------------------------------------- |
| Evidence Recall@5 lift (candidate − baseline)                    | ≥ 5 percentage points                    |
| nDCG@5 lift (candidate − baseline)                               | ≥ 0.03                                   |
| General/evidence-dense Evidence Recall@5 non-regression          | candidate ≥ baseline − 2 percentage points |
| Candidate chunk size P95 (token estimate)                        | ≤ `CHUNK_SIZE * 1.1`                     |
| Evidence density of the QA set                                   | ≥ 80% of QA records carry evidence       |
| Source-only saturation guard                                     | source Hit@K reported as a diagnostic    |

Interpretation rules:

- If **only Pass A passes**, the chunker is the cause of the lift — ship the Markdown branch but keep an eye on the production-shape (B) regression in follow-up work.
- If **only Pass B passes**, the lift is reranker-driven, not chunker-driven — keep both shipped, but do not market the Markdown branch as a chunking improvement.
- If **both pass**, the chunker change is genuine retrieval-quality improvement.
- If **neither passes**, treat as a real negative result on this corpus and document the recommended follow-ups.

---

## Implementation notes

- The candidate chunker is wired in `rag_mcp.ingestion._read_and_chunk_file_async` and ships in OpenSpec change `2-rag-retrieval-quality-improvements`.
- The reranker is the cross-encoder (ONNX) shipped under ADR-005, with the wider fetch pool from ADR-016 / this OpenSpec change.
- `retrieval.search()` exposes the chunk's full `metadata` dict in each result row, so Section Match reads structured metadata first; the regex fallback is only used when metadata is genuinely absent.
- Evidence snippet matching is normalised: case-insensitive, whitespace-collapsed substring match against the chunk text.
- The Markdown candidate chunker writes new chunk metadata (`heading_path` and `header`) when LlamaIndex's `MarkdownNodeParser` emits them; we do not back-fill metadata for chunks where the parser left it off.
