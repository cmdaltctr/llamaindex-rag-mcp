# Experiment 14: LiteParse Promotion on Harder Corpus (Qasper)

**ID**: `14-liteparse-qasper-promotion-2026-06-29`  
**Date planned**: 2026-06-29  
**Status**: PLANNED  
**Relation**: OpenSpec change `calibrate-rag-retrieval-defaults`; validates ADR-020

---

## Why this experiment exists

Exp 11 tested LiteParse vs pypdf on a 20-paper corpus that was too easy (dense
baseline achieved 100% Hit@5, making reranker comparison impossible). This
experiment re-runs the comparison on Qasper academic PDFs (two-column layout,
harder retrieval) where corpus saturation is unlikely. It completes the
unfilled TODO sections from Exp 11 and validates H3 (reranker benefit) and H2
(speed) under post-ADR-021 optimisations.

## Hypothesis / Research question

1. **H1 (corpus validity)**: Dense-only baseline does NOT achieve 100% Hit@5
   on Qasper — the corpus has headroom for quality comparisons.
2. **H2 (speed)**: Post-ADR-021 LiteParse ingestion + retrieval latency is
   significantly lower than pypdf.
3. **H3 (reranker benefit)**: Reranking helps LiteParse more than pypdf (the
   original H3 from Exp 11 that was inconclusive due to saturation).

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | PDF reader | pypdf, liteparse |
| Independent | Reranker | off, on (post-ADR-021 config) |
| Dependent | Coverage@20, Hit@5, Hit@10, MRR@10 | Quality metrics |
| Dependent | P95 latency, ingestion time | Operational metrics |
| Controlled | Corpus | Qasper dev set (≥ 30 PDFs, ≥ 100 queries) |
| Controlled | Embedding model | `qwen3-embedding:0.6b` |
| Controlled | Reranker model | `cross-encoder/ms-marco-MiniLM-L-6-v2` (ONNX) |
| Controlled | Post-ADR-021 config | `RERANK_FETCH_MULTIPLIER=3`, `RERANK_MAX_FETCH=100` |
| Controlled | `top_k` | 50 |

## Corpus and ground truth

| Item | Value |
| --- | --- |
| Source | Qasper dev set (`allenai/qasper` from HuggingFace) |
| Minimum PDFs | ≥ 30 |
| Minimum queries | ≥ 100 |
| Ground truth | Qasper dev annotations |
| Corpus validity gate | Dense baseline < 100% Hit@5 |

## Experimental design / cell matrix

| Run ID | PDF Reader | Rerank |
| --- | --- | --- |
| `pypdf_off` | pypdf | off |
| `pypdf_on` | pypdf | on |
| `liteparse_off` | liteparse | off |
| `liteparse_on` | liteparse | on |

## Metrics

### Primary metrics

- Coverage@20, Hit@5 (for corpus validity gate)
- Reranker lift (Coverage@20 delta: on minus off) per reader

### Diagnostic metrics

- Hit@10, MRR@10, Recall@50
- P95 latency, ingestion time

## Success criteria / pass gates

| Criterion | Threshold |
| --- | --- |
| Corpus validity | Dense baseline Hit@5 < 100% |
| H3 (reranker × reader) | Reranker lift for LiteParse > reranker lift for pypdf |
| H2 (speed) | LiteParse ingestion time < pypdf ingestion time |
| Non-regression | Liteparse Coverage@20 ≥ pypdf Coverage@20 (within −2pp) |

## Interpretation rules

- If H1 passes and H3 passes: LiteParse benefits more from reranking. Promote
  `PDF_READER=auto` (LiteParse default). Draft ADR-020 amendment.
- If H1 passes but H3 fails: Reranker benefit is reader-independent. LiteParse
  promotion depends only on speed (H2).
- If H1 fails: corpus is still too easy. Need an even harder corpus.
- If LiteParse quality regresses > 2pp: do NOT promote LiteParse default.

## Procedure / reproduction commands

### Step 1: Prepare Qasper PDF corpus

```bash
uv run python experiments/14-liteparse-qasper-promotion-2026-06-29/prepare_qasper_pdfs.py
```

### Step 2: Build indexes (both readers)

```bash
PDF_READER=pypdf uv run python experiments/14-liteparse-qasper-promotion-2026-06-29/build_indexes.py --reader pypdf
PDF_READER=liteparse uv run python experiments/14-liteparse-qasper-promotion-2026-06-29/build_indexes.py --reader liteparse
```

### Step 3: Run evaluation

```bash
PYTHONUNBUFFERED=1 uv run python -u \
  experiments/14-liteparse-qasper-promotion-2026-06-29/run_eval.py \
  --k-values 5 10 20 50 \
  --resume \
  2>&1 | tee experiments/14-liteparse-qasper-promotion-2026-06-29/output/run_eval.log
```

### Step 4: Summarise

```bash
uv run python experiments/14-liteparse-qasper-promotion-2026-06-29/summarise_eval.py
```

## Artefacts expected

| File | Description | Required? |
| --- | --- | :--: |
| `protocol.md` | This plan | ✅ |
| `results.md` | Human-readable report | ✅ |
| `prepare_qasper_pdfs.py` | Qasper PDF export | ✅ |
| `build_indexes.py` | Index builder (both readers) | ✅ |
| `run_eval.py` | Evaluation runner | ✅ |
| `summarise_eval.py` | Results summariser with H3/H2 gates | ✅ |
| `eval_results.json` | Raw results | ✅ |
| `eval_results.summary.json` | Aggregated summary | ✅ |

## References

- Exp 11: `experiments/11-liteparse-pdf-quality-2026-06-20/`
- ADR-020: `docs/adr/020-pdf-reader-factory.md`
- ADR-021: `docs/adr/021-reranker-fetch-reduction-and-speed-optimization.md`
