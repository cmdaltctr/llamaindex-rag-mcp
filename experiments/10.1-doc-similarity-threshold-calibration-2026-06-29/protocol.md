# Experiment 10.1: DOC_SIMILARITY_THRESHOLD Calibration

**ID**: `10.1-doc-similarity-threshold-calibration-2026-06-29`  
**Date planned**: 2026-06-29  
**Status**: PLANNED  
**Relation**: OpenSpec change `calibrate-rag-retrieval-defaults`; informs ADR-023

---

## Why this experiment exists

The `DOC_SIMILARITY_THRESHOLD` default (0.85) was set as a placeholder when
`doc_graph.py` was first written. ADR-023 notes it "needs experiment calibration
with qwen3-embedding:0.6b." No experiment has been run to validate this value.
This experiment sweeps thresholds {0.70, 0.75, 0.80, 0.85, 0.90} to find the
value that maximises graph modularity while keeping the false-positive rate
below 20%.

## Hypothesis / Research question

1. **H1 (optimal threshold)**: The threshold that maximises modularity is not
   0.85 — it is lower (0.75 or 0.80), because qwen3-embedding:0.6b produces
   lower absolute similarity scores for semantically related content.
2. **H2 (false-positive rate)**: At the modularity-optimal threshold, the
   false-positive rate (edges rated as "noise" by manual inspection) is below
   20%.
3. **H3 (current default acceptability)**: The current default (0.85) is within
   the acceptable range (FP < 20%, modularity within 10% of optimal).

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | `DOC_SIMILARITY_THRESHOLD` | 0.70, 0.75, 0.80, 0.85, 0.90 |
| Dependent | Edge count | Total similarity edges in graph |
| Dependent | Cluster count | Number of Louvain communities |
| Dependent | Mean cluster size | Average community size |
| Dependent | Modularity | Louvain modularity score |
| Dependent | False-positive rate | Manual rating of 10 random edges per threshold |
| Controlled | Corpus | This repo's codebase + docs (≥ 50 documents) |
| Controlled | Embedding model | `qwen3-embedding:0.6b` |

## Corpus and ground truth

| Item | Value |
| --- | --- |
| Source | This repo's own codebase + documentation |
| Code files | ≥ 30 Python/TypeScript files from `src/rag_mcp/` |
| Doc files | ≥ 20 Markdown files from `docs/` |
| Requirement | ≥ 50 documents with pairwise similarity above 0.70 |
| Ground truth | Manual ratings of 10 random edges per threshold |

## Environment and prerequisites

| Requirement | Version / value |
| --- | --- |
| Python | 3.12 |
| Package manager | `uv` |
| Embedding model | `qwen3-embedding:0.6b` via Ollama |
| Key dependency | `networkx` (Louvain community detection) |

## Experimental design / cell matrix

| Run ID | Threshold | Expected effect |
| --- | ---: | --- |
| `thresh_070` | 0.70 | Most edges, most noise |
| `thresh_075` | 0.75 | Many edges, moderate noise |
| `thresh_080` | 0.80 | Moderate edges, low noise |
| `thresh_085` | 0.85 | Current default — baseline |
| `thresh_090` | 0.90 | Fewest edges, least noise |

## Metrics

### Primary metrics

- Modularity score (Louvain)
- False-positive rate (manual edge rating)

### Diagnostic metrics

- Edge count, cluster count, mean cluster size

## Procedure / reproduction commands

### Step 1: Build mixed corpus

```bash
uv run python experiments/10.1-doc-similarity-threshold-calibration-2026-06-29/build_corpus.py
```

### Step 2: Run threshold sweep

```bash
uv run python experiments/10.1-doc-similarity-threshold-calibration-2026-06-29/run_eval.py
```

### Step 3: Manual edge rating

Manually rate 10 random edges per threshold in `output/manual_ratings.json`.

### Step 4: Summarise

```bash
uv run python experiments/10.1-doc-similarity-threshold-calibration-2026-06-29/summarise_eval.py
```

## Success criteria / pass gates

| Criterion | Threshold |
| --- | --- |
| Modularity maximised | Identify threshold with highest modularity |
| False-positive rate | < 20% at the recommended threshold |
| Current default acceptability | 0.85 within 10% of optimal modularity AND FP < 20% |

## Interpretation rules

- If H1 passes (optimal ≠ 0.85): recommend changing `DOC_SIMILARITY_THRESHOLD`
  to the modularity-optimal value. Draft ADR-023 amendment.
- If H1 fails (optimal = 0.85): current default validated. No change.
- If H2 fails (FP ≥ 20% at optimal): threshold is too aggressive. Recommend
  the highest threshold with FP < 20%.
- If H3 passes: 0.85 is acceptable. No change needed.

## Artefacts expected

| File | Description | Required? |
| --- | --- | :--: |
| `protocol.md` | This plan | ✅ |
| `build_corpus.py` | Builds mixed corpus from repo files | ✅ |
| `run_eval.py` | Threshold sweep runner | ✅ |
| `summarise_eval.py` | Results summariser | ✅ |
| `results.md` | Human-readable report | ✅ |
| `manual_ratings.json` | Manual edge ratings | ✅ |

## References

- ADR-023: `docs/adr/023-document-graph-edges-and-community-detection.md`
- Code: `rag_mcp.doc_graph.build_document_graph(threshold=...)`
- Config: `DOC_SIMILARITY_THRESHOLD` in `config.py`
