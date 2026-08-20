## Context

Experiment 5 (`experiments/example/experiment-5-reranker-backend-device-parity/`, commit `1a12249`) measured fresh-child execution routes: ONNX CPU, ONNX CoreML, Torch CPU, Torch MPS. Verdict: correctness H1/H5 PASS, speed H2 PASS (MPS median 0.677× Torch CPU), operational H3 FAIL (RSS 2.370×, cold start 13.826× ONNX CPU). The cost is dominated by the torch + transformers + sentence-transformers import stack (~3.5 s) paid in every child, plus ~630 MiB process residency against a 268 MiB baseline. Experiment 17 separately showed MPS 4.5× faster than ONNX CPU at larger batch shapes with clean device parity.

Production constraints that shape the design: the `torch` extra stays opt-in (ADR-005/ADR-043 boundary, enforced by `reranker-backend-selection` spec); ONNX CPU stays the default backend; `SentenceTransformerReranker` and the process-wide `(backend_name, model_id)` model cache stay untouched in production; TDR-014 governs experiment admissibility.

## Goals / Non-Goals

**Goals:**

- Measure what Experiment 5's H3 could not: amortised startup, steady-state residency, and memory growth of a long-lived Torch process.
- Keep the experiment harness entirely inside the experiment directory; zero production code changes.
- Prove lifecycle behaviour (ready handshake, induced-death fallback, drain-and-exit, RSS reclamation) with pre-registered gates.

**Non-Goals:**

- No production worker, no new settings, no default-backend change. A passing result only *recommends* a follow-up OpenSpec.
- No revision of Experiment 5 or its verdict.
- No CoreML re-testing (rejected in Experiment 5 on ~5.5 GiB RSS).

## Decisions

### D1: Experiment-local worker prototype, stdio JSON-lines protocol

The worker is a committed child script owned by the experiment. The parent speaks newline-delimited JSON over the child's stdin/stdout: `hello` (torch version, model, effective device, MPS availability) → `ready`; then `rerank` requests carrying `(request_id, query, candidates[], top_k)` answered with scored/sorted/truncated results plus per-request diagnostics. Stdio is chosen over sockets/queues because EOF-on-stdin gives orphan protection for free: a crashed parent closes the pipe and the worker exits, releasing its ~630 MiB. Alternative (local socket) rejected: same capability, more failure modes, no orphan latch.

### D2: Production reranker class inside the worker, unmodified

The worker constructs `SentenceTransformerReranker` and calls `rerank()`. Score semantics (Identity activation + shared sigmoid, `reranker_sigmoid_v1`) therefore stay identical to production by construction, not by re-implementation. The parent never imports anything from the `torch` extra; the base process stays torch-free, preserving the ADR-005 boundary by process separation rather than import discipline. Alternative (re-implement scoring in the worker) rejected: drifts from the production contract.

### D3: Cell matrix W1–W4, longevity axis on W3

- W1 `onnx_cpu` in-process — production default baseline.
- W2 `torch_mps` fresh child per round — replicates the Experiment 5 shape on this workload for one-shot cost confirmation.
- W3 `torch_mps` persistent worker — ≥3 fresh worker lifetimes × ≥1,000 measured requests each, periodic memory sampling, plus two lifecycle probes (induced mid-serving death; idle-expiry restart).
- W4 `torch_cpu` persistent control — attributes any worker-level effect to MPS rather than to persistence itself.

Alternative (drop W4) rejected: without it a worker-lifecycle artefact and an MPS artefact are indistinguishable.

### D4: Sampled memory, not peak-only

`ru_maxrss` is monotonic and cannot show plateaus or reclamation. The parent samples the child's RSS via `psutil` (fallback: `resource.getrusage` on the child side if psutil is unavailable) every N requests and on a timed ticker; the worker reports `torch.mps.current_allocated_memory()` / `driver_allocated_memory()` per sample window. Summary derives: steady-state plateau, MPS allocator plateau, post-burn-in growth slope per 1,000 requests, and post-exit reclamation check. Alternative (peak-only, as Experiment 5) rejected: peak-only is exactly the blind spot this experiment exists to close.

### D5: Pre-registered gates (fixed in the protocol before any measured cell)

- G1 parity: W3 vs W2 vs W1-round-1 ranking equality 100%, max score delta ≤ 1e-4 (Experiment 5 H1 tolerance).
- G2 speed: W3 median ≤ 0.8× W1 median (Experiment 5 H2 gate shape).
- G3 amortisation: measured break-even N* ≤ 150 requests.
- G4 steady-state residency: W3 plateau RSS ≤ 750 MiB absolute. Chosen as an absolute bound (not a ratio to W1) because a long-lived worker is a different deployment shape than the fresh-child design Experiment 5's 2.0× ratio governed; ~630 MiB observed at load makes 750 MiB a honest plateau ceiling with ~20% headroom. The protocol records this amendment rationale up front rather than relaxing a gate after measurement.
- G5 growth: < 20 MiB per 1,000 requests post-burn-in, no monotonic climb.
- G6 fallback: induced worker death → request completes via ONNX CPU or un-reranked within the registered deadline, loud diagnostics, no hang.
- G7 lifecycle: shutdown drains within deadline, no orphans/zombies, worker exit reclaims RSS to the registered tolerance.

Any gate failure → ONNX CPU remains default, worker stays experimental. Gates are never relaxed after a cell runs.

### D6: TDR-014 admissibility throughout

Plan agreement check before measured work; per-cell D13 manifests (repo commit, lock hash, workload identity, effective backend/device via the existing `_lib` observers); `HF_HUB_OFFLINE=1`; untimed load + warm-up separated from measured rows; atomic `.tmp`→rename checkpoints with `--resume`; incomplete/invalid lifetimes recorded by status string, never as numbers. The workload is the committed Experiment 5 `workload.json` reused by recorded SHA-256 (`sha256:bb412ddc…`), keeping H1-parity claims comparable across 5 and 5b.

## Risks / Trade-offs

- [MPS sampler accuracy varies with macOS memory pressure] → record sampler method per cell in the manifest; treat G5 as slope-based (trend over 1,000-request windows) rather than absolute-sample-based.
- [1,000+ requests × 4 cells is hours of machine time] → checkpoint per request batch; `--resume` bounds loss to one batch; run on mains power with the machine otherwise idle, as in Experiment 5.
- [Worker prototype proves the protocol, not production wiring] → stated in results interpretation; promotion requires the follow-up OpenSpec to design production lifecycle (spawn policy, restart backoff, idle timeout tuning) against real traffic.
- [Gate G4 bound could look post-hoc generous vs Experiment 5's 2.0×] → the protocol's pre-registration section states the absolute-bound rationale before execution; the summary must report both the absolute plateau and the ratio to W1 so readers can apply either lens.

## Migration Plan

None: experiment-only change, no production surface. Rollback is deleting the experiment directory.

## Open Questions

- Exact request-batch checkpoint granularity (100 vs 250 requests) — tuning detail, safe to fix at harness-build time.
- Whether the idle-expiry probe sweeps one timeout value or two — recorded in the protocol before the run; does not affect gate structure.
