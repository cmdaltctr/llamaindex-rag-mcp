# ADR-029: Disable CoreML for Reranker — Silent Fallback Lesson

**Date:** 2026-07-31
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

ADR-021 (June 23) added the CoreML Execution Provider to the reranker,
claiming a 10× speedup. During Experiment 15 (July 31), testing the
gte-reranker swap, the CoreML provider was found to be **silently failing
on every single inference call** — the reranker had not actually been
reranking since ADR-021 was implemented, a period of **5 weeks**.

### What CoreML is good at

CoreML is Apple's hardware-accelerated ML framework. It routes ONNX graph
nodes to the Apple Neural Engine and GPU, which are significantly faster
than CPU for compatible workloads. CoreML excels at:

- **Fixed-input models** — image classifiers (224×224 pixels), object
  detectors, audio classifiers. The input shape never changes between calls.
- **Compiled graph models** — CoreML compiles the ONNX graph into an
  optimised `.mlmodel` package at load time, then runs it on the ANE.

### Why it breaks for the reranker

The cross-encoder reranker scores query-document pairs. Each batch of pairs
has a **different sequence length** because documents vary in length and the
tokenizer pads to the longest pair in the batch:

```
Batch 1: 32 pairs, longest = 47 tokens  → shape (32, 47)
Batch 2: 32 pairs, longest = 203 tokens → shape (32, 203)
Batch 3: 32 pairs, longest = 89 tokens  → shape (32, 89)
```

CoreML compiles the graph for the first input shape and **cannot resize**
when the shape changes. Every call after the first fails:

```
Error executing model: Error in dynamically resizing for sequence length (error: -7)
```

This is a fundamental limitation of CoreML's graph compilation model, not an
ONNX Runtime bug. CoreML expects fixed shapes; NLP cross-encoders produce
dynamic shapes.

### How the failure went unnoticed for 5 weeks

The reranker's graceful fallback (designed for transient network errors and
missing model files) caught the CoreML exception and returned un-reranked
results with only a warning log:

```python
except Exception as exc:
    logger.warning("Reranker inference failed: %s. Returning un-reranked results.", exc)
    for r in results:
        r["_reranked"] = False
    return results[:top_k]
```

The warning was logged to stderr, which in production goes to the MCP
protocol channel (invisible to the user). In experiments, the warning
appeared in log files but was not flagged as a blocking error. The
`_reranked: False` metadata was present on every result but was never
checked by the evaluation pipeline.

### Impact on prior experiments

| Experiment | Date | Reranker status | Impact |
| --- | --- | --- | --- |
| Exp 10 | May 31 | ✅ Working (CPU, pre-ADR-021) | Valid — reranker genuinely degrades |
| Exp 11 | Jun 20 | ✅ Working (CPU, pre-ADR-021) | Valid |
| **ADR-021** | **Jun 23** | **CoreML introduced** | **Broke reranker silently** |
| Exp 12 | Jun 29 | ❌ Broken (CoreML) | Rerank-on cells invalid; rerank-off cells valid |
| Exp 9a-rerun | Jun 29 | ❌ Broken (CoreML) | Same — rerank-on cells invalid |
| Exp 13 | Jun 29 | ❌ Broken (CoreML) | Rerank-on cells invalid |
| Exp 15 | Jul 31 | ✅ Fixed (CPU, this ADR) | Valid — confirms Exp 10's finding |

Key decisions (ADR-019 disable reranker, Exp 12 hybrid promotion) were based
on rerank-off cells, which were unaffected. No production decision was
compromised, but ~3 weeks of reranker-on experiment cells were wasted.

### ADR-021's "10× speedup" was real but misattributed

The speedup came from three other fixes in ADR-021, not CoreML:

| Fix | Contribution | CoreML? |
| --- | --- | --- |
| Batched inference (32/batch) | Major — reduced memory thrash | No |
| Reduced fetch_k (500→150) | Major — 3.3× fewer candidates | No |
| max_length 512→256 | Moderate — 2× fewer tokens/pair | No |
| CoreML provider | **Negative** — added exception overhead | Yes |

CoreML actually made things **slower** by adding exception creation, stack
unwinding, and warning logging to every batch. The "10× speedup" would have
been even faster without CoreML in the loop.

## Decision

### 1. Default to CPUExecutionProvider

CoreML is disabled by default for the reranker. An env var override exists
for future testing:

```python
_onnx_provider = os.getenv("RERANK_ONNX_PROVIDER", "cpu")
if _onnx_provider == "coreml" and "CoreMLExecutionProvider" in available:
    providers = ["CoreMLExecutionProvider", "CPUExecutionProvider"]
else:
    providers = ["CPUExecutionProvider"]
```

CoreML may be re-enabled in the future if:
- ONNX Runtime adds dynamic shape support for CoreML, OR
- The reranker is refactored to use fixed-length padding (pad every batch
  to `max_length` regardless of actual content length), OR
- A different model with fixed input shapes is adopted

### 2. Model-aware max_length cap

The tokenizer `max_length` is now capped at the model's own
`model_max_length` to prevent ONNX dimension mismatch errors:

```python
model_max = getattr(self._tokenizer, "model_max_length", TOKENIZER_MAX_LENGTH)
if not isinstance(model_max, int) or model_max > 100000:
    model_max = TOKENIZER_MAX_LENGTH
self._effective_max_length = min(TOKENIZER_MAX_LENGTH, model_max)
```

This prevents the `max_length=2048` vs MiniLM's 512-token position embedding
mismatch discovered during Exp 15.

### 3. Non-silent fallback (refactor reminder)

The current silent fallback should be refactored in the planned retrieval
refactor (Phase 1 of the refactor proposal). The fallback was designed for
transient failures (network timeouts), not for persistent configuration
errors (wrong provider). Proposed changes for the refactor:

- **Distinguish transient vs persistent failures.** A provider that fails
  on every call is a configuration error, not a transient issue. After N
  consecutive failures with the same error, escalate from warning to error.
- **Surface `_reranked: False` to the caller.** The retrieval layer should
  check the reranker's success flag and include it in diagnostics when
  `include_diagnostics=True`.
- **Log provider failures at ERROR level, not WARNING.** A silently failing
  provider is a production incident, not a transient hiccup.

These changes are deferred to the refactor to avoid scope creep in the
current change.

**Resolved by:** OpenSpec change `silent-failure-audit-and-guards` (2026-08).
All three bullets shipped: consecutive same-signature failures are tracked
module-wide, `rerank_reason` surfaces the reranker's own failure text under
`include_diagnostics=True`, and the log level escalates. The third bullet
shipped as **thresholded** escalation (WARNING below 3 consecutive
same-signature failures, ERROR at or above), not the unconditional ERROR the
bullet's wording implies literally. Unconditional ERROR would fire on the
single transient network timeout the reranker is explicitly designed to
retry, training operators to ignore the level meant to mean "incident" —
thresholded escalation is the synthesis of this decision's first bullet
("distinguish transient vs persistent failures") and third bullet, not a
literal reading of the third alone. See that change's `design.md` for the
full rationale.

## Consequences

### Positive

- The reranker now **actually works** for the first time since June 23
- CPU-only inference is deterministic (no CoreML float precision differences)
- The env var override (`RERANK_ONNX_PROVIDER=coreml`) allows future testing
  without code changes
- Model-aware `max_length` prevents dimension mismatch errors for any model

### Negative

- CPU-only inference is slower than a hypothetical working CoreML path
  would be. MiniLM takes ~5s/query on CPU with 30 candidates; CoreML (if it
  worked) could potentially be 2-5× faster.
- The graceful fallback remains silent until the refactor. Future provider
  or model issues could go unnoticed again if the warning logs aren't
  monitored.

### Neutral

- Non-Apple platforms (Linux CI, Windows) see no change — they were already
  CPU-only.
- The `RERANK_ONNX_PROVIDER` env var defaults to `"cpu"` but is overridable,
  so operators who want to experiment with CoreML (or future providers like
  Metal) can do so without code changes.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Remove CoreML entirely** (no env var) | Too rigid. Future CoreML versions may support dynamic shapes. The env var costs nothing and preserves the option. |
| **Pad all batches to `max_length`** (fixed shape for CoreML) | Wastes compute — most pairs are <100 tokens but would be padded to 512. The padding overhead negates CoreML's speed advantage. |
| **Use Metal EP instead of CoreML** | Metal EP targets GPU, not Neural Engine. Less tested for NLP workloads in ONNX Runtime. Same dynamic shape limitation likely applies. |
| **Keep CoreML but catch and retry on CPU** | Adds complexity for no benefit — the first batch always fails, so every query pays the exception overhead. Better to skip CoreML entirely. |

## References

- ADR-005: Cross-Encoder Reranker with ONNX Runtime (original adoption)
- ADR-021: Reranker Inference Optimisation (introduced CoreML — this ADR partially supersedes Fix 1)
- ADR-028: Swap Default Reranker to gte-reranker-modernbert-base (Rejected — Exp 15 showed no benefit)
- Experiment 10: `experiments/10-reranker-technical-workload-calibration-2026-05-31/` (valid, pre-CoreML)
- Experiment 15: `experiments/15-gte-reranker-swap-2026-07-31/` (discovered and fixed the CoreML bug)
- ONNX Runtime CoreML EP docs: https://onnxruntime.ai/docs/execution-providers/CoreML-ExecutionProvider.html
- Refactor proposal: `docs/brainstorm/refactor-proposal/PROPOSAL.md` (Phase 1 includes reranker refactor)
