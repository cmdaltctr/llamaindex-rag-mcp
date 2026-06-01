## Context

ADR-019 superseded ADR-018 by changing the safe default for the current cross-encoder reranker from default-on to default-off for technical workloads. `config.py` now defines `RERANK_ENABLED=false`, `RERANK_ENABLED_FOR_SEMANTIC=true`, and `HARD_TECHNICAL_THRESHOLD=0.3`, but the latter two are only policy knobs: `retrieval.py` still only checks the explicit/default `rerank` value. This creates a mismatch between configuration comments, ADR-019's intended policy, and actual runtime behaviour.

The current public surfaces also have historical defaults that may bypass config intent. In particular, MCP/server and CLI surfaces need to follow `config.py` as the single source of truth rather than hardcoded default rerank behaviour.

## Goals / Non-Goals

**Goals:**

- Implement a single policy resolver for effective rerank behaviour.
- Preserve explicit caller intent: `rerank=True` forces reranking, `rerank=False` disables reranking.
- Make omitted/`None` rerank follow `config.py` defaults.
- Use `RERANK_ENABLED_FOR_SEMANTIC` and `HARD_TECHNICAL_THRESHOLD` only when no explicit caller override is supplied.
- Add a deterministic technical-query classifier sufficient for policy decisions and tests.
- Update MCP/CLI defaults and docs so they no longer imply automatic semantic reranking unless the policy resolver implements it.

**Non-Goals:**

- Do not replace the reranker model.
- Do not recalibrate `HARD_TECHNICAL_THRESHOLD=0.3`; it remains a conservative heuristic from ADR-019.
- Do not change `RERANK_MAX_FETCH` or `RERANK_FETCH_MULTIPLIER` semantics.
- Do not implement corpus-wide offline profiling; use lightweight query/workload metadata available at search time.

## Decisions

### Decision 1: centralise rerank policy resolution

Add a helper in retrieval code, e.g. `_resolve_rerank_policy(...)`, that returns the effective boolean rerank decision and optionally a reason string for diagnostics. All search entry points should use this helper.

Rationale: keeping this in one place avoids drift between direct retrieval, MCP, and CLI behaviour.

### Decision 2: use tri-state rerank at public boundaries where needed

Where a caller can omit rerank, use `rerank: bool | None = None` internally:

- `True`: force rerank.
- `False`: force no rerank.
- `None`: apply config/policy defaults.

Existing APIs may continue accepting booleans, but default values should represent omission and must route through the resolver.

### Decision 3: classify technical intent using existing identifier rules

Reuse the identifier-heavy rules used by Experiment 9a/10 where practical: backticks, slash paths, dotted paths, camelCase, snake_case, all-caps constants, exception/error tokens, version strings, and explicit package/API names. The resolver can classify a single query as technical or accept workload/corpus metadata when available.

For single-query search, the default heuristic is:

- if the query is identifier-heavy and `RERANK_ENABLED` is false, do not rerank;
- if the query is non-technical and `RERANK_ENABLED_FOR_SEMANTIC` is true, rerank may be enabled by policy;
- if the technical fraction is known and is `>= HARD_TECHNICAL_THRESHOLD`, do not enable policy reranking.

### Decision 4: diagnostics should expose the effective decision

When diagnostics are requested, include whether reranking was explicit or policy-derived and why it was enabled/disabled. This is important because ADR-019 distinguishes explicit opt-in from automatic semantic override.

## Risks / Trade-offs

- **Risk: heuristic misclassification** → Mitigation: explicit `rerank=True`/`False` always overrides policy; diagnostics expose the decision.
- **Risk: surprising semantic reranking latency** → Mitigation: keep global `RERANK_ENABLED=false`; semantic override can be disabled via `RERANK_ENABLED_FOR_SEMANTIC=false`.
- **Risk: public API compatibility** → Mitigation: maintain boolean compatibility and only change omitted/default behaviour.
- **Risk: threshold not calibrated** → Mitigation: document `HARD_TECHNICAL_THRESHOLD=0.3` as a heuristic and add follow-up experiment for calibration.

## Migration Plan

1. Add policy resolver and tests without changing explicit `rerank=True`/`False` behaviour.
2. Update direct retrieval defaults to use the resolver.
3. Update MCP/server and CLI defaults to represent omitted rerank and follow config.
4. Update `.env.example` and inline comments.
5. Run existing retrieval, MCP, and CLI tests plus new policy tests.

Rollback: set `RERANK_ENABLED=true` or pass explicit `rerank=True` at call sites to restore reranker-on behaviour while leaving the policy code in place.
