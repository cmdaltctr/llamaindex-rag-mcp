# Experiment: Embedding Model Retrieval Quality Comparison

**ID**: `embedding-model-comparison-2026-05-19`
**Date**: 2026-05-19
**Operator**: Dr Muhammad Aizat Bin Md Hawari
**Status**: PASS

---

## Hypothesis / Purpose

`qwen3-embedding:0.6b` produces retrieval results at least as good as `nomic-embed-text`
(768-dim) and `qwen3-embedding:8b` (4096-dim), while offering significantly better
throughput.

## Variables

| Type                         | Variable                                    | Values                                                           |
| ---------------------------- | ------------------------------------------- | ---------------------------------------------------------------- |
| Independent (what we change) | Embedding model                             | `nomic-embed-text`, `qwen3-embedding:0.6b`, `qwen3-embedding:8b` |
| Dependent (what we measure)  | Hit@1, Hit@3, Hit@5, MRR, avg query latency | —                                                                |
| Controlled (held constant)   | Reranker                                    | Disabled                                                         |
| Controlled (held constant)   | Corpus                                      | 6 documents, 207 chunks                                          |
| Controlled (held constant)   | Chunk size / overlap                        | 512 / 64                                                         |
| Controlled (held constant)   | Similarity threshold                        | 0.0 (no filtering)                                               |

## Background

Experiment 1 measured how the cross-encoder reranker and similarity threshold affect
retrieval quality using a single embedding model (`nomic-embed-text`). This experiment
answers a different question: **which embedding model produces better retrieval results?**

Throughput benchmarking (via `rag-mcp benchmark`, with `ScientificAdvertising.pdf`, 117 chunks)
shows:

| Model                  | Throughput      | Dimensions | Query Latency |
| ---------------------- | --------------- | ---------- | ------------- |
| `nomic-embed-text`     | 15.3 chunks/sec | 768        | ~36 ms        |
| `qwen3-embedding:0.6b` | 4.5 chunks/sec  | 1024       | ~104 ms       |
| `qwen3-embedding:8b`   | 0.63 chunks/sec | 4096       | ~259 ms       |

But throughput is only half the story. A slower model is acceptable if it retrieves
more relevant results. This experiment measures that trade-off.

---

## What We Are Measuring

For each query, we check whether the **correct document** appears in the top-K results
returned by each embedding model. We measure:

- **Hit Rate@1** — Is the correct document the very top result?
- **Hit Rate@3** — Is the correct document in the top 3 results?
- **Hit Rate@5** — Is the correct document in the top 5 results?
- **MRR (Mean Reciprocal Rank)** — Average of `1/rank` for the first correct result across all queries. A score of 1.0 means every query got the right document at position 1.
- **Average latency per query** — How long each query takes.

We test all models on the **same corpus** and the **same queries**, with reranking
disabled, so the only variable is the embedding model.

---

## Step 1: Prepare Your Corpus

Place 5–10 documents (PDF, MD, or TXT) into the `corpus/` directory:

```
experiments/embedding-model-comparison-2026-05-19/corpus/
├── why-language-models-hallucinate.pdf
├── learning-to-code-systematic-review.pdf
├── handwriting-brain-connectivity-eeg.pdf
├── paper-search-mcp-cf-README.md
├── grep-ai-README.md
├── ghazali-mustasfa.pdf
└── ...
```

Guidelines for selecting documents:

- Use documents you are **familiar with** so you can write accurate queries.
- Choose documents with **overlapping themes** (e.g., all ML papers, or all about a
  specific technology). This makes retrieval harder and more discriminating.
- Aim for a mix of lengths — short articles and longer papers.
- Ensure file names are **descriptive** so the `expected_source` field is easy to write.

---

## Step 2: Write Your Ground-Truth Queries

Read each document and write queries that should retrieve that document. Write these
queries **before running the experiment** to avoid confirmation bias.

Edit `ground-truth.json` and replace the example entries with your own.

**Format**:

```json
{
  "queries": [
    {
      "query": "Your search question here",
      "expected_source": "substring-of-filename",
      "expected_answer": "short phrase from document text"
    }
  ]
}
```

**Guidance for writing good queries**:

| Query Type        | Description                                | Example                                                                |
| ----------------- | ------------------------------------------ | ---------------------------------------------------------------------- |
| **Easy**          | Contains keywords from the document        | "What does the attention mechanism in the transformer do?"             |
| **Hard**          | Paraphrased, conceptual, no exact keywords | "How can a neural network process sequences without using recurrence?" |
| **Cross-topical** | Could match multiple documents             | "What training objective is used?" (matches several ML papers)         |

Aim for:

- **3–5 queries per document**
- **15–30 queries total**
- Roughly 60% easy, 30% hard, 10% cross-topical

---

## Step 3: Ensure All Models Are Available

```bash
# Pull all models in Ollama
ollama pull nomic-embed-text
ollama pull qwen3-embedding:0.6b
ollama pull qwen3-embedding:8b

# Verify they are available
ollama list
```

---

## Step 4: Run the Experiment

```bash
cd experiments/embedding-model-comparison-2026-05-19
uv run python run_eval.py
```

The script will:

1. Load your `ground-truth.json`
2. For each model in its `MODELS` list (`nomic-embed-text`, `qwen3-embedding:0.6b`,
   `qwen3-embedding:8b`):
   - Set up a fresh temporary ChromaDB
   - Ingest the `corpus/` directory
   - Run each query and record results
3. Print a comparison table
4. Save raw results to `eval_results.json`

**If `corpus/` is empty**, the script will fall back to the test fixtures at
`tests/fixtures/` so you can verify the script works before doing the real experiment.

**To add or remove models**: edit the `MODELS` list near the top of `run_eval.py`.

---

## Step 5: Interpret the Results

The output table looks like:

```
┌──────────────────────┬──────────┬──────────┬──────────┬───────┬──────────┐
│ Model                │  Hit@1   │  Hit@3   │  Hit@5   │  MRR  │ Avg Lat  │
├──────────────────────┼──────────┼──────────┼──────────┼───────┼──────────┤
│ nomic-embed-text     │  94.1%   │  94.1%   │  94.1%   │ 0.941 │ 36.2 ms  │
│ qwen3-embedding:0.6b │ 100.0%   │ 100.0%   │ 100.0%   │ 1.000 │ 104.3 ms │
│ qwen3-embedding:8b   │ 100.0%   │ 100.0%   │ 100.0%   │ 1.000 │ 259.2 ms │
└──────────────────────┴──────────┴──────────┴──────────┴───────┴──────────┘
```

Key questions to answer:

1. **Is the quality difference worth the throughput trade-off?**
   `qwen3-embedding:0.6b` is ~3× slower than `nomic-embed-text` for ingestion but
   achieves perfect retrieval (100% vs 94.1% Hit@1). The 8b model offers **no quality
   advantage** over the 0.6b model while being 7× slower for ingestion.

2. **Which queries does each model fail on?**
   Check the per-query detail table to see if failures cluster on hard queries.

3. **Is the MRR difference significant?**
   A small MRR gap (< 0.05) probably does not justify switching models.
   A gap >= 0.05 is meaningful.

---

## Troubleshooting

| Problem                      | Solution                                                                 |
| ---------------------------- | ------------------------------------------------------------------------ |
| `Ollama is not reachable`    | Run `ollama serve` in another terminal                                   |
| `Model not found`            | Run `ollama pull <model-name>`                                           |
| `corpus/ is empty` warning   | This is fine — the script uses test fixtures as fallback                 |
| Embedding dimension mismatch | The script creates a fresh ChromaDB per model, so this should not happen |
| Script crashes on import     | Ensure you run from the project root or use `uv run`                     |

---

## Notes

- The reranker is **disabled** in this experiment so we isolate embedding model quality.
- Each model gets its own temporary ChromaDB because vectors from different models
  have different dimensions and cannot coexist in the same collection.
- The script cleans up temporary directories after completion.
- All results are saved to `eval_results.json` for post-hoc analysis.
- The `MODELS` list in `run_eval.py` can be edited to add or remove models from the comparison.

---

## Artefacts

| File                | Description                                           |
| ------------------- | ----------------------------------------------------- |
| `protocol.md`       | This file — hypothesis, method, reproduction steps    |
| `results.md`        | Full results with per-query detail and score tables   |
| `run_eval.py`       | Automation script (17 queries × 3 models)             |
| `eval_results.json` | Raw per-query results (scores, sources, latency)      |
| `ground-truth.json` | Pre-written queries with expected sources and answers |
| `questions.md`      | Human-readable ground-truth queries with full answers |
| `corpus/`           | Test documents (6 files: PDFs + Markdown)             |
