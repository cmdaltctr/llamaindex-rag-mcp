# Experiment 11: LiteParse PDF Quality and Speed

**ID**: `11-liteparse-pdf-quality-2026-06-20`
**Date planned**: 2026-06-20
**Operator**: Dr Muhammad Aizat Bin Md Hawari (with a-build / a-autonomous agents as needed)
**Status**: PLANNED
**Relation**: OpenSpec change `use-liteparse-as-pdf-reader`; superseded by ADR-020 (pending outcome)

---

## Why this experiment exists

The current PDF ingestion path resolves through `llama-index-readers-file>=0.2.0` to `pypdf` 6.11.0 (confirmed in `uv.lock:2872`), which is the slowest and lowest-quality model-free PDF parser in published benchmarks and discards all layout information. The proposed OpenSpec change `use-liteparse-as-pdf-reader` would replace pypdf with LiteParse v2.0 (Rust + PDFium) as the default PDF parser.

This experiment is the **hard validation gate** (per design.md Decision 6) that determines whether LiteParse actually improves retrieval quality and ingest speed on this project's real corpus. Without it, the adoption decision rests on vendor benchmarks and third-party reports — including a documented two-column reading-order regression that may or may not affect this corpus.

The experiment's PASS/FAIL verdict directly determines:
- Whether `PDF_READER` default flips from `pypdf` to `auto` in a follow-on change
- Whether ADR-020 status is `Accepted` or `Declined`
- Whether the `readers/` factory and LiteParse adapter ship at all

## Hypothesis / Research question

**Primary hypothesis (H1).** With `PDF_READER=liteparse`, mean nDCG@10 across the corpus improves by at least 5% relative to the `PDF_READER=pypdf` baseline, while zero queries move from "found" (in top-K) to "not found".

**Secondary hypothesis (H2).** With `PDF_READER=liteparse`, total ingest wall-clock for the corpus is at most 80% of the pypdf baseline (i.e. ≥20% faster end-to-end ingest including Ollama embeddings).

**Negative control (H3).** The existing reranker (when enabled) continues to improve nDCG@10 over the no-rerank baseline by at least 5% relative on both parser paths. If the reranker stops helping on the LiteParse path, that signals a chunking/text-quality regression worth investigating.

## Background and prior evidence

- **Vendor benchmark** (LlamaIndex blog, "Markdown Comes to LiteParse"): LiteParse leads model-free tools at 0.871 NID (reading order), 0.693 TEDS (tables), 0.816 MHS (headers); 3.16 ms/page vs pymupdf4llm 141.5 ms/page. https://www.llamaindex.ai/blog/markdown-comes-to-liteparse
- **Third-party regression report** (community benchmark, Digg thread): LiteParse v2 merges left/right columns into same lines on some two-column PDFs, worse for LLM/document reading. Worth verifying on academic corpus.
- **Prior experiments**: ADR-019 was informed by Experiments 9a/10; this experiment follows the same discipline. `experiments/EXP_README.md` rows 9a and 10 are precedents for hybrid-retrieval and reranker calibration.
- **Relevant code paths**: `src/rag_mcp/ingestion.py:257` (`SimpleDirectoryReader` call site), `src/rag_mcp/ingestion.py:_read_and_chunk_file_async`, `src/rag_mcp/retrieval.py:search`.
- **OpenSpec change**: `openspec/changes/use-liteparse-as-pdf-reader/proposal.md`.

**Known caveats:**
- The corpus composition is operator-supplied; saturation at 100% Hit@1 is a real risk on small or easy corpora (cf. Experiments 6, 9). Mitigated by including hard cases: two-column papers, table-heavy PDFs, papers with formulae.
- pypdf is a slow baseline; the speed win may be larger than the 20% gate suggests. We record the actual ratio regardless.

## Variables

| Type        | Variable                        | Values / treatment                                       |
| ----------- | ------------------------------- | -------------------------------------------------------- |
| Independent | PDF parser backend              | `pypdf` (baseline), `liteparse` (candidate)              |
| Dependent   | nDCG@10                         | Per-query, then mean across corpus                       |
| Dependent   | Hit@5, Hit@10, Hit@20, MRR@10   | Diagnostic; not gated                                    |
| Dependent   | Total ingest wall-clock         | Per-corpus; recorded once per cell                       |
| Dependent   | Parsing-only wall-clock         | Per-file; recorded during build_indexes.py               |
| Dependent   | Chunk count, mean chunk tokens  | Diagnostic; chunk-size inflation indicates parsing noise |
| Controlled  | Corpus                          | Fixed across cells (same PDFs in both indexes)           |
| Controlled  | Embedding model                 | `qwen3:embedding-0.6b` via Ollama (per ADR-009)          |
| Controlled  | Chunking                        | `SentenceSplitter(chunk_size=1024, chunk_overlap=100)`   |
| Controlled  | Reranker                        | Crossed (see cell matrix)                                |
| Controlled  | Top-K                           | max(k_values) = 50 per query                             |

**Explicitly not changed:** chunk size, chunk overlap, embedding model, hybrid retrieval setting (off — isolates the parser variable), metadata extraction, reranker model.

## Corpus and ground truth

| Item               | Value                                                                                              |
| ------------------ | -------------------------------------------------------------------------------------------------- |
| Source             | Operator-supplied academic PDFs (see `corpus/README.md` for suggested mix)                         |
| Local path         | `experiments/11-liteparse-pdf-quality-2026-06-20/corpus/`                                          |
| Size               | ≥20 PDFs, ≥100 pages total (target ~150–200 pages to avoid saturation)                             |
| Ground truth path  | `experiments/11-liteparse-pdf-quality-2026-06-20/ground_truth.json`                                |
| Evidence density   | Target 100% (every query has at least one known-good source file)                                  |
| Symlinks?          | No. PDFs copied into `corpus/` directly.                                                           |

**Corpus composition requirement:**
- ≥12 two-column academic papers (NeurIPS / ICML / ACL / CVPR style). These exercise LiteParse's column-aware reading order — the make-or-break feature.
- ≥5 single-column papers (arXiv preprint style). Sanity check that LiteParse does not regress on easy layouts.
- ≥3 table-heavy PDFs (surveys, financial reports, systematic reviews). Exercise LiteParse's grid projection.
- Optional: 1–2 scanned PDFs (image-only). Exercise LiteParse's Tesseract OCR path. If OCR is unavailable, exclude from corpus and note in results.

## Environment and prerequisites

| Requirement         | Version / value                                                |
| ------------------- | -------------------------------------------------------------- |
| Python              | 3.12 (per `pyproject.toml`)                                    |
| Package manager     | `uv`                                                           |
| Embedding model     | `qwen3:embedding-0.6b` via Ollama                              |
| Reranker            | `cross-encoder/ms-marco-MiniLM-L-6-v2` via ONNX Runtime        |
| LiteParse           | v2.0+ via `uv sync --extra pdf-liteparse`                      |
| Hardware            | macOS arm64 (M-series) preferred; record actual machine class  |
| Key config          | `OLLAMA_BASE_URL`, `CHROMA_PERSIST_DIR` (per cell)             |

```bash
# Sanity checks before running
uv sync --extra pdf-liteparse
ollama list | grep qwen3
python -c "from liteparse import LiteParse; LiteParse().parse('corpus/.smoke.pdf')"  # if a smoke PDF exists
```

## Experimental design / cell matrix

Four cells, fully crossed on parser × reranker:

| Run ID         | Purpose                          | Parser    | Reranker | ChromaDB dir                  | Expected interpretation                       |
| -------------- | -------------------------------- | --------- | -------- | ----------------------------- | --------------------------------------------- |
| `pypdf_nr`     | Baseline, no reranker            | pypdf     | off      | `output/chroma_pypdf`         | Quality floor with current parser             |
| `pypdf_r`      | Baseline, with reranker          | pypdf     | on       | `output/chroma_pypdf`         | Current production behaviour (per ADR-019)    |
| `liteparse_nr` | Candidate, no reranker           | liteparse | off      | `output/chroma_liteparse`     | Pure parser-quality comparison                |
| `liteparse_r`  | Candidate, with reranker         | liteparse | on       | `output/chroma_liteparse`     | Whether reranker still helps on LiteParse text |

**Phase 1 stop rule:** Run all four cells. If LiteParse cell crashes on >25% of corpus, abort and document — the parser is not production-ready for this corpus shape.

**Phase 2 stop rule:** If H1 (nDCG@10 +5%) passes but H3 (reranker still helps) fails on the LiteParse path, mark INCONCLUSIVE and document. Do not promote LiteParse to `auto` default without understanding why the reranker stopped helping.

**Escalation rule:** If results are confounded by corpus saturation (Hit@10 = 100% on all cells), assemble a harder corpus (e.g. FreshStack, Qasper — cf. Experiments 7a, 9a) before promoting LiteParse.

## Metrics

### Primary metrics
- **nDCG@10**: graded relevance based on whether the retrieved chunk's source file matches `expected_files` for the query, weighted by chunk rank. The H1 pass gate is on this metric.
- **Total ingest wall-clock**: seconds from `build_indexes.py` start to finish, per parser. The H2 pass gate is on this metric.

### Diagnostic metrics (reported, not gated)
- Hit@5, Hit@10, Hit@20, Hit@50
- MRR@10
- Parsing-only wall-clock (per-file, per-page averages)
- Mean / P95 retrieval latency
- Chunk count per file, mean estimated tokens per chunk
- bm25/dense score distributions (if hybrid enabled in future follow-up)
- Per-category breakdown (two-column vs single-column vs table-heavy)

## Procedure / reproduction commands

### Step 1: Prepare data

```bash
# Operator populates corpus/ per corpus/README.md
# Operator expands ground_truth.json from stub to ≥25 queries
ls experiments/11-liteparse-pdf-quality-2026-06-20/corpus/*.pdf | wc -l  # expect ≥20
```

### Step 2: Build indexes

```bash
# Build pypdf baseline index
CHROMA_PERSIST_DIR=./experiments/11-liteparse-pdf-quality-2026-06-20/output/chroma_pypdf \
  PDF_READER=pypdf \
  PYTHONUNBUFFERED=1 \
  uv run python -u experiments/11-liteparse-pdf-quality-2026-06-20/build_indexes.py \
  --parser pypdf \
  2>&1 | tee experiments/11-liteparse-pdf-quality-2026-06-20/output/build_pypdf.log

# Build liteparse candidate index
CHROMA_PERSIST_DIR=./experiments/11-liteparse-pdf-quality-2026-06-20/output/chroma_liteparse \
  PDF_READER=liteparse \
  PYTHONUNBUFFERED=1 \
  uv run python -u experiments/11-liteparse-pdf-quality-2026-06-20/build_indexes.py \
  --parser liteparse \
  2>&1 | tee experiments/11-liteparse-pdf-quality-2026-06-20/output/build_liteparse.log
```

`build_indexes.py` records per-file parsing wall-clock into `output/build_<parser>_timing.json` for H2.

### Step 3: Run evaluation

```bash
PYTHONUNBUFFERED=1 uv run python -u \
  experiments/11-liteparse-pdf-quality-2026-06-20/run_eval.py \
  --modes pypdf,liteparse \
  --rerank-cross \
  --resume \
  --k-values 5 10 20 50 \
  2>&1 | tee experiments/11-liteparse-pdf-quality-2026-06-20/output/run_eval.log
```

The runner writes `eval_results_checkpoint.json` after each cell. If interrupted, re-run with `--resume`.

### Step 4: Summarise raw results

```bash
uv run python experiments/11-liteparse-pdf-quality-2026-06-20/summarise_eval.py
# Writes output/eval_results.summary.json and results.md
```

## Success criteria / pass gates

Pre-registered before the experiment runs (per `/s-experiment` discipline).

| Criterion                                       | Threshold                                                  | Why this threshold matters                                                |
| ------------------------------------------------ | ---------------------------------------------------------- | ------------------------------------------------------------------------- |
| **H1 — Quality win**                             | `nDCG@10(liteparse_nr) ≥ nDCG@10(pypdf_nr) × 1.05`         | Justifies swapping the default parser; 5% is a conservative minimum lift. |
| **H2 — Speed win**                               | `ingest_wallclock(liteparse) ≤ ingest_wallclock(pypdf) × 0.80` | At 100+ docs, parsing speed compounds; <20% saving is not worth the dep.  |
| **H3 — Reranker still helps (negative control)** | `nDCG@10(liteparse_r) ≥ nDCG@10(liteparse_nr) × 1.05`      | If reranker stops helping, LiteParse text may have a hidden regression.   |
| **H4 — No catastrophic regression**              | `0 queries` move from "found" (in top-20) to "not found"   | Protects against LiteParse silently dropping content from specific PDFs.  |

**All four gates must pass** for an overall PASS verdict. Any single failure → FAIL (or INCONCLUSIVE if H3 alone fails).

## Interpretation rules

- **If H1 + H2 + H3 + H4 all pass:** Status = PASS. ADR-020 status = Accepted. Follow-on change flips `PDF_READER` default from `pypdf` to `auto`.
- **If H1 passes but H2 fails:** Status = PARTIAL. LiteParse is a quality win but not a speed win. Decision: adopt LiteParse as `auto` default (quality > speed); record H2 failure in ADR-020 consequences.
- **If H1 fails:** Status = FAIL. ADR-020 status = Declined. Retain pypdf as default; keep the factory architecture for future use (pypdfium2, spdf).
- **If H3 fails alone:** Status = INCONCLUSIVE. Investigate why reranker stopped helping on LiteParse text. Possible causes: chunk-boundary changes, column-merge artefacts, header/footer noise not stripped. Document and decide.
- **If H4 fails (any query lost):** Status = FAIL. LiteParse is silently dropping content. Do not adopt regardless of other metrics. Investigate which PDFs lost content.
- **If corpus saturates (all cells at Hit@10 = 100%):** Status = INCONCLUSIVE. Assemble harder corpus before deciding.

## What to do if the experiment fails

1. **Document the negative result honestly** in `results.md` and ADR-020. Do not promote LiteParse.
2. **Consider pypdfium2 as a smaller upgrade** (separate OpenSpec change). Same PDFium engine, no Rust build, no bbox, but still faster than pypdf. Lower risk, smaller win.
3. **Watch `spdf` maturity.** If `spdf` (the MIT-licensed Rust clone) stabilises, re-run Experiment 11 with `spdf` as the candidate.
4. **Investigate the specific failure mode.** If LiteParse failed on two-column papers specifically, that confirms the third-party regression report and rules out LiteParse for academic corpora until fixed upstream.

## Implementation notes

- **Code path under test:** `src/rag_mcp/ingestion.py:_read_and_chunk_file_async` (current); for the liteparse cell, `build_indexes.py` calls `liteparse.LiteParse().parse()` directly and constructs LlamaIndex `Document` objects manually — this bypasses the not-yet-existing adapter but exercises the same chunking and embedding pipeline.
- **Flags/env vars used:** `PDF_READER=pypdf|liteparse`, `CHROMA_PERSIST_DIR=<per-cell>`, `RERANK_ENABLED=true|false`, `HYBRID_ENABLED=false` (hybrid off to isolate the parser variable).
- **Monkey patches / test-only hooks:** None. `build_indexes.py` writes to isolated ChromaDB dirs; production data untouched.
- **Scope boundaries:** PDF parsing only. docx/pptx/image paths not exercised. Hybrid retrieval off. Metadata extraction runs normally.
- **Known risks:**
  - Corpus saturation (mitigated by including hard cases).
  - LiteParse native build failure on the operator's machine (mitigated by `uv sync --extra pdf-liteparse` smoke check in Step 1).
  - Ground-truth subjectivity (mitigated by writing queries before running, per `/s-experiment`).

## Cleanup

```bash
# Keep raw results, summaries, and logs.
# Remove large ChromaDB indexes if disk-constrained (they are reproducible from corpus/).
rm -rf experiments/11-liteparse-pdf-quality-2026-06-20/output/chroma_pypdf
rm -rf experiments/11-liteparse-pdf-quality-2026-06-20/output/chroma_liteparse
# Keep: eval_results.json, eval_results.summary.json, results.md, *.log, build_*_timing.json
```

## Artefacts expected

| File / directory                          | Description                                     | Required? |
| ----------------------------------------- | ----------------------------------------------- | :-------: |
| `protocol.md`                             | This plan                                       |     ✅     |
| `results.md`                              | Human-readable result report                    |     ✅     |
| `run_eval.py`                             | Evaluation runner (cell matrix)                 |     ✅     |
| `build_indexes.py`                        | Index builder for both parser cells             |     ✅     |
| `summarise_eval.py`                       | Aggregator and pass-gate evaluator              |     ✅     |
| `eval_results.json`                       | Raw machine-readable results                    |     ✅     |
| `eval_results_checkpoint.json`            | Cell-by-cell checkpoint for resume              |     ✅     |
| `eval_results.summary.json`               | Aggregated summary with pass-gate verdict       |     ✅     |
| `output/build_pypdf_timing.json`          | Per-file parsing wall-clock (pypdf)             |     ✅     |
| `output/build_liteparse_timing.json`      | Per-file parsing wall-clock (liteparse)         |     ✅     |
| `output/run_eval.log`                     | Run log                                          |    Optional |
| `output/build_pypdf.log`, `build_liteparse.log` | Build logs                                  |    Optional |
| `ground_truth.json`                       | Pre-written queries with expected sources       |     ✅     |
| `corpus/`                                 | Local test PDFs                                 |     ✅     |
| `corpus/MANIFEST.md`                      | PDF source URLs and licences (if not committed) |    Optional |

## References

- OpenSpec change: `openspec/changes/use-liteparse-as-pdf-reader/proposal.md`
- Skill: `.opencode/skills/s-experiment/SKILL.md`
- Eval runner pattern: `.opencode/skills/s-experiment/references/eval-runner-pattern.md`
- Summarise pattern: `.opencode/skills/s-experiment/references/summarise-pattern.md`
- LlamaIndex blog (LiteParse benchmarks): https://www.llamaindex.ai/blog/markdown-comes-to-liteparse
- LiteParse repo: https://github.com/run-llama/liteparse
- Prior experiment precedents: Experiments 9a (`experiments/9a-hybrid-retrieval-freshstack-langchain-2026-05-30/`) and 10 (`experiments/10-reranker-technical-workload-calibration-2026-05-31/`)
