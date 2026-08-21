# Experiment 5b — Persistent MPS reranker worker

**Experiment ID:** `5b-persistent-mps-reranker-worker`  
**Protocol version:** `1.0` (`1.0-draft` prepared against `b4788ff`; operational values resolved 2026-08-21 against `b013ae6`)  
**Status:** PLANNED — finalised before harness code; no measured result is claimed  
**Prepared against repository commit:** `b4788ff2fb6f548d11091edbeb1f9df622574a98`  
**Role:** experiment-only evaluation of a persistent optional Torch MPS worker

> Version 1.0 resolves every operational value that the proposal and prior
> experiments left open; no `TODO-LOCAL` marker remains. The amendment rule
> survives for future versions: any value changed after the first measured
> row invalidates the campaign and requires a new protocol version.

## 1. Research question

Can a persistent, process-isolated Torch MPS worker amortise the import and
model-load cost observed in Experiment 5 while preserving compatible Torch
fp32 rankings, improving parent-observed latency, staying inside the declared
opt-in memory budget, and failing or shutting down without hangs, late
responses, zombies or orphaned descendants?

This experiment does not reopen Experiment 5. Its H3 verdict remains FAIL.
Passing this protocol may recommend a separate production-worker OpenSpec and
decision record; it cannot introduce or promote a production worker itself.

## 2. Prior evidence carried forward

Experiment 5 measured fresh child processes using the cached
`cross-encoder/ms-marco-MiniLM-L-6-v2` model with `HF_HUB_OFFLINE=1`.

| Route | Median latency | Cold start | Peak RSS | Additional observation |
| --- | ---: | ---: | ---: | --- |
| `onnx_cpu` | 68.45 ms | approximately 0.276 s | approximately 268 MiB | ONNX int8, `CPUExecutionProvider` |
| `torch_cpu` | 58.72 ms | — | — | Torch fp32 CPU reference |
| `torch_mps` | 39.74 ms | approximately 3.818 s | approximately 635.6 MiB | MPS allocator approximately 86.7 MiB |

Torch CPU and Torch MPS were ranking-identical on 360/360 comparisons, with a
maximum score delta of `4.02e-07`. ONNX int8 and Torch fp32 disagreed on
360/360 rankings. That is backend/quantisation divergence, not an MPS device
defect, and it is not a correctness gate in Experiment 5b.

## 3. Pre-registered hypotheses

- **G1 — compatible Torch-route correctness:** persistence and IPC do not
  change Torch fp32 rankings or scores beyond the registered tolerance, and
  every admitted response proves the requested route and successful reranking.
- **G2 — MPS device speed:** persistent Torch MPS is faster than persistent
  Torch CPU using parent-observed end-to-end latency.
- **G3 — deployment value:** persistent Torch MPS is faster than the in-process
  ONNX CPU production baseline. This is a deployment comparison, not a
  cross-backend correctness assertion or a replication of Experiment 5 H2.
- **G4 — cumulative amortisation:** the full persistent-worker startup/model
  load and warm-up cost crosses the paired ONNX baseline within the declared request
  horizon.
- **G5/G6 — resource bounds:** every persistent-MPS lifetime fits the worker
  and whole-process-tree budgets and has bounded post-burn-in growth.
- **G7/G8 — failure and lifecycle bounds:** worker/channel failure degrades
  within registered deadlines, and every shutdown or parent-death route leaves
  no worker or descendant behind.
- **G9 — admissibility:** plan agreement, manifests, preflight, raw rows,
  complete-lifetime checkpoints and statuses satisfy TDR-014.

## 4. Experimental unit

The primary correctness and latency unit is one fixed query with its fixed,
ordered 50-candidate pool served through one declared execution route.

The persistence/resource unit is one complete fresh worker lifetime. A worker
lifetime starts before process spawn and ends only after the worker and every
descendant have exited and the external supervisor has completed its lifecycle
checks. Lifetimes, not repeated requests inside one process, are the unit of
replication.

## 5. Fixed workload identity

Reuse the committed Experiment 5 workload without regeneration or
modification:

- source: `experiments/example/experiment-5-reranker-backend-device-parity/workload.json`;
- identity: `sha256:bb412ddcd1e3c855a6bd78e06e61ff6a5bf72592a1566602c3b769524d06e1dc`;
- shape: 24 queries × 50 candidates;
- model: `cross-encoder/ms-marco-MiniLM-L-6-v2`, already cached;
- network policy: `HF_HUB_OFFLINE=1` for preflight and measured execution.

The workload is used for paired correctness, speed and primary break-even. The
amended design also requires a heterogeneous longevity schedule varying
candidate count and token length. It is committed as
`longevity_schedule.json` with the deterministic generator
`generate_longevity_schedule.py` (seed `20260821`):

- identity: `sha256:d59452150f92e235fc262ad4efdf7863a4d52a231bb8b2a08dd8f195b9b09d55`;
- shape: 228 requests over 19 strata — candidate counts
  {10, 25, 50, 100, 200} × approximate per-candidate token lengths
  {32, 128, 256, 512}, subject to the 65,536-token-per-request budget, with
  12 replicates per stratum;
- bursts: 8 groups of 16 consecutive requests (window starts 0, 30, 61, 91,
  121, 151, 182, 212) exercise queue/backpressure behaviour;
- materialisation: the harness synthesises query and candidate text from a
  fixed 512-word vocabulary using each request's recorded
  `text_materialisation_seed`, so text is a pure function of the committed
  schedule.

## 6. Manipulated variables and five-cell matrix

Manipulated factors are backend, device, process shape and backend precision.
The ONNX provider is manipulated only for the ONNX cell.

| Cell | Backend/precision | Effective route | Process shape | Role |
| --- | --- | --- | --- | --- |
| W1 `onnx_cpu_in_process` | ONNX int8 | `CPUExecutionProvider` first | in-process, fallback-ready parent | production deployment baseline |
| W2 `torch_mps_fresh` | Torch fp32 | device prefix `mps` | fresh child | one-shot MPS and compatible correctness reference |
| W3 `torch_mps_persistent` | Torch fp32 | device prefix `mps` | persistent worker | treatment under evaluation |
| W4 `torch_cpu_persistent` | Torch fp32 | device prefix `cpu` | persistent worker | persistent device-speed and correctness control |
| W5 `torch_cpu_fresh` | Torch fp32 | device prefix `cpu` | fresh child | completes the persistence × device matrix |

W2/W3 and W4/W5 estimate persistence effects within device. W3/W4 estimates
the MPS device effect within the persistent process shape. W2/W5 estimates the
device effect in fresh children.

## 7. Controlled variables

- identical model ID and exact cached model revision/file identity across all
  Torch routes: revision `233902d25c440f23af6f7d6e94d2946bac0bee0a`
  (`refs/main` in the local HF cache) with file SHA-256 digests
  `380e02c93f431831be65d99a4e7e5f67c133985bf2e77d9d4eba46847190bacc`
  (`config.json`),
  `821d1aa69520101d6e0737f78a042ae25b19e5cb9160701909d10434f4aeb0ae`
  (`model.safetensors`),
  `d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66`
  (`tokenizer.json`),
  `a5c2e5a7b1a29a0702cd28c08a399b5ecc110c263009d17f7e3b415f25905fd8`
  (`tokenizer_config.json`),
  `07eced375cec144d27c900241f3e339478dec958f92fddbc551f295c992038a3`
  (`vocab.txt`) and
  `3c3507f36dff57bce437223db3b3081d1e2b52ec3e56ee55438193ecb2c94dd6`
  (`special_tokens_map.json`); W1 additionally uses the cached ONNX exports
  `5d3e70fd0c9ff14b9b5169a51e957b7a9c74897afd0a35ce4bd318150c1d4d4a`
  (`onnx/model.onnx`) and
  `3573b6b9593cb2f75987a31815d409ca3dd8808629118fd20451bb1a5d90cec7`
  (`onnx/model_qint8_arm64.onnx`); any handshake revision/digest mismatch
  aborts the cell;
- tokenizer/max-length policy identical across cells; the carried-forward
  tokenizer maximum-length environment value is 2048;
- batch size 32 and `top_k=50`, matching the Experiment 5 plan;
- identical query/candidate text and order from the fixed workload;
- shared production sigmoid-normalisation contract;
- production `SentenceTransformerReranker` used unmodified inside Torch
  children;
- `PYTORCH_ENABLE_MPS_FALLBACK=0` set before any Torch-capable import;
- same physical machine, macOS build, power source and background-load policy;
- Apple Silicon host with at least 16 GiB physical memory for the declared
  opt-in budget;
- no vector DB, embedding, BM25, document parsing or network activity in the
  measured inference path;
- W1 and every W3 fallback parent use the same fallback-ready state: the ONNX
  model is loaded and warmed before measured request rows;
- one inference request active per worker unless a later protocol version
  explicitly declares a queue/concurrency factor;
- whole-lifetime execution order counterbalanced across repetitions.

## 8. Repetitions, warm-up and measurement windows

- W3 and W4: at least 3 complete, fresh worker lifetimes each;
- every persistent lifetime: at least 1,000 measured requests after untimed
  load and warm-up;
- W1, W2 and W5: at least 3 paired repetitions so every declared contrast has
  a fresh reference for the corresponding lifetime order;
- warm-up is recorded separately and excluded from every aggregate;
- requests 1–200 are memory burn-in;
- the plateau window is requests 801–1000;
- the growth window is requests 201–1000;
- current RSS is sampled at least once per second and every 10 completed
  requests, and after every completed request inside the growth window
  (requests 201–1000), yielding at least 800 ordered growth samples per
  lifetime.

An interrupted lifetime is never resumed under a new PID. Its partial rows are
retained with an invalid/incomplete status and reason, and the replacement
lifetime restarts from request zero.

## 9. Primary estimands

### 9.1 Parent-observed end-to-end latency

Primary latency begins before parent serialisation/queueing and ends after IPC,
worker inference, response parsing and route/result validation. Worker-only
inference time is diagnostic, not the primary gate input.

Report paired request rows, each lifetime median and P95, the pooled descriptive
distribution, and the W3/W4 and W3/W1 median ratios.

### 9.2 Cumulative startup break-even

For lifetime `l` and request count `n`:

`persistent_time_l(n) = startup_l + warmup_l + sum(parent_latency_l[1:n])`

`startup_l` includes worker startup and model load; model load is not added a
second time.

The paired W1 comparator is the cumulative W1 parent-observed request time for
the same ordered workload. `N*_l` is the first `n` where persistent time is no
greater than W1 and remains no greater through the registered horizon.

Report every `N*_l`, their median and a seeded block-bootstrap one-sided 95%
upper confidence bound. The seed is `20260821` and the block length is 40
samples. Report break-even by candidate-count/token-length stratum and
normalised candidate-token work as secondary estimands.

### 9.3 Memory

Retain these fields separately:

- current and peak worker RSS;
- current and peak parent RSS;
- current and peak complete process-tree RSS;
- `torch.mps.current_allocated_memory()`;
- `torch.mps.driver_allocated_memory()`;
- ratios to the paired W1 parent/process state.

Worker/process-tree plateau is the 95th percentile of current-RSS samples over
requests 801–1000. Peak-only `ru_maxrss` is diagnostic and cannot prove
plateau, growth or reclamation.

### 9.4 Post-burn-in growth

Use ordered current-RSS samples from requests 201–1000. Estimate Theil-Sen
slope, convert it to MiB per 1,000 requests, and calculate a seeded block-
bootstrap one-sided 95% upper confidence bound for every lifetime and the
pooled samples. The seed is `20260821` and the block length is 40 samples.

## 10. Pre-registered gates

| Gate | Exact decision rule |
| --- | --- |
| G1a | W3 versus paired W2: 100% ranking equality and maximum absolute score delta ≤ `1e-4`. |
| G1b | W3 versus paired W4: 100% ranking equality and maximum absolute score delta ≤ `1e-4`. |
| G1c | Every admitted response proves request ID/generation, model identity, requested/effective backend and device, expected cardinality and successful reranking; one violation fails the cell. |
| G2 | Parent-observed W3 median latency ≤ `0.8 ×` paired W4 median latency. |
| G3 | Parent-observed W3 median latency ≤ `0.8 ×` paired W1 median latency. This is the production-deployment gate, not a correctness gate or Experiment 5 H2 replication. |
| G4 | The cumulative break-even one-sided 95% upper confidence bound is ≤ 150 requests on the frozen primary workload. |
| G5 | Every W3 lifetime independently: worker plateau RSS ≤ 750 MiB; fallback-ready parent plus worker process-tree plateau RSS ≤ 1,250 MiB; process-tree peak RSS ≤ 1,500 MiB. |
| G6 | Every lifetime and the pooled post-burn-in growth one-sided 95% upper confidence bound are < 20 MiB per 1,000 requests. |
| G7 | Worker death, worker hang and pipe-pressure probes complete through ONNX CPU or the existing un-reranked fallback within the registered request deadline, with loud diagnostics and no late response admitted. Deadline: 5.0 s. |
| G8 | Requested shutdown, stdin EOF, idle expiry and externally induced parent death leave zero worker/descendant processes after bounded TERM/KILL and reaping. Drain 2 s; TERM grace 5 s; KILL grace 5 s; idle expiry 60 s; orphan observation 10 s. |
| G9 | TDR-014 plan agreement, manifest, preflight, no-fallback, raw-row, checkpoint, completion-status and deterministic-projection requirements all pass. |

ONNX/Torch ranking, score and threshold divergence remains raw descriptive
evidence. It is excluded from G1.

Any failed or `NOT_EVALUABLE` gate rejects promotion and retains ONNX CPU as
the production default. Gates are never relaxed after the first measured row.

## 11. Versioned JSON-lines protocol contract

The experiment worker communicates over stdin/stdout JSON lines:

1. child emits `hello` with protocol version and process identity;
2. child loads the production reranker and emits `ready` with exact model and
   route evidence;
3. parent sends bounded `rerank` frames carrying request ID, generation,
   query, candidates and `top_k`;
4. child returns a correlated result frame with route, cardinality, reranked
   status, ordered IDs/scores and diagnostics;
5. parent sends orderly shutdown or closes stdin; worker drains or aborts
   within the registered bounds and exits.

Stdout is protocol-only. Stderr is drained concurrently. Maximum JSON frame
size is 8 MiB, maximum candidate count is 200, maximum token budget is
65,536 tokens per request and maximum queue depth is 16. Duplicate, unknown,
oversized, wrong-generation and late frames are rejected and retained as
failure evidence.

## 12. Lifecycle probe matrix

Every probe records parent PID, worker PID, descendant PIDs, worker generation,
start/end monotonic timestamps, requested/effective fallback route, exit status,
deadline result and final process existence/reaping evidence.

| Probe | Required observation |
| --- | --- |
| worker death | Kill a ready W3 worker during a request; request falls back within the deadline; no late response is admitted. |
| worker hang | Stop or otherwise make the worker non-responsive during a request; deadline fires; bounded termination and fallback occur. |
| parent death while idle | External supervisor kills the parent; stdin/descriptor closure or supervisor cleanup removes worker and descendants. |
| parent death in-flight | External supervisor kills the parent during inference; no worker or descendant remains after the orphan-observation bound. |
| stdout backpressure | Stop parent reads until the registered pressure condition; no unbounded hang, and termination remains bounded. |
| stderr flooding | Worker emits the registered diagnostic volume; concurrent drain prevents deadlock. Volume: 4 MiB sustained. |
| malformed/oversized frame | Worker or parent rejects the frame loudly without admitting it to measured evidence. Limits: section 11 bounds (8 MiB frame, 200 candidates, 65,536 tokens). |
| request deadline | A late response is rejected by request ID/generation and the request completes through the registered fallback. Deadline: 5.0 s. |
| idle expiry and restart | Idle worker exits; next request creates a new generation after registered backoff and re-runs route preflight. Idle expiry 60 s; backoff 1 s, 2 s, 4 s capped; maximum 3 restart attempts. |
| orderly shutdown | In-flight work drains or aborts, stdin closes, TERM/KILL bounds are honoured and the process is reaped. Bounds: drain 2 s, TERM grace 5 s, KILL grace 5 s. |
| EOF-on-stdin | Worker exits after parent channel closure; EOF is evidence but not the sole orphan guarantee. |
| orphan/reaping check | External supervisor proves zero live worker/descendant processes and no zombie after each applicable probe. Observation bound: 10 s. |

Maximum restart attempts are 3, with a 1 s, 2 s, 4 s capped backoff sequence.
A restarted worker always has a new generation and preflight.

## 13. Preflight assertions

Before any measured row:

- `plan.json` loads through `ExperimentPlan.from_json`;
- the runner matrix exactly equals W1–W5 via `assert_runner_cells`;
- workload identity equals
  `sha256:bb412ddcd1e3c855a6bd78e06e61ff6a5bf72592a1566602c3b769524d06e1dc`;
- model equals `cross-encoder/ms-marco-MiniLM-L-6-v2` at cached revision
  `233902d25c440f23af6f7d6e94d2946bac0bee0a` with the section 7 file
  digests;
- `reranker.requested_backend` and `reranker.effective_backend` are non-null
  and equal for the manipulated route;
- W1 reports `CPUExecutionProvider` first;
- W2/W3 report Torch device prefix `mps`;
- W4/W5 report Torch device prefix `cpu`;
- `PYTORCH_ENABLE_MPS_FALLBACK=0` was set before Torch import;
- parent after Torch child/probe execution has not imported `torch`,
  `transformers` or `sentence_transformers`;
- no production graceful fallback, wrong cardinality or `_reranked=False`
  result enters a measured cell;
- `HF_HUB_OFFLINE=1` and no model download/network activity contaminates the
  measured region;
- current RSS sampling is available; otherwise G5/G6 are `NOT_EVALUABLE` and
  measured promotion work is blocked;
- power, thermal/background-load and fallback-ready W1 parent policy match the
  protocol.

## 14. Abort, invalid and not-evaluable criteria

Abort the cell immediately and retain a non-numeric status/reason when:

- requested and effective backend/device/provider differ;
- the model identity, tokenizer policy, workload hash or fixed order differs;
- any admitted response is unreranked, wrong-cardinality, wrong-generation,
  malformed or late;
- Torch-stack modules appear in the parent;
- model download or network access occurs;
- a sampler needed by a gate is unavailable;
- a thermal, power or foreground-interference condition breaches its
  pre-registered local bound (mains power required; host thermal pressure
  above nominal; declared foreground interference);
- the process or supervisor cannot complete the declared repetition/lifetime;
- a checkpoint is partial, a lifetime crosses PIDs, or plan/runner agreement
  fails.

An invalid or incomplete row/lifetime is never recorded as slow or aggregated.
Current-RSS absence makes G5/G6 `NOT_EVALUABLE`; it does not permit substitution
with peak RSS.

## 15. Randomisation and interference controls

Counterbalance complete cell/lifetime order so thermal and time drift do not
consistently favour one route. Record host identity, macOS, Python and package
versions, power source, memory pressure, available thermal evidence,
foreground-interference declaration, cell order and start/end times.

The counterbalancing schedule is fixed (seed `20260821`). Each repetition
block runs all five cells once, in an order produced by seeding
`random.Random(20260821)`, shuffling the cell list and rotating it by two
positions per block:

| Block | Execution order |
| --- | --- |
| 1 | W5, W3, W2, W4, W1 |
| 2 | W2, W4, W1, W5, W3 |
| 3 | W1, W5, W3, W2, W4 |

Every cell occupies a different position in each block. The registered
thermal/interference rule: measurement runs only on mains power; a complete
lifetime is invalid when host thermal pressure exceeds nominal or when
operator-declared foreground interference occurs, and an invalid lifetime is
repeated in full — never edited at the request-row level.

## 16. Analysis plan

1. Validate plan/runner agreement and every preflight assertion.
2. Exclude warm-up and every incomplete/invalid lifetime.
3. Evaluate G1 on paired Torch fp32 rows only.
4. Evaluate G2 on W3/W4 parent-observed paired latency.
5. Evaluate G3/G4 on paired W3/W1 deployment rows.
6. Evaluate G5 per W3 lifetime; do not average a failing lifetime into a pass.
7. Evaluate G6 per lifetime and pooled with the fixed bootstrap procedure.
8. Evaluate every G7/G8 probe from raw supervisor/process evidence.
9. Evaluate G9 and regenerate the canonical correctness projection twice.
10. Report ONNX/Torch divergence descriptively without feeding it into G1.

No inferential test is substituted for a practical gate. Raw lifetime and
request distributions remain visible beside summaries.

## 17. TDR-014 artefact contract

Required committed artefacts after implementation/execution:

- this `protocol.md`, with immutable pre-measurement version and later dated
  execution record;
- `plan.json` plus recorded plan hash and green runner agreement;
- reused workload path and SHA-256, never a regenerated copy;
- heterogeneous longevity schedule (`longevity_schedule.json`, generator
  `generate_longevity_schedule.py`) and SHA-256;
- per-cell/per-lifetime runtime manifests with repo, lock, workload, model,
  Python/dependency and requested/effective route identity;
- preflight assertion output and no-fallback result;
- raw per-request rows carrying `cell_id`, `query_id`/request ID, worker
  lifetime/generation, phase, parent latency and metrics;
- ordered current-RSS and MPS allocator/driver samples;
- lifecycle supervisor/process rows and stderr diagnostics;
- atomic complete-lifetime checkpoint and completion statuses;
- canonical correctness projections generated twice from frozen raw rows;
- results summary with G1–G9, every invalid/`NOT_EVALUABLE` item, absolute and
  W1-ratio memory reporting.

Inference-only fields that are legitimately absent must carry explicit
TDR-014 `null_reasons`; absence is not positive evidence.

## 18. Checkpoint and resume contract

Write checkpoints to `.tmp`, fsync/close as implemented, then atomically rename.
A checkpoint marks only a complete lifetime reusable. `--resume` skips complete
lifetimes and restarts any incomplete lifetime from request zero. Partial rows
remain evidence of interruption but never enter aggregates. No score pairing,
latency aggregate or memory slope crosses PIDs/generations.

## 19. Interpretation rules

- G1 pass + G2/G3/G4 pass + G5/G6 pass + G7/G8/G9 pass: the experiment may
  recommend a separate production-worker proposal.
- Torch routes disagree under G1: reject persistence/MPS promotion and
  investigate compatible-route correctness.
- ONNX differs while Torch routes satisfy G1: classify as backend/
  quantisation divergence, not an MPS defect.
- speed passes but memory/lifecycle/admissibility fails: retain the useful
  diagnostic finding but reject production promotion.
- any `NOT_EVALUABLE` gate: reject promotion; do not reinterpret it as pass.

The 750 MiB worker budget and whole-process-tree budgets are new opt-in product
limits. They do not rehabilitate Experiment 5 H3.

## 20. Threats to validity

- Apple Silicon generations and macOS MPS behaviour vary.
- Repeated fixed workloads may warm caches; the separate heterogeneous schedule
  is required for longevity/fragmentation evidence.
- system thermal state and WindowServer/background activity can bias timings.
- driver-allocated MPS memory may reflect system/device behaviour distinct from
  process RSS or current allocator use.
- an experiment-local worker proves this protocol shape, not production spawn,
  packaging, traffic, idle-retention or restart policy.

## 21. Planned reproduction commands

These commands describe the intended house-style interface. The harness files
do not exist at protocol time. The registered probe flags are the section 12
probe names in kebab-case: `--probe-worker-death`, `--probe-worker-hang`,
`--probe-parent-death-idle`, `--probe-parent-death-inflight`,
`--probe-stdout-backpressure`, `--probe-stderr-flooding`,
`--probe-malformed-frame`, `--probe-request-deadline`,
`--probe-idle-expiry-restart`, `--probe-orderly-shutdown`, `--probe-eof-stdin`
and `--probe-orphan-reaping`.

```bash
cd experiments/5b-persistent-mps-reranker-worker-2026-08-20

# Structural validation before model load.
PYTHONPATH=../.. uv run --no-sync python -c \
  'from experiments._lib.plan import ExperimentPlan; ExperimentPlan.from_json("plan.json")'

# Untimed route and lifecycle preflight only.
HF_HUB_OFFLINE=1 uv run --no-sync python run_eval.py --dry-run

# Measured campaign, only after preflight passes.
HF_HUB_OFFLINE=1 uv run --no-sync python run_eval.py --output-dir output
uv run --no-sync python summarise_eval.py --output-dir output
```

## 22. Current execution record

**PLANNED.** No harness code, local preflight, worker lifetime, lifecycle probe,
latency row, memory sample, gate verdict or promotion recommendation is claimed
by this protocol draft.

**Version 1.0, 2026-08-21:** all operational values registered — longevity
schedule identity, model revision/file digests, bootstrap seed and block
length, request/drain/TERM/KILL/idle/orphan deadlines, restart limits, frame
bounds, counterbalancing table and thermal/interference rule. No `TODO-LOCAL`
marker remains.
