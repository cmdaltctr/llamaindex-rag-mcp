# Experiment 6 — Ingestion boundedness, atomic replacement and concurrency

**Template ID:** `example/experiment-6-ingestion-boundedness-and-atomicity`  
**Status:** PLANNED  
**Role:** systems/reliability gate after Stage 3A; evidence for optional Stage 3B

## 1. Research question

Does the hardened ingestion path keep memory bounded as corpus file count grows and preserve the last durable searchable version under injected failures? If those correctness properties hold, does moving embedding outside a narrow store-write lock materially improve throughput enough to justify a Stage 3B concurrency change?

The experiment has two phases: **A correctness/boundedness is mandatory; B concurrency A/B is conditional.**

## 2. Pre-registered hypotheses

### Phase A — mandatory

- **H1 — bounded node lifetime:** increasing corpus file count by N does not increase the maximum number of simultaneously retained source-file node sets linearly with N; implementation stays within the declared bounded unit.
- **H2 — memory scaling:** peak RSS grows sublinearly with file count once steady processing begins; define the numeric guard before promotion based on generated file size (recommended: 4x files must not cause >2x peak working-set growth after excluding fixed model baseline).
- **H3 — failure safety:** parse, embedding and store-write failure injected while replacing source version B leaves durable version A searchable.
- **H4 — successful swap:** after B is durable, A is removed and retrieval sees one effective latest source version.
- **H5 — unchanged skip:** a second identical ingest performs zero embedding/store-write work for unchanged files.

### Phase B — conditional optimisation

- **H6 — throughput:** narrow-lock/precomputed-embedding candidate improves documents/chunks per second by at least 20% over Stage 3A baseline on the selected hardware.
- **H7 — no resource regression:** candidate peak RSS <= 1.25x baseline and no correctness/failure-safety gate regresses.

If H6 fails, Stage 3B is not warranted even if the candidate works.

## 3. Experimental unit

Phase A boundedness/performance unit: one complete generated-corpus ingest.  
Failure-safety unit: one source replacement attempt with one injected failure point.  
Phase B unit: one generated-corpus ingest per pipeline variant/repetition.

## 4. Manipulated / independent variables

### Phase A factors

A. corpus size in files: e.g. `{25, 100, 400}` with fixed file size/content complexity;  
B. failure point: `{none, parse, embed, store_write}`;  
C. repeat state: `{first_ingest, unchanged_second_ingest, one_file_modified}`.

### Phase B factor

`pipeline_variant`:
- `stage3a_bounded_safe` — control;
- `stage3b_narrow_lock` — treatment, only after candidate exists.

Optional second block: vector store backend `{chroma_local, lancedb_local}`. Cloud storage is a separate systems environment and should not be mixed into local lock conclusions.

## 5. Controlled variables

- generated source bytes and seed;
- average tokens/chunks per file;
- embedding provider/model;
- embed batch size;
- vector store and mode within each backend block;
- parser/chunking/metadata extraction settings (disable expensive LLM metadata unless specifically under test);
- hardware/power state;
- Python/dependency lock;
- same corpus order;
- same write/version identity rules.

For a pure ingestion-systems benchmark, use a deterministic local fake embedding provider or precomputed embedding seam for Phase A memory/fault tests where possible; run a real Ollama embedding sub-benchmark separately if measuring real embed throughput.

## 6. Blocking / stratification variables

- store backend is a block;
- fake/precomputed vs real embedding is a block;
- cold first ingest vs unchanged repeat vs one-file change are separate operational blocks.

Do not average local Chroma and Lance lock behaviour into one mean.

## 7. Dependent variables

### Correctness

- old-version searchable boolean after failure;
- latest-version uniqueness after success;
- stale-version row count;
- files/chunks skipped unchanged;
- generation changes;
- error classification.

### Systems

- peak RSS and baseline-adjusted peak working set;
- maximum simultaneously live file/node batches;
- total wall time;
- parse/chunk time;
- embedding time;
- store-write time;
- lock-wait time;
- docs/s and chunks/s;
- number of embedding calls and written rows.

## 8. Cell matrix

### Phase A boundedness

For each corpus size: one clean first ingest + unchanged repeat. Add one-file-modified at medium size.

### Phase A fault injection

| Cell | Existing version A | New B | Inject at | Expected |
|---|---|---|---|---|
| F0 | yes | valid | none | B replaces A |
| F1 | yes | invalid/forced | parse | A remains |
| F2 | yes | valid parse | embed | A remains |
| F3 | yes | valid embed | write | A remains |

### Phase B

For each store/backend block run baseline and treatment on the exact same generated corpus with fresh storage.

## 9. Corpus identity

Generate deterministic text/code files from a committed seed and generator version. Record manifest SHA, file count, bytes and expected chunk range. Generated corpus content must be byte-identical across pipeline variants.

## 10. Randomisation / counterbalancing

Phase A correctness sequence is fixed.  
Phase B performance: alternate baseline/treatment order across >=3 repetitions and use fresh stores per repetition. If real Ollama is used, record model residency and run a warm-up before measured repetitions.

## 11. Repetitions and warm-up

- deterministic fault cells: one + exact rerun;
- memory scaling: >=3 runs per corpus size if RSS noise is material;
- Phase B throughput: >=3, preferably 5, fresh-store repetitions per variant.

## 12. Preflight assertions

- runtime manifest identifies pipeline variant and store;
- generated corpus checksums match across comparable cells;
- failure injector is armed at the intended stage;
- old version A is searchable before F1-F3;
- peak RSS sampler is functioning before performance inference;
- unchanged-second-ingest preflight verifies same index-shaping identity.

## 13. Abort / invalid-cell criteria

- corpus differs across A/B performance cells;
- model download/startup contaminates measured steady-state without being separated;
- injected failure fires at a different stage;
- process terminates before memory/timing samples are flushed -> `INCOMPLETE`;
- old version was not confirmed before a failure-safety cell.

## 14. Success gates

H1-H5 are mandatory correctness gates.  
Suggested H2: 4x files -> <=2x baseline-adjusted peak RSS; final value must be frozen before measured execution.  
H6: >=20% throughput improvement for Stage3B candidate.  
H7: <=25% peak-RSS regression and all H1-H5 still pass.

## 15. Analysis plan

Plot peak RSS vs file count separately per store. Report stage timing breakdown and lock wait. For Phase B compare paired repetition ratios rather than only absolute times. Fault results are exact booleans/row traces, not statistical.

## 16. Threats to validity

- synthetic files may not model huge PDFs/single-file memory;
- fake embeddings isolate orchestration but not real Ollama behaviour;
- local Chroma lock conclusions do not automatically apply to Chroma Cloud;
- macOS memory reporting includes runtime allocator/cache behaviour.

## 17. Reproduction command placeholder

```bash
uv run python experiments/<promoted-dir>/run_eval.py --phase boundedness
uv run python experiments/<promoted-dir>/run_eval.py --phase faults
# conditional
uv run python experiments/<promoted-dir>/run_eval.py --phase concurrency-ab
```

## 18. Required raw artefacts

- corpus generator + manifest;
- per-run stage timings;
- memory time series/peak summary;
- failure injection traces and post-failure query results;
- embedding/write call counts;
- runtime manifests/checkpoints.

## 19. Interpretation rules

- H1-H5 fail -> fix ingestion; no large calibration.
- H1-H5 pass, H6 fails -> keep Stage 3A; do not widen concurrency.
- H1-H7 pass -> Stage 3B is evidence-backed for the tested block(s).
- local backend disagreement -> make backend-specific concurrency policy; do not average into a universal claim.

## 20. Cleanup

Remove generated corpora/stores after hashes/results are retained. Keep generator and manifests.
