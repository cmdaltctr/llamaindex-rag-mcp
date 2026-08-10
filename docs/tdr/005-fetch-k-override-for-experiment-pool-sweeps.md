# TDR-005: fetch_k override parameter for experiment pool-size sweeps

**Date:** 2026-06-29
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari with AI agent
**Tags:** retrieval | reranker | experiment | fetch-pool

## Context

Experiment 10 ("Reranker Technical Workload Calibration") was designed to
answer a simple question: *does a larger reranker candidate pool improve
retrieval quality on technical workloads?*

It labelled three pool sizes — `RERANK_MAX_FETCH` = 50, 200, 500 — and ran
them on the FreshStack LangChain corpus. But all three cells produced
**identical** metrics (Coverage@20 = 0.540, Recall@50 = 0.354, Hit@10 = 0.596).

### Root cause

The effective candidate pool is computed by a formula:

```python
fetch_k = max(RERANK_MAX_FETCH, top_k * RERANK_FETCH_MULTIPLIER)
```

Experiment 10 ran at `top_k=50` with the pre-ADR-021 default
`RERANK_FETCH_MULTIPLIER=10`. So:

```text
max(50,  50 × 10) = 500
max(200, 50 × 10) = 500
max(500, 50 × 10) = 500
```

All three labelled pool sizes collapsed to the same effective `fetch_k=500`.
The experiment answered "does pool size matter at 500?" three times, not
"does a smaller pool (50) outperform a larger one (500)?"

ADR-019 documents this confound explicitly. A corrected experiment (10b)
is required.

## Decision

Add a `fetch_k_override: int | None = None` parameter to
`_resolve_fetch_k()` and a `fetch_k: int | None = None` parameter to
`search()` in `retrieval.py`. When set, the override bypasses the
`max()` formula and uses the provided value directly (after clamping to
collection size).

```python
# retrieval.py — _resolve_fetch_k with override


def _resolve_fetch_k(
    top_k: int,
    rerank: bool,
    collection_count: int,
    fetch_k_override: int | None = None,  # ← NEW
) -> int:
    if fetch_k_override is not None:
        fetch_k = fetch_k_override  # ← bypass formula
    elif rerank:
        from . import config as _config

        fetch_k = max(
            _config.RERANK_MAX_FETCH,
            top_k * _config.RERANK_FETCH_MULTIPLIER,
        )
    else:
        fetch_k = top_k

    if collection_count > 0:
        fetch_k = min(fetch_k, collection_count)
    return max(fetch_k, 1)
```

```python
# retrieval.py — search() passes the override through

def search(
    ...,
    fetch_k: int | None = None,             # ← NEW
) -> list[dict]:
    ...
    resolved_fetch_k = _resolve_fetch_k(
        top_k, effective_rerank, collection.count(),
        fetch_k_override=fetch_k,           # ← pass through
    )
```

The override is still clamped to `collection.count()` and floored at 1,
matching the existing safety constraints.

**The reranker (`reranker.py`) does not need modification.** It processes
whatever candidates it receives — the pool size is controlled entirely by
how many candidates the retrieval step fetches from ChromaDB.

## Consequences

### Positive

- Experiment runners can now test genuinely distinct pool sizes (50, 100,
  200, 500) without the formula collapsing them
- The parameter is purely additive: defaults to `None`, so every existing
  caller (MCP server, CLI, production code) gets the old formula-computed
  behaviour unchanged
- Regression test `test_override_distinct_values_no_collapse` directly
  encodes the Exp 10 confound as a permanent guard

### Negative

- One more parameter on `search()` — the signature is already long (10
  params). This is a readability trade-off accepted for experiment utility.
- No type-level enforcement that `fetch_k` is only used with `rerank=True`.
  A caller passing `fetch_k=500` with `rerank=False` would fetch 500
  candidates and return only `top_k` without reranking — wasteful but not
  incorrect.

### Neutral

- The override does not appear in `config.py`, `.env.example`, or the CLI.
  It is a Python-API-only parameter intended for experiment runners.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Vary `RERANK_FETCH_MULTIPLIER` directly (1, 2, 4, 10 for `top_k=50`) | Couples pool size to the multiplier, making results harder to reason about. The multiplier also interacts with production `top_k=10` differently, confusing the extrapolation. |
| Lower `top_k` to 20 with `multiplier=1` | Changes the retrieval shape from prior experiments, making results non-comparable with Exp 9a/10 at `top_k=50`. |
| Add a `--fetch-k-override` CLI flag | The CLI is a thin wrapper; the parameter belongs on `search()` so experiment runners (which call `search()` directly) can use it without CLI parsing. |
| Modify `reranker.py` to accept `fetch_k` | The reranker doesn't compute `fetch_k` — `_resolve_fetch_k()` does. The reranker processes whatever it receives. Adding a parameter there would be dead code. |

## How to Recognise / Handle This Again

### Symptom: identical metrics across "different" pool sizes

If an experiment reports the same Coverage@20, Recall@50, or Hit@10 across
cells that are supposed to have different pool sizes, the formula is
collapsing them.

### Diagnostic

```python
from rag_mcp.retrieval import _resolve_fetch_k

# Check whether labelled pool sizes are genuinely distinct:
for label in (50, 100, 200, 500):
    actual = _resolve_fetch_k(top_k=50, rerank=True, collection_count=10000, fetch_k_override=label)
    print(f"label={label}, actual={actual}")

# Without the override (the old path):
for label in (50, 200, 500):
    actual = _resolve_fetch_k(top_k=50, rerank=True, collection_count=10000)
    print(f"formula_computed={actual}")  # All print 150 with post-ADR-021 config
```

### Recovery

Use `fetch_k=` parameter on `search()` or `fetch_k_override=` on
`_resolve_fetch_k()` to bypass the formula:

```python
results = retrieval.search(
    query="example",
    top_k=50,
    rerank=True,
    fetch_k=200,  # ← genuinely 200, not collapsed
)
```

## Revisit Triggers

- If `_resolve_fetch_k()` is refactored or removed, update or supersede
  this TDR.
- If a future ADR changes the fetch-size formula (e.g., removes the
  `max()` in favour of a different computation), verify the override
  still makes sense.
- If the parameter is adopted by production callers (not just
  experiments), promote it to `config.py` as an env-var-backed setting
  and write an ADR.

## References

- `src/rag_mcp/retrieval.py` — `_resolve_fetch_k()` and `search()`
- `tests/test_rerank_fetch_pool.py` — regression tests including
  `test_override_distinct_values_no_collapse`
- ADR-019: Disable Reranker for Technical Workloads
- ADR-021: Reranker Inference Optimisation (CoreML, Batching, Reduced Fetch Pool)
- OpenSpec change: `calibrate-rag-retrieval-defaults`
- Experiment 10 protocol: `experiments/10-reranker-technical-workload-calibration-2026-05-31/protocol.md`
