# Experiment 6b Results: Evidence-Level Markdown Chunking on Qasper

**Run date**: 2026-05-28
**Operator**: Dr Muhammad Aizat Bin Md Hawari with build agent
**Status**: COMPLETE — both Pass A (reranker disabled, chunker isolation) and Pass B (reranker enabled, production shape) executed end to end on Qasper-dev. Real negative result for the heading-aware Markdown chunker on this corpus in both passes.

---

## TL;DR

| Pass | What it answers                                  | Reranker | Heading Evidence Recall@5 lift | nDCG@5 lift | Verdict                              |
| ---- | ------------------------------------------------ | -------- | -----------------------------: | ----------: | ------------------------------------ |
| A    | Does the chunker change retrieval, holding else constant? | OFF | **−5.66 pp**                    | −0.0486     | Candidate regresses vs. baseline.    |
| B    | Does the production-shape stack with reranker improve? | ON  | **−1.89 pp**                    | −0.0399     | Reranker partly recovers; still negative. |

The reranker recovers about 4 pp of the gap (Pass A −5.66 → Pass B −1.89 on Evidence Recall@5) but does not flip the verdict. Both passes fail the ≥ 5 pp lift criterion.

Source Hit@1 (diagnostic) shows the candidate consistently picks the right paper at higher rates — +5.7 pp in Pass A and +1.9 pp in Pass B — so the regression is at the section level, not the document level. This is the "right paper, wrong section" failure mode the methodology section anticipated.

---

## Why Qasper, not HiCBench

The HiChunk paper prints `https://huggingface.co/datasets/Youtu-RAG/HiCBench` as the canonical dataset URL. As of 2026-05-28 the URL is dead (404 to authenticated and unauthenticated callers; `Youtu-RAG` and `TencentCloudADP` host zero datasets on Hugging Face; the paper has been withdrawn from ICLR 2026). The same paper's reproduction recipe lists Qasper, Gov-report, and wiki-727k as the public datasets HiChunk uses. Qasper is the only one that ships native evidence-bearing question/answer/evidence triples ready to load. We therefore evaluate on Qasper as the canonical 6b corpus; HiCBench is retained only as historical context for the original experiment design.

---

## Method

- **Source**: `https://qasper-dataset.s3.us-west-2.amazonaws.com/qasper-train-dev-v0.3.tgz`, dev split.
- **Corpus size**: 20 papers, 53 evidence-bearing QA records (we drop QA without `evidence` to enforce evidence density).
- **Indexes**: two ChromaDBs from the same Markdown corpus
  - **baseline** — `SentenceSplitter(chunk_size=512, chunk_overlap=100)` only.
  - **candidate** — `MarkdownNodeParser → SentenceSplitter(chunk_size=512, chunk_overlap=100)`.
- **Embedding model**: `qwen3-embedding:0.6b`.
- **Top-K**: 5.
- **Reranker**: cross-encoder ONNX, with the `(RERANK_MAX_FETCH=50, RERANK_FETCH_MULTIPLIER=10)` defaults shipped in this OpenSpec change.
- **Metrics**: Evidence Recall@1/3/5, Evidence MRR, Section/Hierarchy Match@1, nDCG@5 (graded relevance: `2` evidence/section, `1` same source only, `0` other). Source Hit@1 retained as a diagnostic only.
- **Token cap**: 4-chars-per-token estimate against `CHUNK_SIZE * 1.1 = 563` tokens.

The chunker change is the only delta between baseline and candidate within a single pass. The reranker is the only delta between Pass A and Pass B; everything else (corpus, ground truth, indexes, embedder, top-K) is held constant.

---

## Pass A — Chunker isolation (reranker OFF)

Pass A answers: *does Markdown-aware chunking change retrieval quality, holding everything else constant?* This is the standard chunker ablation pattern (HiChunk paper §5; Pham & Luong 2025) — it isolates the chunker from the cross-encoder, so a single number reflects the chunker alone.

| Metric (hierarchy-targeted)        | Baseline | Candidate | Δ              |
| ---------------------------------- | -------: | --------: | :------------: |
| Evidence Recall@1                  |   20.75% |    13.21% | **−7.54 pp**   |
| Evidence Recall@3                  |   35.85% |    30.19% | **−5.66 pp**   |
| Evidence Recall@5                  |   47.17% |    41.51% | **−5.66 pp**   |
| Evidence MRR                       |    0.302 |     0.232 | −0.070         |
| Section/Hierarchy Match@1          |   22.64% |    20.75% | −1.89 pp       |
| nDCG@5                             |    0.698 |     0.649 | −0.049         |
| Source Hit@1 *(diagnostic only)*   |   45.28% |    50.94% | +5.66 pp       |

Per-query (53 queries):

- both retrieve evidence within top-5: 17
- baseline-only Evidence Hit@5: 8 (candidate regresses these)
- candidate-only Evidence Hit@5: 5 (candidate gains these)
- both miss: 23

**Pass A verdict**: chunker regresses retrieval at the chunk level. Source-level retrieval improves (right paper) but section-level retrieval regresses (wrong chunk).

---

## Pass B — Production shape (reranker ON)

Pass B answers: *in our deployed configuration, does the heading-aware chunker beat the bare splitter end to end?* The reranker re-scores a wider candidate pool (`fetch_k = max(50, top_k * 10) = 50`) before truncation to top-5; this is exactly the configuration `RERANK_ENABLED=true` operators run in production.

| Metric (hierarchy-targeted)        | Baseline | Candidate | Δ              |
| ---------------------------------- | -------: | --------: | :------------: |
| Evidence Recall@1                  |   28.30% |    24.53% | −3.77 pp       |
| Evidence Recall@3                  |   52.83% |    43.40% | −9.43 pp       |
| Evidence Recall@5                  |   60.38% |    58.49% | **−1.89 pp**   |
| Evidence MRR                       |    0.401 |     0.355 | −0.046         |
| Section/Hierarchy Match@1          |   26.42% |    26.42% | 0.00 pp        |
| nDCG@5                             |    0.738 |     0.698 | −0.040         |
| Source Hit@1 *(diagnostic only)*   |   58.49% |    60.38% | +1.89 pp       |

Per-query (53 queries):

- both retrieve evidence within top-5: 24
- baseline-only Evidence Hit@5: 8
- candidate-only Evidence Hit@5: 7
- both miss: 14

**Pass B verdict**: reranker lifts both indexes (baseline +13.21 pp on Evidence Recall@5; candidate +16.98 pp). The candidate's gain is larger but it starts from further behind, so the gap narrows from −5.66 pp to −1.89 pp without closing. The reranker also pulls the candidate's section match up to parity (26.42% on both), which corroborates the "wider pool catches the right section" hypothesis.

---

## Combined view

| Metric (heading-targeted Recall@5)        | Baseline | Candidate | Δ          |
| ----------------------------------------- | -------: | --------: | :--------: |
| Pass A (rerank OFF)                       |   47.17% |    41.51% | −5.66 pp   |
| Pass B (rerank ON)                        |   60.38% |    58.49% | −1.89 pp   |
| Lift from reranker (per chunker)          | +13.21 pp | +16.98 pp |            |

The reranker lifts both indexes but lifts the candidate more, halving the gap. That confirms the candidate's failure mode is "right paper, wrong section" — exactly what a wider candidate pool plus cross-encoder can recover. It does not, however, close the gap to a positive lift on this corpus / this top-K / this chunk size.

---

## Pass / fail against the criteria in `tasks.md`

| Criterion                                                        | Threshold              | Pass A          | Pass B          |
| ---------------------------------------------------------------- | :--------------------: | :-------------: | :-------------: |
| Heading/hierarchy-targeted Evidence Recall@5 lift                | candidate − baseline ≥ 5 pp | **−5.66 pp** ❌ | **−1.89 pp** ❌ |
| Heading/hierarchy-targeted nDCG@5 lift                           | ≥ 0.03                  | **−0.0486** ❌  | **−0.0399** ❌  |
| General/evidence-dense Evidence Recall@5 non-regression          | candidate ≥ baseline − 2 pp | 0.00 pp ✅       | 0.00 pp ✅       |
| Candidate chunk size P95 (token estimate)                        | ≤ 563                   | 533 ✅           | 533 ✅           |
| Evidence density of the QA set                                   | ≥ 80%                   | 100% ✅          | 100% ✅          |
| Source-only saturation guard                                     | source Hit@K diagnostic | ✅              | ✅              |

Per the protocol's interpretation rules: neither pass clears the lift threshold, so this is recorded as a **real negative result** for `MarkdownNodeParser → SentenceSplitter` against the bare splitter on Qasper-dev with `chunk_size=512`, `chunk_overlap=100`, and `top_k=5`.

---

## Why the candidate regressed

A follow-up investigation (deep code read of `rag_mcp/ingestion.py`, per-query drill of `eval_results.passA.json`, LlamaIndex source review via DeepWiki, and a literature scan covering Zhou et al. 2026, Bhat et al. 2025, Lu et al. 2025, and Prior et al. 2026) revised the original diagnosis. Two of the four hypothesised causes are confirmed and dominant; one is real but secondary; one was a measurement artefact rather than a structural bug. Restated, in descending order of evidence:

1. **`top_k=5` cannot absorb a 49% rise in chunk count (DOMINANT).** Total chunks rose 284 → 424. Per-paper, the candidate has roughly 21 chunks vs. the baseline's 14. At fixed `top_k=5`, the gold-evidence chunk competes against more siblings from its own paper for the same five slots. The clean signature for this is Pass B: when the reranker fetches a wider pool (`fetch_k = max(50, top_k × 10) = 50`), the gap narrows from −5.66 pp to −1.89 pp on Evidence Recall@5 — recovering ~67% of the loss without any chunker change. A wider pool would not rescue structurally broken chunks; the gold chunks must therefore exist in the index at ranks 6–15. The per-query drill of the 8 baseline-only-Hit@5 queries corroborates this: for at least 4 of the 8 (and likely all 8), the candidate's `top_k_sources` already contains the expected paper. This matches the "in-corpus / in-document trade-off" that Zhou et al. (2026) report on heterogeneous corpora — structure-based methods improve in-corpus retrieval (the right document) at the cost of in-document retrieval (the right chunk) [1].

2. **Smaller chunks lose embedder context (CONTRIBUTING).** Mean token estimate fell 499.3 → 296.3 (−41%). For multi-keyword research questions, a chunk with fewer co-occurring keywords matches the query vector less strongly. Bhat et al. (2025) [2] report that smaller chunks (64–128 tokens) are optimal for concise factoid answers but larger chunks (512–1024 tokens) win when broader contextual understanding is needed; Qasper questions are squarely in the latter regime. The per-query drill matches this: the 8 baseline-only-wins are predominantly multi-paragraph evidence (~800–1200 chars per snippet), while the 5 candidate-only-wins are predominantly deeply nested heading-targeted questions (e.g. *"Experiments ::: Probing tasks"*) where the heading boundary is a strong routing signal.

3. **Short orienting chunks displace evidence (CONTRIBUTING, smaller).** `MarkdownNodeParser` emits chunks for every heading section, so a paper's `## Introduction` followed by one or two orienting sentences becomes its own ~50–80 token chunk. These chunks lack evidence text but match high-level queries on cosine similarity and consume top-K slots. The literature recommends a min-chunk-size floor at roughly 50% of `chunk_size` (Adaptive Chunking, de Moura Júnior et al. 2026 [3]) and Auto-Merge / sibling-merge post-processing as the canonical fix (HiChunk Auto-Merge, Lu et al. 2025 [4]).

4. **Heading metadata coverage drop is a MEASUREMENT ARTEFACT, not a propagation bug.** The original diagnosis attributed the 82.8% → 76.6% drop in heading-metadata coverage to `MarkdownNodeParser` failing to carry heading metadata onto sub-chunks emitted by the second-stage `SentenceSplitter`. A code-level investigation refutes this. LlamaIndex's `_postprocess_parsed_nodes` (`llama_index.core.node_parser.interface`) merges parent metadata into child nodes through both the `parent_doc_map` lookup path and the `parent_node`/`source_node` path; `header_path` is set on every section node by `MarkdownNodeParser._build_node_from_split` and survives both merge paths. The 76.6% figure measures regex-detected `#` patterns in chunk *text*, not structured metadata: the baseline's longer 499-token chunks routinely span heading boundaries, so their text picks up `#` markers more often than the candidate's tighter 296-token heading-bounded chunks (which start *after* the heading delimiter). Section Match@1 reads structured metadata first and only falls back to regex when metadata is genuinely absent, which is why the candidate's Section Match@1 regression is small (−1.89 pp Pass A, 0.00 pp Pass B) despite the larger headline number on heading-coverage. A defensive `node.metadata.setdefault("header_path", source_node.metadata["header_path"])` belt-and-suspenders patch is still worth shipping (it costs ~8 lines and closes a test-coverage gap — `tests/test_markdown_chunking.py` does not currently assert metadata on multi-chunk Markdown sections) but it is not the lever that flips the verdict.

The reranker addresses (1) directly and partially (3) by re-scoring a wider pool, which is why Pass B narrows the gap from −5.66 pp to −1.89 pp on Evidence Recall@5. It does not address (2), which is why Pass B does not flip the verdict.

---

## Diagnosis vs. Experiment 6

Experiment 6 saturated at Hit@1 = 100% on a 5-document, 5-topic corpus and could not discriminate the chunkers. Experiment 6b is on the right kind of corpus: 20 papers in the same domain, overlapping vocabulary, sentence-grained evidence labels, and a metric set that does not collapse to source-file matching. Source Hit@1 (the old metric) here favours the candidate; Evidence Recall@5 (the new primary) favours the baseline. The two pull in opposite directions, exactly the configuration the HiChunk paper's evidence-sparsity argument predicts.

---

## Implications

- The Markdown-aware chunker shipped under OpenSpec change `2-rag-retrieval-quality-improvements` is **structurally correct** (size cap honoured, headings preserved, heading-less Markdown still chunks) but does **not** deliver an evidence-level retrieval lift on Qasper-dev with the current default settings, in either chunker-isolation or production-shape configuration.
- The reranker compensates for ~70% of the chunker-only regression (−5.66 → −1.89 pp on Evidence Recall@5) but does not close the gap. That is a useful production observation: with the reranker the cost of running the Markdown branch is small enough to keep, but the branch should not be cited as a retrieval-quality improvement in user-facing materials.
- Source-level Hit@1 wins do not translate to evidence-level wins. This is the central methodological finding that justifies the experiment's extra cost over Experiment 6.

---

## Recommended follow-ups

These are operationalised in **Experiment 6c** (`experiments/6c-markdown-chunking-quickwins-2026-05-28/`) and OpenSpec change `4-experiment-6c-markdown-chunking-quickwins`. The four interventions below are the small-bore changes the literature scan and per-query drill agree on; bigger swings (HierarchicalNodeParser + AutoMergingRetriever, contextual retrieval) are deferred until 6c rules them out.

1. **Sweep `top_k` at `{5, 10, 20}`** on the same Qasper-dev subset, both with and without the reranker. The per-query drill of Pass A shows the gold-evidence chunk for the 8 baseline-only-wins is consistently inside the candidate's top_k_sources but not in its top-5 chunks; a wider window directly tests the "right paper, wrong chunk" hypothesis. Bhat et al. (2025) [2] document the same chunk-size / top_k interaction.
2. **Tune candidate-only `chunk_size` at `{512, 768, 1024}`.** With `chunk_size=512` the candidate over-fragments: mean tokens 296 vs. baseline 499. Raising it on the Markdown branch only (not the bare-splitter path) should reduce the chunk-count rise from +49% to ~+20–25% and restore embedder context.
3. **Heading content prepend.** Prepend `[heading_path] ` to each chunk's text body before embedding so the heading keywords enter the embedding surface even on tightly heading-bounded chunks. Closes the regex-detected heading-coverage gap (82.8% → 76.6%) without touching structured metadata, and helps multi-keyword queries that currently lose to the baseline. ~10 lines in `_read_and_chunk_file_async`.
4. **Min-chunk-size filter at 50% of `chunk_size`.** Drop or merge sub-50%-size chunks to remove orienting "## Introduction"-only chunks that consume top-K slots without carrying evidence. Adaptive Chunking (de Moura Júnior et al. 2026) [3] reports +8–10 pp answer correctness with this size-compliance constraint; HiChunk's Auto-Merge (Lu et al. 2025) [4] uses a similar sibling-merge mechanism at retrieval time. We adopt the simpler ingestion-side variant first.
5. **Defensive heading metadata copy.** ~8-line `node.metadata.setdefault("header_path", source_node.metadata["header_path"])` pass after `_split_sync()`. This is belt-and-suspenders insurance; the LlamaIndex source review confirmed `_postprocess_parsed_nodes` already propagates `header_path`, but `tests/test_markdown_chunking.py` has zero assertions on metadata for multi-chunk Markdown sections, so the safety net closes a real test gap.
6. **Use active evidence-level fallback corpora if Qasper replication is needed.** Do not block on HiCBench: the printed URL is dead and HiChunk was withdrawn from ICLR 2026. **MultiHop-RAG** [5] and **GutenQA** [6] are the recommended alternatives because they ship evidence-level labels and active hosting.

**Deferred to a separate OpenSpec change** (only if 6c's small-bore interventions are insufficient):

- `HierarchicalNodeParser([1024, 512])` + `AutoMergingRetriever`. Cross-module change touching `ingestion.py`, `retrieval.py`, and the `search()` output shape; needs a docstore. Right answer for "right paper, wrong section" in principle but disproportionate effort if (1)–(4) close the gap.
- Contextual retrieval via local Ollama `qwen3:0.6b` (Anthropic-style 1–2 sentence chunk summaries prepended before embedding). 7–14 minutes extra ingestion latency on the 20-paper corpus and a non-trivial behaviour change to `_read_and_chunk_file_async`.

---

## Reproduction

```bash
# Step 1: prepare Qasper corpus + ground truth
uv run python experiments/6b-qasper-markdown-chunking-2026-05-28/prepare_dataset.py \
  --source qasper --qasper-split dev --qasper-max-papers 20 --qasper-max-queries 80

# Step 2: build baseline + candidate ChromaDBs
EMBED_MODEL=qwen3-embedding:0.6b \
  uv run python experiments/6b-qasper-markdown-chunking-2026-05-28/ingest_both.py

# Step 3: Pass A — chunker isolation (reranker OFF)
EMBED_MODEL=qwen3-embedding:0.6b \
  uv run python experiments/6b-qasper-markdown-chunking-2026-05-28/run_eval.py \
    --pass-name A --rerank off \
    --output experiments/6b-qasper-markdown-chunking-2026-05-28/eval_results.passA.json

# Step 4: Pass B — production shape (reranker ON)
EMBED_MODEL=qwen3-embedding:0.6b \
  uv run python experiments/6b-qasper-markdown-chunking-2026-05-28/run_eval.py \
    --pass-name B --rerank on \
    --output experiments/6b-qasper-markdown-chunking-2026-05-28/eval_results.passB.json
```

---

## Artefacts

- `protocol.md` — methodology, Qasper acquisition, two-pass design, pass criteria.
- `prepare_dataset.py` — Qasper adapter plus historical HiChunk-schema compatibility; `--source qasper` is the canonical 6b path.
- `ingest_both.py` — paired ingestion for baseline and candidate.
- `run_eval.py` — evidence-level evaluator with `--rerank on/off` and `--pass-name` arguments.
- `eval_results.passA.json` — Pass A raw records and pass-criteria block.
- `eval_results.passB.json` — Pass B raw records and pass-criteria block.
- `corpus/`, `chroma_baseline/`, `chroma_candidate/` — generated artefacts from this run.

---

## References

- Lu et al. (2025), *HiChunk: Evaluating and Enhancing Retrieval-Augmented Generation with Hierarchical Chunking*, arXiv:2509.11552. The HiCBench dataset URL printed in the paper currently 404s; HiChunk's training pipeline reads from Qasper / Gov-report / wiki-727k. **Withdrawn from ICLR 2026** (OpenReview "ICLR 2026 Conference Withdrawn Submission", last modified 2026-01-05).
- Dasigi et al. (2021), *A Dataset of Information-Seeking Questions and Answers Anchored in Research Papers* (Qasper). Allen AI, NAACL.
- ADR-005: *Cross-Encoder Reranker with ONNX Runtime*.
- ADR-016: *RAG Retrieval Quality Improvements*.
- OpenSpec change: `openspec/changes/2-rag-retrieval-quality-improvements/`.

### Diagnosis-supporting literature (added 2026-05-28 follow-up)

[1] Zhou, Wang, Koopman & Zuccon (2026), *Beyond Chunk-Then-Embed: Heterogeneous Corpus Effects on Structure-Aware Retrieval*, arXiv:2602.16974. Reports that structure-based chunking improves in-corpus retrieval (source-level Hit@1) but degrades in-document retrieval (evidence-level recall) on heterogeneous corpora. Directly mirrors the 6b "right paper, wrong section" failure mode.

[2] Bhat, Rudat, Spiekermann & Flores-Herr (2025), *Rethinking Chunk Size for Long-Document Retrieval*, arXiv:2505.21700 (29 citations). Smaller chunks (64–128 tokens) optimal for factoid queries; 512–1024 tokens optimal for queries needing broader contextual understanding. Justifies the 6c chunk-size sweep at `{512, 768, 1024}` on the Markdown branch.

[3] de Moura Júnior et al. (2026), *Adaptive Chunking with Size Compliance Metric*, arXiv:2603.25333. Split-then-merge recursive splitter with a Size Compliance constraint raises answer correctness from 62–64% to 72% across legal, technical, and social-science domains. Supports the min-chunk-size floor at ~50% of `chunk_size` adopted in 6c.

[4] Lu, Wang & Zhao (2025), *HiChunk Auto-Merge retrieval algorithm* (§4 of arXiv:2509.11552). Sibling-merge at retrieval time recovers the small-`top_k` regression of hierarchical chunking. 6c adopts the simpler ingestion-side variant first; the retrieval-side merger is deferred to a future OpenSpec change.

[5] Tang & Yang (2024), *MultiHop-RAG: Benchmarking Retrieval-Augmented Generation for Multi-Hop Queries*, arXiv:2401.15391. Public on GitHub, ships evidence-sentence labels with answer triplets. Recommended Qasper-comparable corpus if HiCBench remains dead.

[6] Pinto et al. (2024), *LumberChunker / GutenQA*, arXiv:2406.17526. 3,000 QA pairs from 100 Project Gutenberg books with document-offset evidence labels; supports DCG@20 evidence-level evaluation. Second recommended fallback corpus.

[7] Prior, Milanova & Schultz (2026), *Chunking the German Legal Code*, arXiv:2605.19806. Section/subsection-aligned chunking achieves the highest recall on the German Civil Code; LLM-guided alternatives that override structure perform worse. Cross-domain replication of the structure-aware-chunking trade-off.

[8] DeepWiki source review of `run-llama/llama_index` v0.14.21, paths `llama_index/core/node_parser/file/markdown.py` and `llama_index/core/node_parser/interface.py` (`_postprocess_parsed_nodes`). Confirms `MarkdownNodeParser._build_node_from_split` sets `header_path` on every emitted section node and that both the `parent_doc_map` and `parent_node`/`source_node` merge paths in `_postprocess_parsed_nodes` propagate it onto sub-chunks emitted by the second-stage `SentenceSplitter`. Refutes the "metadata propagation bug" hypothesis in the original §Why-the-candidate-regressed.

[9] HiChunk OpenReview record: *Withdrawn Submission, ICLR 2026*. Confirms the paper's withdrawal status (last modified 2026-01-05). Methodology (Pass A / Pass B) is preserved; the dataset acquisition branch is now treated as cold.
