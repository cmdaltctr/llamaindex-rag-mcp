# Experiment 6 — Execution results (v1.0, 2026-08-19)

**Task:** OpenSpec `harden-pipeline-correctness-before-calibration`, Stage 5 task 5.6 — run the ingestion boundedness/atomicity template against CURRENT code and record the confirming evidence.

**Status: GREEN.** Phase A H1–H5 all PASS. Phase B (confirming-only) consistent with experiment 18's Stage 3B record. Fault cells reproduce identically on exact rerun.

**Code under test:** repo commit `c475852cf195658ce6af8654e11e07dce4c39fec` (`git_dirty: true` — the experiment files themselves are uncommitted), `uv.lock` sha256 `3a225230a6eb…`. Pipeline variant: `stage3b_narrow_lock_current` (Stage 3B narrow write lock retained at HEAD; the Stage 3A baseline arm no longer exists, so Phase B measures current code only and cites experiment 18 as the A/B record).

## Phase A — mandatory gates (all PASS)

### H1 — bounded node lifetime: PASS

Direct observable from a harness probe wrapping `pipeline.replace_source_nodes_async` (the call site pipeline.py resolves):

| Observable | 25 files | 100 files | 400 files | 2-stream contended |
|---|---|---|---|---|
| max simultaneously-live replacement batches | 1 | 1 | 1 | 2 |
| max nodes per batch | 3 | 3 | 3 | 3 |

The high-water mark equals the ingest-stream count at every corpus size — it does not scale with file count. Corroborating code path: `src/rag_mcp/core/ingestion/pipeline.py` processes files in a sequential for-loop and drops the bounded node set in the `finally` block (`del nodes`); `replace_source_nodes_async` receives exactly one source's nodes.

### H2 — memory scaling: PASS (frozen guard)

Guard frozen in `plan.json` before the measured run: 4x files must not cause >2x baseline-adjusted peak RSS; baseline = median peak RSS of `rss_baseline_rep1..3` (fake runtime installed, empty-directory ingest).

- Baseline raw peaks: 135,643,136 / 137,216,000 / 137,281,536 B → median 137,216,000 B
- Raw peaks (all reps reported, medians used only for the guard):
  - 25 files: 277,020,672 / 277,135,360 / 277,839,872 B → adjusted median 139,919,360 B
  - 100 files: 298,680,320 / 298,254,336 / 302,596,096 B → adjusted median 161,464,320 B
  - 400 files: 375,619,584 / 371,752,960 / 375,308,288 B → adjusted median 238,092,288 B
- Frozen pair ratios: 25→100 (4x files) = **1.154** ≤ 2.0; 100→400 (4x files) = **1.475** ≤ 2.0
- Descriptive 25→400 (16x files) adjusted ratio: 1.703 ≤ 4.0 (2², implied by the guard)

### H3 — failure safety: PASS

Sequence per cell: version A ingested and confirmed searchable (row gate), target modified to B, injector armed, B ingest fails at the intended stage, A rows verified intact, injector disarmed, recovery ingest completes the swap.

| Cell | injection fired (marker in error) | observed stage | rows after failure | old-version rows | A survived |
|---|---|---|---|---|---|
| fault_parse | yes | file | 3 (= first) | 3 | YES |
| fault_embed | yes | embedding | 3 (= first) | 3 | YES |
| fault_store_write | yes | store_write | 3 (= first) | 3 | YES |

Determinism: `--rerun-proof` re-ran all four fault cells into isolated stores; every deterministic evidence field is identical (`output/rerun_proof_verdict.json`, `all_identical: true`).

### H4 — successful swap: PASS

All four cells (F0–F3): after the swap, `rows_for_target == swap_chunks`, `final_version_rows == swap_chunks`, `stale_rows == 0`, and for F1–F3 the old version-A rows are gone after recovery. F0 (`fault_none`) is the un-injected control: the modified ingest is itself the swap, so A correctly does not survive.

### H5 — unchanged skip: PASS

Second identical ingest at every size: `files_skipped_unchanged == size`, `chunks_created == 0`, **embed seam calls == 0**, **store write calls == 0** (counters at the production seams `_embed_missing_nodes` and `store.write_nodes`). `modified_100`: the one-file-modified ingest indexes exactly 1 file (99 skipped) with 1 embed call and 1 store write.

## Phase B — confirming evidence only (H6/H7)

Framing (also frozen in `plan.json`): Stage 3B is retained at HEAD; the Stage 3A baseline arm no longer exists. Current-code 2-stream contended throughput (100 files, fresh store per rep, 3 reps per arm) is compared descriptively against experiment 18's Stage 3B arm (`experiments/18-ingestion-lock-scope-ab-2026-08-19/output/results.ab.json`, A/B reference commit `b4b01b6`). This is not a re-run of the A/B.

| Arm | current docs/s (3 reps) | mean | exp18 stage3b mean | frozen-rule (≥0.9x, lock rule) | chunks/s current | chunks/s ref | ratio |
|---|---|---|---|---|---|---|---|
| fake contended | 29.28 / 29.86 / 28.80 | 29.31 | 36.28 | **FAIL (0.808x)** — flagged below | 86.45 | 76.39 | **1.132x** |
| real Ollama contended | 6.685 / 6.788 / 6.758 | 6.744 | 7.40 | **PASS (0.911x)**, lock-wait fraction 0.0 ≤ 0.10 | 19.89 | 15.76 | **1.262x** |

- **H6 (throughput consistent with Stage 3B): TRUE.** The real arm passes the frozen rule outright and its lock-wait fraction is exactly 0.0 — the Stage 3A value was 0.9668, so the narrow lock is demonstrably still in effect. The fake arm's raw docs/s ratio (0.808) is below the frozen 0.9 threshold; the cause is corpus composition, not code: the exp-6 generator's word pool yields **289 chunks per 100 files vs experiment 18's 208** (39% more store-write/embed work per document). Chunk-normalised throughput — the like-for-like comparison — shows no regression on either arm (1.13x fake, 1.26x real). Reported as found; no threshold was retro-fitted.
- **H7 (no resource regression): TRUE.** Current max peak RSS 315,637,760 B vs Stage 3B reference max 303,677,440 B = 1.039x ≤ 1.25; all Phase A gates green on the same code.
- Stage breakdown (real arm, rep2, summed over both streams): change-detection 0.141 s, parse/chunk 0.181 s, embedding 25.911 s, store-write 1.981 s, lock-wait 0.000 s, cleanup 0.923 s — embedding dominates and runs outside the lock, exactly the Stage 3B shape.

## Embedding runtime decision

- **Phase A:** deterministic fake embedding — the harness assigns `MockEmbedding` (`mock-deterministic-v1`, 32-dim) on the shared LlamaIndex `Settings.embed_model` before ingestion, the same seam the production composition root uses. No network, no model download. Protocol §5 fake/precomputed seam.
- **Phase B real arm:** real Ollama `nomic-embed-text`, pinned via explicit env (`EMBED_PROVIDER=local`, `LOCAL_BACKEND=ollama`, `EMBED_MODEL=nomic-embed-text`, `OLLAMA_BASE_URL=http://localhost:11434`) because the repo `.env` selects the llamacpp provider whose extra is not installed. Matches experiment 18's real-runtime pins.
- **Ollama reachability:** daemon up, `nomic-embed-text:latest` present (probed before the run); a warm-up ingest (2 files, separate collection, recorded as `warmup` rows) preceded each real measured cell.
- **Block-specific preflight:** fake cells assert `embedding.model == mock-deterministic-v1`; real cells assert `== nomic-embed-text`; `assert_no_fallback` runs on every cell manifest.

## Manifest identity

Every cell carries a D13 manifest built via `experiments._lib.manifest.build_runtime_manifest` with `pipeline_variant=stage3b_narrow_lock_current`, corpus identity = sha256 of the committed corpus-manifest copy, and `vector_store.index_identity` computed through the production `build_index_identity`. Retrieval/qrels/reranker/sparse/chunker sections are explicit nulls-with-reasons — this is an ingestion-systems experiment and TDR-014's retrieval-field mandatory list applies to retrieval experiments. Corpus identities (inner, from generator manifests): size 0 `e3b0c442…` (empty), 3 `64009dc2…`, 25 `4efc8dcf…`, 100 `3297e64b…`, 400 `ad5a378c…`. Controlled-constant assertions (per embedding block) green for provider/model/backend/mode/index-identity/pipeline-variant.

## Reproduction

```bash
uv run --no-sync python experiments/example/experiment-6-ingestion-boundedness-and-atomicity/run_eval.py --smoke
uv run --no-sync python experiments/example/experiment-6-ingestion-boundedness-and-atomicity/run_eval.py --phase boundedness
uv run --no-sync python experiments/example/experiment-6-ingestion-boundedness-and-atomicity/run_eval.py --phase faults
uv run --no-sync python experiments/example/experiment-6-ingestion-boundedness-and-atomicity/run_eval.py --rerun-proof
uv run --no-sync python experiments/example/experiment-6-ingestion-boundedness-and-atomicity/run_eval.py --phase concurrency-ab
uv run --no-sync python experiments/example/experiment-6-ingestion-boundedness-and-atomicity/summarise_eval.py
```

All drivers support `--resume`; `--remerge` rebuilds the aggregate artefacts from `output/cells` (recovery path).

## Production defects

None observed. Every gate's expected behaviour matched the observed behaviour; no hotfixes were needed or applied.

## Judgement calls

1. **Fake-arm frozen-rule miss reported, not worked around.** The 0.9x docs/s rule was frozen expecting corpus comparability with experiment 18; the corpora differ in chunks per file (289 vs 208 per 100 files). Both the frozen-rule outcome and the chunk-normalised ratio are reported; H6 follows the pre-declared escape (real arm passes the frozen rule, no chunk-normalised regression on either arm).
2. **`fault_none` (F0) old-version survival is correctly False** — the un-injected control's ingest is itself the successful swap. H3 evaluates F1–F3 only, matching experiment 18's gate logic.
3. **Store directories are run-scoped** (`store_{out_dir}_{cell}`): the first rerun-proof attempt collided with the primary run's persistent store; fixed in the harness (the failed attempt's artefacts were discarded, cells re-run clean).
4. **Chunk-count difference between fake (289) and real (295) arms** on the same corpus: chunk boundaries depend on the embed-model tokeniser in production chunking; recorded honestly in both arms' manifests via their distinct `index_identity`.
5. **Fault cells carry evidence records, not per-query rows** — the unit is a replacement attempt; `validate_per_query_rows` fits the boundedness/confirming rows (39 rows validated) and the fault booleans/counts live in their cell records, per the "where the shape fits" instruction.
6. **Experiments are exempt from the 500-line ceiling** (`tests/test_file_size_ceiling.py` governs `src/rag_mcp/` only); `run_eval.py` (~880 lines) and `summarise_eval.py` (~480) carry that debt openly, split by responsibility (corpus/harness/runner/summariser).
7. **Controlled-constant checks run in the summariser**, not per-cell preflight — they need all cell manifests, which only exist after each subprocess completes (subprocess-per-cell design). Per-cell preflight covers plan assertions, no-fallback, model identity, RSS sampler, corpus counts, and version-A searchability.
8. **`graphify update` not run** — the task's hard scope forbids modifying anything outside this experiment directory; the graph at `graphify-out/` will be dirty until the parent refreshes it.

## Artefacts

| Path | Content |
|---|---|
| `plan.json` | frozen 23-cell matrix, H2 guard, phase-B framing/verdict rule |
| `output/cells/*.json` | 23 complete cell records (manifest + rows/evidence) |
| `output/results.raw.json` | 39 validated per-run rows (36 measured, 3 warmup) |
| `output/cell_records.json` | finalised cell records (all `complete`) |
| `output/results.summary.json` | gates, H2 numbers, phase-B comparison, runtime decision |
| `output/rerun_proof_verdict.json` | fault-cell exact-rerun determinism proof |
| `output/rerun_proof/*.json` | the rerun cells themselves |
| `corpus_manifests/corpus_{0,3,25,100,400}.json` | committed generator manifests (sha256 per file) |
| `corpus.py`, `harness.py`, `run_eval.py`, `summarise_eval.py` | the harness |
