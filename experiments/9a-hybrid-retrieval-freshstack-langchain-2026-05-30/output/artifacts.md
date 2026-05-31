# Artifacts — Experiment 9a

**Experiment**: `9a-hybrid-retrieval-freshstack-langchain-2026-05-30`
**Date completed**: 2026-05-31
**Repository**: [cmdaltctr/llamaindex-rag-mcp](https://github.com/cmdaltctr/llamaindex-rag-mcp)

---

## GitHub Release

Large artifacts are uploaded to the GitHub release for this experiment:

> **Release URL**: https://github.com/cmdaltctr/llamaindex-rag-mcp/releases/tag/exp-9a-hybrid-retrieval

*Release published; see assets in the release above.*

---

## File Inventory

### In Git (committed)

These files are tracked in version control and always available:

| File | Size | Description |
| ---- | ---- | ----------- |
| `protocol.md` | 12 KB | Experiment plan, hypothesis, pass gates, interpretation rules |
| `prepare_freshstack.py` | ~8 KB | Downloads FreshStack LangChain corpus from HuggingFace, exports as Markdown + manifest |
| `build_indexes.py` | ~6 KB | Builds Chroma indexes with progress logging and resume support |
| `run_eval.py` | ~12 KB | Runs 4-cell eval grid with checkpoint/resume support |
| `summarise_eval.py` | ~5 KB | Aggregates raw results into metrics tables |
| `output/ground-truth.json` | 5.4 MB | Query set with identifier/semantic categories and relevant parent IDs |
| `output/freshstack-qrels.json` | 3.9 MB | Nugget-level qrels preserving FreshStack structure |
| `output/eval_results.summary.json` | 12 KB | Aggregated metrics by cell and query category |
| `output/results.md` | 12 KB | Human-readable result report with interpretation |
| `output/index_build.json` | 4 KB | Chroma index build metadata |
| `output/.gitignore` | <1 KB | Excludes large files from git |

### Not in Git (large files in release)

These files are too large for GitHub's repository size limits and are only available via the release:

| File | Size | Description |
| ---- | ---- | ----------- |
| `output/chroma_dense/` | 315 MB | ChromaDB persistent index for dense-only cells (SQLite + embeddings) |
| `output/chroma_hybrid_bm25/` | 310 MB | Copy of dense index; BM25 built in-memory at query time |
| `output/eval_results.json` | 21 MB | Raw per-query results: 223 queries × 4 cells with full retrieval data |
| `output/eval_results_checkpoint.json` | 21 MB | Checkpoint file used by resume logic (identical to eval_results.json after completion) |
| `output/build_indexes.log` | 32 KB | Build progress log |
| `output/run_eval.log` | 4 KB | Eval run log |
| `corpus/langchain/` | 116 MB | 10,009 exported FreshStack LangChain parent documents (front-matter Markdown) |
| `corpus/continuity/` | <1 MB | 16 Exp 9 continuity documents |
| `corpus/langchain_manifest.jsonl` | <1 MB | JSONL manifest mapping FreshStack IDs to file paths |

**Total release size**: ~770 MB (compressed)

---

## What Each File Contains

### `output/chroma_dense/`

ChromaDB persistent client directory containing:
- `chroma.sqlite3` — SQLite database with document text, metadata, and vector embeddings
- `*.bin` — HNSW index files for approximate nearest neighbor search

Contains 10,025 documents (10,009 FreshStack + 16 continuity) embedded with `qwen3-embedding:0.6b`.

**Use case**: Load directly into ChromaDB for inspection or further experiments:
```python
import chromadb
client = chromadb.PersistentClient(path="output/chroma_dense")
collection = client.get_collection("documents")
print(f"{collection.count()} documents indexed")
```

### `output/eval_results.json`

Raw per-query results for all 4 cells (dense/hybrid × rerank on/off). Each query entry contains:
- Query text and ID
- Top-50 retrieved documents with scores and ranks
- Fusion diagnostics (dense_rank, sparse_rank, fused_rank) for hybrid cells
- Latency measurements
- Ground truth metrics (Coverage@20, Recall@50, alpha-nDCG@10)

**Use case**: Re-analyze results, compute custom metrics, or debug specific queries.

### `output/ground-truth.json`

Query set with:
- 203 FreshStack LangChain test questions (200 identifier-heavy, 3 semantic)
- 20 continuity queries from Experiment 9
- For each query: relevant parent IDs, nugget-level qrels, identifier rule hits

**Use case**: Understand the ground truth structure and reproduce metric calculations.

### `output/freshstack-qrels.json`

Nugget-level relevance judgments in FreshStack format:
- Each query has multiple nuggets (sub-questions)
- Each nugget lists relevant corpus IDs (documents that answer that nugget)

**Use case**: Compare with FreshStack's official evaluation tools or compute alpha-nDCG.

### `corpus/langchain/`

10,009 Markdown files, each containing:
- YAML front matter with `freshstack_id`, `source_url`, `topic`, `source_kind`
- Raw text from FreshStack corpus chunks

Example:
```markdown
---
freshstack_id: langchain/docs/docs/how_to/output_parser_json.md_0_4315
source_url: https://github.com/langchain-ai/langchain/...
topic: langchain
source_kind: freshstack-parent
---

<document text here>
```

**Use case**: Inspect actual document content, verify corpus quality, or re-ingest into other vector stores.

### `corpus/langchain_manifest.jsonl`

JSONL file mapping FreshStack IDs to exported file paths:
```json
{"freshstack_id": "langchain/docs/...", "file_path": "corpus/langchain/00001_abc123.md", ...}
```

**Use case**: Programmatic lookup of which file corresponds to which FreshStack document.

---

## Reproduction from Scratch

To reproduce the experiment without downloading artifacts:

### 1. Prepare corpus (~10 min)

Downloads FreshStack LangChain from HuggingFace and exports as Markdown:

```bash
cd experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30

uv run --with datasets --with pyarrow --with pandas python prepare_freshstack.py \
  --topic langchain \
  --queries-repo freshstack/queries-oct-2024 \
  --corpus-repo freshstack/corpus-oct-2024 \
  --output-dir . \
  --min-parent-docs 10000 \
  --max-parent-docs 10000 \
  --clean
```

**Requires**: ~116 MB disk, HuggingFace account (optional), `datasets` library.

### 2. Build Chroma indexes (~1-2 hours)

Embeds 10,025 documents via Ollama and builds HNSW indexes:

```bash
PYTHONUNBUFFERED=1 caffeinate -dimsu uv run python -u build_indexes.py \
  --experiment-dir . \
  --batch-size 100 \
  --progress-every 10 \
  --force \
  2>&1 | tee output/build_indexes.log
```

**Requires**: Ollama running locally with `qwen3-embedding:0.6b` pulled, ~315 MB disk for dense index.

### 3. Run evaluation (~2-3 hours)

Runs 4 cells × 223 queries with checkpoint/resume:

```bash
PYTHONUNBUFFERED=1 caffeinate -dimsu uv run python -u run_eval.py \
  --experiment-dir . \
  --modes dense-only,hybrid_bm25 \
  --rerank-cross \
  --resume \
  --k-values 5 10 20 50 \
  2>&1 | tee output/run_eval.log
```

**Requires**: Ollama running, reranker model downloads automatically from HuggingFace (~23 MB).

### 4. Summarize results (instant)

```bash
uv run python summarise_eval.py \
  --input output/eval_results.json \
  --output output/eval_results.summary.json \
  --results-md output/results.md
```

---

## Hardware Used

- **CPU**: Apple M1 Pro (10-core)
- **RAM**: 32 GB
- **OS**: macOS 25.5 (Darwin 25.5.0)
- **Embedding**: Ollama local, `qwen3-embedding:0.6b` (639 MB model)
- **Reranker**: ONNX Runtime on CPU, `cross-encoder/ms-marco-MiniLM-L-6-v2` (23 MB)
- **Python**: 3.12
- **ChromaDB**: 1.5.9

---

## Verification

To verify download integrity:

```bash
# After downloading release assets
find output/ -type f -exec sha256sum {} \; > checksums.txt

# Compare with checksums.txt from the release
diff checksums.txt expected_checksums.txt
```

*(Checksums will be generated and uploaded with the release.)*

---

## Notes

- **Why not commit large files to git?** GitHub has a 100 MB per-file limit and recommends keeping repos under 1 GB. The Chroma indexes alone are 625 MB.
- **Why not use Git LFS?** LFS adds complexity and bandwidth costs. For one-off experiment artifacts, GitHub releases are simpler and free.
- **Reproducibility**: All scripts are deterministic. Running reproduction steps on the same hardware should produce identical results (±1% due to floating-point non-determinism in ONNX).
