# Experiment 14: LiteParse Promotion on Harder Corpus (Qasper)

**ID**: `14-liteparse-qasper-promotion-2026-06-29`  
**Date planned**: 2026-06-29  
**Status**: REPAIRED build path (v2.0, Stage 4 task 4.3.6) — real immutable PDF bytes, parser-before-embeddings preflight, per-parser artefact/index identity; THREE-PARSER extension (v2.1, 2026-08-23) — pdf-inspector added as a third reader arm (see the final section)
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
   significantly lower than pypdf. (v2.1: H2 spans all three readers —
   pdf-inspector is reported against both existing readers with no
   pre-registered direction; the LiteParse-vs-pypdf contrast stays the
   pre-registered primary.)
3. **H3 (reranker benefit)**: Reranking helps LiteParse more than pypdf (the
   original H3 from Exp 11 that was inconclusive due to saturation). (v2.1:
   reranker lift is computed per reader for all three readers; the
   LiteParse-vs-pypdf contrast stays the pre-registered primary.)

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | PDF reader | pypdf, liteparse, pdf_inspector (pdf-inspector added v2.1, 2026-08-23; plan level uses the module name `pdf_inspector`) |
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
| `pdf_inspector_off` | pdf_inspector | off |
| `pdf_inspector_on` | pdf_inspector | on |

Cell ids match `plan.json`. The `pdf_inspector_*` rows were added in the
v2.1 extension (2026-08-23); the matrix grew from four to six evaluation
cells, and the build stage gained a third build cell (`build_pdf_inspector`)
mirroring `build_pypdf`/`build_liteparse`.

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

The pre-registered gates above are the v1/v2.0 LiteParse-vs-pypdf contrasts.
v2.1: pdf-inspector cells are measured with the same metrics and timing
decomposition, but no directional promotion gate was pre-registered for
pdf-inspector; any default change it motivates is decided at Gate 6C after
the result commit.

## Interpretation rules

- If H1 passes and H3 passes: LiteParse benefits more from reranking. Promote
  `PDF_READER=auto` (LiteParse default). Draft ADR-020 amendment.
- If H1 passes but H3 fails: Reranker benefit is reader-independent. LiteParse
  promotion depends only on speed (H2).
- If H1 fails: corpus is still too easy. Need an even harder corpus.
- If LiteParse quality regresses > 2pp: do NOT promote LiteParse default.
- v2.1: if pdf-inspector beats both readers on quality or speed, the same
  rule as LiteParse promotion applies — evidence first, then the ADR-020
  decision at Gate 6C **after** the result commit.

## Procedure / reproduction commands

### Step 1: Prepare Qasper PDF corpus

```bash
uv run python experiments/14-liteparse-qasper-promotion-2026-06-29/prepare_qasper_pdfs.py
```

### Step 2: Build indexes (all three readers)

```bash
PDF_READER=pypdf uv run python experiments/14-liteparse-qasper-promotion-2026-06-29/build_indexes.py --reader pypdf
PDF_READER=liteparse uv run python experiments/14-liteparse-qasper-promotion-2026-06-29/build_indexes.py --reader liteparse
PDF_READER=pdf_inspector uv run python experiments/14-liteparse-qasper-promotion-2026-06-29/build_indexes.py --reader pdf_inspector
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
| `build_indexes.py` | Index builder (all three readers) | ✅ |
| `run_eval.py` | Evaluation runner | ✅ |
| `summarise_eval.py` | Results summariser with H3/H2 gates | ✅ |
| `eval_results.json` | Raw results | ✅ |
| `eval_results.summary.json` | Aggregated summary | ✅ |

## References

- Exp 11: `experiments/11-liteparse-pdf-quality-2026-06-20/`
- ADR-020: `docs/adr/020-pdf-reader-factory.md`
- ADR-021: `docs/adr/021-reranker-fetch-reduction-and-speed-optimization.md`

---

## Build path repair (v2.0, 2026-08-19 — Stage 4 task 4.3.6, design D19)

The v1 build path was defective: it globed `*.md` from `qasper_pdfs/`
(prepare_qasper_pdfs.py exports Markdown, never PDFs), so the `--reader`
flag only renamed the output directory and stamped metadata — the PDF
reader factor never touched the indexed text and the parser A/B was
fictional. The sections above are historical record; where they describe
Markdown ingestion they are superseded by this section.

### What changed

- **Real PDF bytes**: `build_indexes.py` now globs
  `sorted(corpus_dir.glob("*.pdf"))` and parses through the production
  factory `get_pdf_reader(reader)` (ADR-020; no harness-side parser
  imports). Corpus identity = sha256 over the concatenation of sorted
  per-file hashes; corpus files are immutable inputs.
- **Parse stage before embeddings**: every file records a chronological
  `parse_start`/`parse_end` event pair (plus `parse_error` on failure —
  a parse failure does not abort the build). Before the embed stage,
  `experiments/_lib/preflight.py::assert_parser_invoked_before_embeddings`
  runs on that event log and the build aborts on failure (PreflightError
  propagates).
- **Per-parser artefact identity**: the parsed texts are written to
  `output/parsed_<reader>.json` (atomic `.tmp`→rename) whose
  `artefact_sha256` is the sha256 of the JSON-serialised parsed
  documents — distinct parsers producing different text MUST yield
  distinct artefact identities.
- **Timing decomposition (D19)**: `index_build_<reader>.json` records
  `parse_time_s_total` and `embed_write_time_s` separately, so a faster
  parser cannot hide behind the dominant embedding stage.
  `ingestion_time_s` (their sum) is retained for the v1 summariser's H2
  gate.
- **Index identity**: each parser gets its own index via
  `experiment_storage_config(experiment_id="exp14", corpus="qasper",
  parser=<reader>, ...)`; stored metadata now includes `source_sha256`
  per document.

### New flags

- `--corpus-dir <dir>` (default `qasper_pdfs/`): directory of immutable
  PDF inputs. The agreement tests pass `fixtures/`.
- `--skip-embed`: write the parsed artefact plus the preflight runtime
  manifest only — no Ollama, no Chroma store. Used by agreement tests
  and dry runs.

### Immutable fixtures

`fixtures/doc1_climate.pdf` and `fixtures/doc2_quantum.pdf` were copied
byte-identical from `tests/fixtures/pdf_dir/` (identity = sha256; never
mutated — see `fixtures/README.md`). The fast harness tests parse them
with pypdf only (deterministic per AGENTS.md gotcha 6) and never touch
Ollama.

### Machine-readable plan (D15)

`plan.json` is the machine truth for the cell matrix: two build cells
(`build_pypdf`, `build_liteparse`) plus the four evaluation cells
(`{pypdf,liteparse}_x_{off,on}`). Agreement tests compare
`build_indexes.build_cell_matrix()` and `run_eval.build_eval_cell_matrix()`
against it via `ExperimentPlan.assert_runner_cells`. (Extended 2026-08-23 to
three build cells and six evaluation cells — see "Three-parser extension
(v2.1)" below.)

### Reproduction (v2.0)

```bash
# Dry run (no Ollama, no store): parse artefact + preflight manifest
uv run python experiments/14-liteparse-qasper-promotion-2026-06-29/build_indexes.py \
  --reader pypdf --corpus-dir experiments/14-liteparse-qasper-promotion-2026-06-29/fixtures --skip-embed

# Full builds (one per parser; real corpus)
uv run python experiments/14-liteparse-qasper-promotion-2026-06-29/build_indexes.py --reader pypdf
uv run python experiments/14-liteparse-qasper-promotion-2026-06-29/build_indexes.py --reader liteparse
uv run python experiments/14-liteparse-qasper-promotion-2026-06-29/build_indexes.py --reader pdf_inspector
```

---

## Three-parser extension (v2.1, 2026-08-23 — user-ratified design change)

On 2026-08-23 the user ratified adding **pdf-inspector** as a third PDF
reader arm, turning the parser A/B into an A/B/C. pdf-inspector is
Firecrawl's Rust PDF classification and text/markdown-extraction library
(MIT licence; PyPI distribution `pdf-inspector`; Python module
`pdf_inspector`; Python bindings via PyO3). It converts PDF bytes to
structured markdown with multi-column reading order, headings and tables —
directly comparable to the pypdf and liteparse outputs on the two-column
Qasper corpus.

### What changed

- **Reader factor gains a third level**: `pdf_inspector` in `plan.json`
  (module name; the distribution is hyphenated). Prose keeps the
  pdf-inspector name.
- **Cell matrix grows 4 → 6 evaluation cells**: `pdf_inspector_off` and
  `pdf_inspector_on` join the existing four, mirroring their shape. A third
  build cell `build_pdf_inspector` mirrors `build_pypdf`/`build_liteparse`.
- **Hypotheses span three readers**: H2 and H3 keep the pre-registered
  LiteParse-vs-pypdf primary contrasts; pdf-inspector is reported against
  both with no pre-registered direction (see Hypothesis section and the
  Success criteria note).
- **Preflight expected effective readers** in `plan.json` gain
  `pdf_inspector` — the no-fallback assertion applies to the third reader
  exactly as to the first two.
- **Adapter and corpus tooling are separate code changes**: the reader
  adapter under the production factory and the real-PDF corpus download
  script land outside this document amendment. Harness agreement tests
  compare runner cell generators against `plan.json`, so the runners gain
  the `pdf_inspector` cells with the adapter, preserving the failing-first
  discipline.

### What did not change

- Corpus and ground-truth requirements (immutable real PDF bytes, Qasper
  dev set, ≥ 30 PDFs, ≥ 100 queries) apply identically to all three readers.
- The D19 build-path mechanisms are reader-agnostic and unchanged: parse
  before embeddings, `assert_parser_invoked_before_embeddings`, per-parser
  parsed-text artefact identity, parse vs embed/write timing decomposition,
  per-parser immutable index identity.
- Relation to ADR-020 is intact: this experiment validates the PDF reader
  factory. Gate 6C ordering still forbids amending ADR-020 (or writing its
  successor) before the result commit; this protocol amendment does not
  touch ADR-020.
- Per the task 6.1.7 / 6.GB.2 notes, this experiment is also designated the
  first real test of the documents-profile reranker setting (ADR-019
  evidence update), so the rerank-on cells carry that additional
  interpretation obligation on the semantic workload.
