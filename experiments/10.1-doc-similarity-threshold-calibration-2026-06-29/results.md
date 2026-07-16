# Experiment 10.1: DOC_SIMILARITY_THRESHOLD Calibration

**ID**: `10.1-doc-similarity-threshold-calibration-2026-06-29`
**Date run**: 2026-07-16
**Status**: PASS — current default (0.85) validated
**Relation**: OpenSpec change `calibrate-rag-retrieval-defaults`; informs ADR-023
**Operator**: a-build-agent

---

## Executive summary

The current `DOC_SIMILARITY_THRESHOLD=0.85` is **validated as acceptable**. No change recommended.

The sweep across {0.70, 0.75, 0.80, 0.85, 0.90} revealed that similarity edges are a tiny fraction of the total document graph (47 of 1,968 edges at threshold 0.70 — just 2.4%). The graph is overwhelmingly dominated by structural edges (shared metadata categories, keyword overlaps, heading hierarchies). As a result, the threshold has a negligible effect on modularity (range: 0.1875–0.1947, a delta of 0.0072).

The false-positive rate at 0.85 is **0%** (0 of 5 sampled edges were noise). Lowering the threshold to 0.75 would increase similarity edges from 5 to 24 but introduce a 10% false-positive rate. At 0.70, the FP rate hits the 20% gate exactly.

At 0.90, `qwen3-embedding:0.6b` produces **zero** document pairs above the threshold — the threshold is too high for this model's output distribution.

---

## Hypothesis evaluation

### H1 (optimal threshold ≠ 0.85)

**FAIL.** The modularity-optimal threshold is 0.90, but this is an artefact: at 0.90 there are zero similarity edges, so the graph has no noise to penalise modularity. This is not a meaningful optimum — it's the absence of the feature. Among thresholds that actually produce similarity edges, modularity increases monotonically from 0.70 (0.1875) to 0.85 (0.1939), with diminishing returns. The hypothesis that qwen3-embedding:0.6b produces lower absolute scores (requiring a lower threshold) is not supported — the current 0.85 already produces meaningful edges.

### H2 (FP rate < 20% at modularity-optimal threshold)

**PASS (at 0.85).** The FP rate at 0.85 is 0%. At 0.75 and 0.80, FP is 10%. At 0.70, FP is exactly 20% (borderline). The pass gate (< 20%) is met at all thresholds except 0.70 (which is at the boundary).

### H3 (current default 0.85 is acceptable)

**PASS.** The current default (0.85) has:
- Modularity 0.1939 — within 0.4% of the best productive threshold (0.1947 at 0.90, which is degenerate)
- FP rate 0.0% — well below the 20% gate
- 5 similarity edges — enough to connect genuinely related document pairs

---

## Per-threshold metrics

| Threshold | Sim Edges | Total Edges | Clusters | Mean Cluster Size | Modularity | FP Rate | Rated Edges |
| --------: | --------: | ----------: | -------: | ----------------: | ---------: | ------: | ----------: |
|      0.70 |        47 |       1,968 |        2 |              40.0 |     0.1875 |  20.0%  |        10   |
|      0.75 |        24 |       1,945 |        2 |              40.0 |     0.1908 |  10.0%  |        10   |
|      0.80 |        11 |       1,932 |        2 |              40.0 |     0.1928 |  10.0%  |        10   |
|      0.85 |         5 |       1,926 |        2 |              40.0 |     0.1939 |   0.0%  |         5   |
|      0.90 |         0 |       1,921 |        2 |              40.0 |     0.1947 |    N/A  |         0   |

**Notes:**
- Similarity edges as % of total edges: 2.4% (0.70), 1.2% (0.75), 0.6% (0.80), 0.3% (0.85), 0% (0.90)
- Cluster count is constant (2) across all thresholds — Louvain finds the same code/docs split regardless
- Mean cluster size is constant (40.0) — the two communities are always ~equal in size

---

## Pass gate evaluation

| Criterion                                         | Result  | Detail                                                        |
| ------------------------------------------------- | ------- | ------------------------------------------------------------- |
| FP rate < 20% at recommended threshold (0.85)     | **PASS** | 0.0% (0 of 5 edges rated as noise)                           |
| Modularity within 10% of optimal (productive)     | **PASS** | 0.1939 / 0.1947 = 99.6% (or vs 0.1939 at 0.85 = best productive) |
| 0.85 produces non-trivial similarity edges         | **PASS** | 5 edges connecting genuinely related code↔doc pairs          |

---

## Key findings

### 1. Similarity edges are a minor graph component

The document graph's structure is overwhelmingly driven by metadata edges (shared categories, keywords, headings), not embedding similarity. Even at the most permissive threshold (0.70), similarity edges are only 2.4% of total edges. This means the `DOC_SIMILARITY_THRESHOLD` parameter has limited leverage over graph quality — the structural edges dominate modularity.

### 2. All false positives involve `__init__.py`

Every noise edge in the manual rating involved `src/rag_mcp/__init__.py` paired with a broad documentation file (README.md, ADR-002, providers.md). The `__init__.py` file is thin (imports and re-exports), so its embedding captures generic project vocabulary that overlaps with many documents. This is a known artefact of embedding short, generic files — not a threshold calibration issue.

### 3. 0.90 is degenerate for qwen3-embedding:0.6b

At threshold 0.90, zero document pairs exceed the cutoff. This confirms that `qwen3-embedding:0.6b` produces conservative (lower) cosine similarity scores. Any threshold above 0.85 risks disabling the similarity feature entirely.

### 4. The code/docs community split is robust

Louvain consistently finds 2 communities across all thresholds — one containing code files, one containing documentation. This split is driven by metadata (category=code vs category=documentation), not by similarity edges. The similarity feature adds cross-community connections (code↔doc pairs) but doesn't change the community structure.

---

## Recommendation

**No change to `DOC_SIMILARITY_THRESHOLD`.** The current default of 0.85 is validated:
- FP rate is 0% (best of all productive thresholds)
- Modularity is within 0.4% of the degenerate optimum
- 5 similarity edges connect genuinely related code↔doc pairs

No ADR-023 amendment is warranted.

---

## Corpus

| Item         | Value                                                        |
| ------------ | ----------------------------------------------------------- |
| Source       | This repo's own codebase + documentation                    |
| Code files   | 21 Python files from `src/rag_mcp/`                         |
| Doc files    | 59 Markdown files from `docs/`, `README.md`, `AGENTS.md`    |
| Total        | 80 documents                                                |
| Embeddings   | `qwen3-embedding:0.6b` via Ollama (Q8_0, 1024 dimensions)   |
| Build time   | 137 seconds                                                 |

**Note:** Code file count (21) is below the protocol's ≥ 30 target. This is because `src/rag_mcp/` has 21 `.py` files total. The corpus is still valid — 80 documents exceeds the ≥ 50 requirement.

---

## Reproduction

```bash
# Step 1: Build corpus (embeds repo files via Ollama)
LOCAL_BACKEND=ollama uv run python experiments/10.1-doc-similarity-threshold-calibration-2026-06-29/build_corpus.py --force

# Step 2: Run threshold sweep
LOCAL_BACKEND=ollama uv run python experiments/10.1-doc-similarity-threshold-calibration-2026-06-29/run_eval.py

# Step 3: Rate edges in output/manual_ratings.json

# Step 4: Summarise
LOCAL_BACKEND=ollama uv run python experiments/10.1-doc-similarity-threshold-calibration-2026-06-29/summarise_eval.py
```

**Note:** `LOCAL_BACKEND=ollama` is required because `config.py` defaults to `llamacpp` which requires a separate `LLAMACPP_EMBED_MODEL` env var. Since the corpus is already embedded via Ollama, this only affects the import-time provider initialisation.

---

## Artefacts

| File                          | Location          | Description                                    |
| ----------------------------- | ----------------- | --------------------------------------------- |
| `protocol.md`                 | experiment root   | Experiment plan                               |
| `build_corpus.py`             | experiment root   | Corpus builder (embeds repo files via Ollama) |
| `run_eval.py`                 | experiment root   | Threshold sweep runner                        |
| `summarise_eval.py`           | experiment root   | Results summariser                            |
| `results.md`                  | experiment root   | This report                                   |
| `output/eval_results.json`    | output/ (gitignored) | Raw metrics per threshold                  |
| `output/eval_results.summary.json` | output/ (gitignored) | Summary + pass gates                   |
| `output/manual_ratings.json`  | output/ (gitignored) | Manual edge ratings (35 edges)             |
| `output/chroma_mixed/`        | output/ (gitignored) | ChromaDB index with 80 embedded documents  |

---

## References

- ADR-023: `docs/adr/023-document-graph-via-embedding-similarity.md`
- Code: `rag_mcp.doc_graph.build_document_graph(threshold=...)`
- Config: `DOC_SIMILARITY_THRESHOLD` in `config.py`
