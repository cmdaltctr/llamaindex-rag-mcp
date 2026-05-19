# Experiment 2: Embedding Model Retrieval Quality Comparison — Results

**Date run**: 19 May 2026 (run 2 — all 3 models)
**Purpose**: Compare retrieval quality between `nomic-embed-text` (768-dim), `qwen3-embedding:0.6b` (1024-dim), and `qwen3-embedding:8b` (4096-dim)
**Method**: For 17 queries across 6 documents, does each model retrieve the correct document in the top-K results? Reranking disabled.

---

## Corpus (6 documents — 207 chunks total)

| #  | Document                                                       | Chunks |
| -- | -------------------------------------------------------------- | ------ |
| 1  | Kalai et al. - 2025 - Why Language Models Hallucinate.pdf        | 84     |
| 2  | Ghazali-Mustasfa.pdf                                            | 36     |
| 3  | Popat and Starkey - 2019 - Learning to code or coding to learn A systematic review.pdf | 40 |
| 4  | Van Der Weel and Van Der Meer - 2024 - Handwriting but not typewriting leads to widespread brain connectivity a high-density EEG study wit.pdf | 36 |
| 5  | paper-search-mcp-cf-README.md                                   | 8      |
| 6  | grep-ai-README.md                                               | 3      |

---

## Head-to-Head Summary

| Metric              | nomic-embed-text (768-dim) | qwen3-embedding:0.6b (1024-dim) | qwen3-embedding:8b (4096-dim) |
| ------------------- | -------------------------- | ------------------------------- | ----------------------------- |
| **Hit@1**           | 94.1% (16/17)              | **100.0% (17/17)**              | **100.0% (17/17)**            |
| **Hit@3**           | 94.1% (16/17)              | **100.0% (17/17)**              | **100.0% (17/17)**            |
| **Hit@5**           | 94.1% (16/17)              | **100.0% (17/17)**              | **100.0% (17/17)**            |
| **MRR**             | 0.941                      | **1.000**                       | **1.000**                     |
| **Avg latency**     | **36.2 ms**                | 104.3 ms                        | 259.2 ms                      |
| **Query speed**     | fastest                    | 2.9× slower than nomic          | 7.2× slower than nomic        |

---

## Key Findings

### 1. Both qwen3 variants achieve perfect retrieval — 8b offers no quality advantage

This is the most important finding: `qwen3-embedding:0.6b` and `qwen3-embedding:8b` are **tied on quality** at 100% Hit@1. The larger 8b model does NOT retrieve any additional correct documents that the 0.6b model missed. The 4096-dim embeddings are no better at distinguishing between these 6 topic-diverse documents than 1024-dim embeddings.

### 2. qwen3-embedding:0.6b is the clear winner

| Comparison       | Quality              | Embedding Throughput                    | Query Latency                 |
| ---------------- | -------------------- | --------------------------------------- | ----------------------------- |
| 0.6b vs nomic    | **0.6b wins** (100% vs 94.1%) | nomic **3.4× faster** (15.3 vs 4.5 chunks/sec) | nomic 2.9× faster |
| 0.6b vs 8b       | **Tied** (100% both) | **0.6b is 13.2× faster** (8.35 vs 0.63 chunks/sec) | **0.6b is 2.5× faster** |

The 0.6b model:
- **Outperforms nomic** in retrieval quality (100% vs 94.1% Hit@1) while being only ~3× slower to embed
- **Matches 8b** in retrieval quality (both 100% Hit@1)
- **2.5× faster query latency** than 8b (104ms vs 259ms)
- **13.2× faster embedding** than 8b (8.35 vs 0.63 chunks/sec, from `rag-mcp benchmark`)
- **4× smaller vectors** than 8b (1024-dim vs 4096-dim), meaning smaller ChromaDB storage

### 3. nomic-embed-text: fastest, but misses one query

nomic missed query 11: *"Tell me more about the literature-review prompt"* (targeting the paper-search README). The top-5 results were dominated by unrelated documents (Ghazali, coding paper, hallucination paper). Both qwen3 models retrieved the correct document for this query. The README is the second-smallest document (8 chunks), and this particular section is a small portion of it — nomic's 768-dim embeddings struggled to pick out the semantic signal.

### 4. Interesting side note: 8b has higher confidence on certain queries

While quality is tied, the 8b model showed notably higher similarity scores on some queries:
- Query 10 (*"Which academic sources are supported by the search_papers tool?"*): 8b scored **0.8898**, compared to 0.6542 (nomic) and 0.5880 (0.6b)
- This higher confidence does not translate to better retrieval outcomes for this corpus

---

## Per-Query Detail

### Document 1: Why Language Models Hallucinate (Kalai et al. 2025)

| #  | Query                                                    | nomic rank/score | 0.6b rank/score  | 8b rank/score        |
| -- | -------------------------------------------------------- | ---------------- | ---------------- | -------------------- |
| 1  | How does pretraining training data force models to hallucinate? | 1st / 0.632 | 1st / 0.564 | 1st / 0.578 |
| 2  | Does optimising for cross-entropy loss make models less trustworthy? | 1st / 0.596 | 1st / 0.446 | 1st / 0.491 |

### Document 2: Learning to code or coding to learn (Popat & Starkey 2019)

| #  | Query                                                    | nomic rank/score | 0.6b rank/score  | 8b rank/score        |
| -- | -------------------------------------------------------- | ---------------- | ---------------- | -------------------- |
| 3  | How does coding improve mathematical problem-solving skills in children? | 1st / 0.729 | 1st / 0.567 | 1st / 0.650 |
| 4  | Does coding also improve social skills and collaboration? | 1st / 0.729 | 1st / 0.510 | 1st / 0.645 |
| 5  | Does seating arrangement really impact how children collaborate? | 1st / 0.427 | 1st / 0.343 | 1st / 0.378 |

### Document 3: Handwriting but not typewriting leads to widespread brain connectivity

| #  | Query                                                    | nomic rank/score | 0.6b rank/score  | 8b rank/score        |
| -- | -------------------------------------------------------- | ---------------- | ---------------- | -------------------- |
| 6  | How does handwriting's brain connectivity benefit memory and learning processes? | 1st / 0.746 | 1st / 0.662 | 1st / 0.706 |
| 7  | What are the specific brain regions involved in handwriting hubs? | 1st / 0.657 | 1st / 0.564 | 1st / 0.591 |
| 8  | Does using a digital pen activate the same brain regions as handwriting? | 1st / 0.707 | 1st / 0.600 | 1st / 0.626 |

### Document 4: paper-search-mcp-cf-README.md

| #  | Query                                                    | nomic rank/score | 0.6b rank/score  | 8b rank/score        |
| -- | -------------------------------------------------------- | ---------------- | ---------------- | -------------------- |
| 9  | What are the primary differences between the local and remote versions? | 1st / 0.399 | 1st / 0.309 | 1st / 0.340 |
| 10 | Which academic sources are supported by the search_papers tool? | 1st / 0.654 | 1st / 0.588 | 1st / **0.890** |
| 11 | Tell me more about the literature-review prompt.          | **— / 0.469** ❌  | 1st / 0.380 ✅ | 1st / 0.447 ✅ |

### Document 5: grep-ai-README.md

| #  | Query                                                    | nomic rank/score | 0.6b rank/score  | 8b rank/score        |
| -- | -------------------------------------------------------- | ---------------- | ---------------- | -------------------- |
| 12 | How does semantic search outperform traditional text matching in codebases? | 1st / 0.465 | 1st / 0.562 | 1st / 0.656 |
| 13 | How does grepai help reduce AI agent input tokens?         | 1st / 0.634      | 1st / 0.599      | 1st / 0.572          |
| 14 | Can I use grepai completely offline with Ollama?            | 1st / 0.531      | 1st / 0.451      | 1st / 0.501          |

### Document 6: Ghazali-Mustasfa.pdf

| #  | Query                                                    | nomic rank/score | 0.6b rank/score  | 8b rank/score        |
| -- | -------------------------------------------------------- | ---------------- | ---------------- | -------------------- |
| 15 | How does al-Ghazali view the role of human reason?         | 1st / 0.544      | 1st / 0.493      | 1st / 0.539          |
| 16 | Why was al-Ghazali sceptical of natural philosophy and physics? | 1st / 0.569 | 1st / 0.477 | 1st / 0.559 |
| 17 | How did al-Ghazali's views differ from his teacher Juwayni? | 1st / 0.575      | 1st / 0.537      | 1st / 0.538          |

---

## Score Distribution

| Metric                  | nomic-embed-text | qwen3-embedding:0.6b | qwen3-embedding:8b |
| ----------------------- | ---------------- | -------------------- | ------------------ |
| Average top score       | 0.579            | 0.506                | 0.561              |
| Highest top score       | 0.746            | 0.662                | **0.890**          |
| Lowest top score (hit)  | 0.399            | 0.309                | 0.340              |

---

## Conclusion

The evidence is conclusive:

| Decision               | Throughput Evidence                           | Quality Evidence                                |
| ---------------------- | --------------------------------------------- | ----------------------------------------------- |
| **0.6b over 8b**       | ✅ **13.2× faster** embedding (8.35 vs 0.63 chunks/sec) | ✅ **Neither has quality advantage** — both score 100% Hit@1 |
| **0.6b over nomic**    | ⚠️ nomic **3.4× faster** (15.3 vs 4.5 chunks/sec)    | ✅ **0.6b is better** — 100% vs 94.1% Hit@1 |

**Recommendation**: Use `qwen3-embedding:0.6b` as the default embedding model. It delivers the same perfect retrieval quality as the 8b model while being 13.2× faster to embed and 2.5× faster per query, and it outperforms nomic-embed-text on retrieval quality while maintaining acceptable latency (~104ms).

## Raw Data

Full per-query results with all scores and source paths are saved in `eval_results.json`.
