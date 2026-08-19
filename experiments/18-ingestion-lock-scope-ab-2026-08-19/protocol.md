# Experiment 18 — Ingestion lock-scope baseline and conditional A/B

**Template ID:** promoted from `example/experiment-6-ingestion-boundedness-and-atomicity`
**Status:** PLANNED
**Role:** systems/reliability gate after Stage 3A; measurement evidence for optional Stage 3B (design constraint D12: measure before widening)
**Operator:** Dr Muhammad Aizat Bin Md Hawari
**Date:** 2026-08-19

## 1. Research question

Does the Stage 3A replacement path keep memory bounded and preserve the last
durable searchable version under injected failures; and does the global
`write_lock` scope (embedding + mutation + verify + cleanup all inside the
lock) demonstrably limit ingestion throughput — the only condition under which
design.md §D12 authorises a Stage 3B narrow-lock change?

Two phases: **A correctness/boundedness + lock-scope measurement is mandatory;
B concurrency A/B is conditional** on Phase A evidence justifying a treatment.

## 2. Pre-registered hypotheses

### Phase A — mandatory

- **H1 — bounded node lifetime:** the maximum chunks retained per source stays
  constant per file as corpus file count grows 25 → 100 → 400.
- **H2 — memory scaling:** 4x files must not cause more than 2x peak RSS
  growth (25 → 100 comparison; fake-embedding block, so no model-load noise).
- **H3 — failure safety:** parse, embed, and store-write failure injected
  while replacing source version B leaves durable version A rows searchable.
- **H4 — successful swap:** after B is durable, only B's rows remain for the
  target file; recovery re-ingest after each fault completes the swap.
- **H5 — unchanged skip:** a second identical ingest performs zero embedding
  and store-write work (zero chunks created, all files skipped).

### Phase B — conditional optimisation (reserved)

- **H6 — throughput:** a narrow-lock candidate improves contended docs/s by
  at least 20% over the Stage 3A baseline on this hardware.
- **H7 — no regression:** candidate peak RSS ≤ 1.25x baseline and H1-H5 stay
  green.

If the Phase A timing evidence shows the lock is not the constraint, Stage 3B
is rejected by measurement and Phase B never runs.

## 3. Experimental unit

Phase A boundedness unit: one complete generated-corpus ingest cell (first +
unchanged repeat in one isolated subprocess). Fault unit: one source
replacement attempt with one injected failure point. Timing unit: one
generated 100-file corpus ingestion per topology (sequential or two contended
streams).

## 4. Manipulated / independent variables

- corpus size in files: `{3, 25, 100, 400}`;
- failure point: `{none, parse, embed, store_write}`;
- repeat state: `{first, first_plus_unchanged_second, one_file_modified}`;
- ingest topology: `{sequential_1_stream, concurrent_2_streams}`;
- embedding block: `{fake_deterministic, real_ollama}`.

`concurrent_2_streams` is a deliberate addition over the Example 6 template:
`ingest_path_async` processes files sequentially inside one call, so a single
stream can never contend for the global lock. The realistic contention case —
two concurrent ingest operations writing one collection (daemon dual ingest,
concurrent MCP tool calls) — requires two interleaved streams.

## 5. Controlled variables

Deterministic seed 20260819; generator version 1.0; 6000 target characters
per file; chunk size 512 / overlap 100 (code defaults); metadata extraction
disabled (explicit `EffectiveSettings`, ADR-037); Chroma local persistent
store isolated per cell under `output/`; collection `documents`; frozen
`uv.lock`; same corpus bytes across topology comparisons (same seed).

## 6. Blocking / stratification variables

Store backend is a block (this run: Chroma local only; LanceDB is a separate
future block). Fake vs real embedding is a block: fake isolates orchestration
and store-mutation cost; real (Ollama `nomic-embed-text`) shows the realistic
critical-section composition. Sequential vs contended topologies are separate
operational blocks within each embedding block; never averaged together.

## 7. Dependent variables

Correctness: old-version rows after failure; swap completion; unchanged skip
count; chunks created. Systems: wall time; per-stage timings read from the
Stage 3A ingestion contract (`change_detection_seconds`, `parse_chunk_seconds`,
`embedding_seconds`, `store_write_seconds`, `lock_wait_seconds`,
`cleanup_seconds`, per-unit `total_seconds`); untimed residual (verification +
stamping + orchestration overhead, computed as Σtotal − Σstages);
`docs_per_second`; peak RSS per cell subprocess.

The pipeline is not re-instrumented. Known attribution limits (recorded in
`design-notes.md`): `embedding_seconds` includes embed-semaphore acquire, and
durability verification sits in the untimed residual.

## 8. Cell matrix

| Cell | Factors | Purpose |
| --- | --- | --- |
| bounded_25 / bounded_100 / bounded_400 | sizes, fake, first+unchanged | H1, H2, H5 |
| modified_25 | 25 files, one modified | skip precision (1 reindexed, 24 skipped) |
| fault_none (F0) | 3 files, no injection | H4 baseline |
| fault_parse (F1) | parse injection | H3 |
| fault_embed (F2) | embed injection | H3 |
| fault_store_write (F3) | store-write injection | H3 |
| timing_fake_seq_100 | sequential, fake | store-mutation critical section |
| timing_fake_contended_100 | 2 streams, fake | lock wait under contention, store-bound |
| timing_real_seq_100 | sequential, Ollama | realistic stage composition |
| timing_real_contended_100 | 2 streams, Ollama | realistic contended lock wait |

## 9. Corpus identity

`corpus.py` generates deterministic text from seed 20260819; the manifest
records per-file SHA-256 and `corpus_identity` (SHA-256 of the ordered file
hash list). The contended topology reuses byte-identical corpus content
(same seed); halves are disjoint file subsets copied into two directories.

## 10. Randomisation / counterbalancing

Phase A correctness sequence is fixed. Timing cells run in one fixed order
(fake sequential, fake contended, real sequential, real contended) with a
fresh isolated store per cell; there is no cross-cell cache state to
counterbalance because every cell is a separate process. Real-block model
residency is handled by warm-up (§11).

## 11. Repetitions and warm-up

Correctness cells: one execution each plus exact assertions (deterministic).
Timing cells: one execution per cell in this baseline run; if timing noise
proves material to the Stage 3B decision, the orchestrator re-runs the timing
phase before deciding (repetition is recorded per cell in results). Real
block: one 2-file warm-up ingest into a separate `warmup` collection before
measured cells; warm-up wall time is recorded and excluded.

## 12. Preflight assertions

Runner cells must match `plan.json` exactly (asserted via
`experiments/_lib/plan.py::ExperimentPlan.assert_runner_cells` before any
cell executes); corpus identity recorded in every cell manifest; all store
persist directories under `output/`; metadata extraction disabled in the
injected settings; old version A confirmed present before F1-F3; Ollama
availability probed before real cells (unavailable ⇒ cell recorded
`skipped`, not failed).

## 13. Abort / invalid-cell criteria

Corpus identity mismatch across topology comparisons; a fault firing at a
different stage than armed; old version not confirmed before a fault cell; a
cell process dying before its JSON checkpoint is written (`INCOMPLETE`);
real-embedding cell where the effective model differs from
`nomic-embed-text`; any store path outside `output/`.

## 14. Success gates

H1: max chunks per file > 0 and constant across sizes (bounded unit). H2:
peak RSS(100)/peak RSS(25) ≤ 2.0. H3: old-version rows survive every injected
fault. H4: swap completes for every fault cell including F0. H5: second
ingest skips all files with zero chunks created. Decision inputs (not gates):
single-stream lock-wait fraction; contended lock-wait fraction; contended
speedup = sequential wall / contended wall (same 100 files; fully serialised
= 1.0, ideal 2-stream = 2.0).

## 15. Analysis plan

Report per-cell stage timings and lock wait separately per embedding block.
Compare contended wall time against the sequential run on the same corpus.
Compute the untimed residual per stream. Fault results are exact booleans and
row counts, not statistics. No averaging across blocks.

## 16. Threats to validity

Fake embeddings isolate orchestration but not Ollama behaviour. macOS
`ru_maxrss` includes allocator/runtime overhead; per-cell subprocesses bound
attribution to one cell but cannot separate interpreter baseline from
working set (H2 partially masked by the fixed baseline — mitigated by the
≤2.0 guard rather than an absolute claim). Local Chroma conclusions do not
transfer to Chroma Cloud. Generated text does not model large PDF parsing.
`embedding_seconds` includes semaphore acquire; verify/stamping sit in the
residual (see `design-notes.md` measurement-gap note).

## 17. Reproduction commands

```bash
uv run --no-sync python experiments/18-ingestion-lock-scope-ab-2026-08-19/run_eval.py --smoke
uv run --no-sync python experiments/18-ingestion-lock-scope-ab-2026-08-19/run_eval.py --phase boundedness --resume
uv run --no-sync python experiments/18-ingestion-lock-scope-ab-2026-08-19/run_eval.py --phase faults --resume
uv run --no-sync python experiments/18-ingestion-lock-scope-ab-2026-08-19/run_eval.py --phase timing --resume
uv run --no-sync python experiments/18-ingestion-lock-scope-ab-2026-08-19/summarise_eval.py
# conditional, reserved:
uv run --no-sync python experiments/18-ingestion-lock-scope-ab-2026-08-19/run_eval.py --phase concurrency-ab
```

## 18. Required raw artefacts

`output/cells/<cell>.json` per cell (factors, runtime manifest, raw per-stream
results, timings, peak RSS); `output/results.summary.json`; corpus generator
+ manifest; this protocol; `design-notes.md` (candidate-design survey) and
`test-contract-map.md` (pinned contracts) as companion analysis inputs.

## 19. Interpretation rules

H1-H5 fail ⇒ fix ingestion; no concurrency work. H1-H5 pass and the lock is
not a demonstrated constraint (contended lock-wait fraction immaterial, or
contended speedup already near the parallel bound, or store-write/verify
dominating the lock-held section with embedding negligible) ⇒ keep Stage 3A;
record "not warranted by measurement". H1-H7 pass only after a candidate
exists ⇒ Stage 3B is evidence-backed. Single-stream lock wait ≈ 0 is expected
by construction and is never, alone, evidence for widening. Local-backend
disagreement ⇒ backend-specific policy, never a universal claim.

## 20. Cleanup

Generated corpora and per-cell Chroma directories stay under `output/`
(gitignored) and are deleted after results are retained; generator, protocol,
plans, cell JSONs, and summaries are committed.
