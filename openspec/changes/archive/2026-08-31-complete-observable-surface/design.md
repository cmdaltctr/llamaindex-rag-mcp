## Context

`search()` already threads an out-parameter through the hybrid path:
`_hybrid_query_rows` takes `sparse_report: dict | None` and the native sparse
runner writes the backend that actually served the query into it. That idiom
exists because the sparse backend is decided inside a nested call whose return
value is a fixed row shape. Stage timing has the same shape of problem, and can
reuse the same solution rather than inventing a second one.

Dense and sparse retrieval run concurrently under a `ThreadPoolExecutor` with
two workers in hybrid mode. Their wall-clock durations therefore overlap, unlike
the ingest pipeline's timing buckets, which are sequential and sum to the total.

`_dense_query_rows` and `rrf_with_metadata` are resolved through
`core/retrieval/registry.py`, which stores `"module:attr"` import strings and
enforces no signature. `tests/test_registry_contract.py` checks only that every
registered name resolves. A keyword-only parameter with a default is therefore
safe to add.

Both transports already pass core result rows through untouched: the MCP handler
returns the list directly, and the CLI JSON path calls `json.dumps(results)`.
`search-diagnostics-surface` pins this in its "Core diagnostic fields evolve"
scenario. A new diagnostic key needs no transport edit.

`transports/mcp.py` is at 495 of the 500-line ceiling enforced by
`tests/test_file_size_ceiling.py`.

## Goals / Non-Goals

**Goals:**

- The OpenAPI contract declares every field the shipped transports expose.
- A future field addition fails the build unless the contract is updated in the
  same change, without anyone editing a list.
- A caller who enables diagnostics learns what each retrieval stage cost.
- Absence of a stage in the timing payload is unambiguous.
- Zero change to default response shape, ranking, or scores.

**Non-Goals:**

- Implementing the REST transport. `transports/api/` stays contract-only.
- A total-latency figure. Overlapping concurrent stages make one misleading;
  the caller can measure end-to-end wall time itself.
- Timing for ingestion. That already exists.
- Aggregation, percentiles, histograms, or export to a metrics backend. This
  change reports per-query stage durations to the caller who asked, nothing
  more.
- Splitting `transports/mcp.py`. Tracked separately; this change adds no lines
  to it.

## Decisions

### D1 — Stage timing travels in a report dict, not the return value

`_dense_query_rows` and the sparse runners return a fixed row-list shape that
the fusion stage consumes. Widening that to a tuple would ripple through the
registry contract, both sparse backends, and every test that calls a runner
directly.

Instead, pass an optional `timing_report: dict | None` down the same path
`sparse_report` already travels. Each stage writes its own key. `search()` owns
the dict and attaches it to result rows at the end.

**Alternative rejected:** a module-level or context-local accumulator. It would
avoid the parameter but make concurrent searches in one process share state,
which the `ThreadPoolExecutor` guarantees will happen.

### D2 — Report per-stage durations, never a total

In hybrid mode the dense and sparse stages run concurrently, so
`dense_seconds + sparse_seconds` exceeds the wall time actually spent. Emitting
a `total_seconds` would invite exactly the wrong arithmetic.

The spec therefore requires per-stage durations only. The design records the
concurrency explicitly so a reader of the payload is not misled: these are
"how long did this stage take", not "how the query's wall time divides up".

**Consequence:** the payload cannot answer "where did the time go" for a hybrid
query as directly as the ingest timings answer it for a source. It can answer
"is the reranker the expensive part", which is the question that actually
prompted this work.

### D3 — Omission means the stage did not run

Zero is a legitimate duration for a stage that ran and was fast, particularly a
cached embedding. Reporting a stage that did not run as `0.0` would make those
two states indistinguishable.

Absent key means the stage did not execute. This matches the rule
`ReplaceSourceOutcome.norm_band` already follows, where `None` means the guard
was disabled rather than that the norms were zero.

### D4 — Embedding timing wraps the cache lookup, not the provider call

`_embed_query` consults a 128-entry LRU before calling the provider. Timing the
provider call alone would report nothing on a cache hit and hide the cache's
value. Timing the whole `_embed_query` call reports a near-zero duration on a
hit and the real cost on a miss, which is the distinction an operator wants.

### D5 — A stage that runs twice reports the sum, not the last run

When a hybrid rerank fails, `search()` re-runs `_hybrid_query_rows` with the
dense threshold restored (`pipeline.py:325`). Dense, sparse and fusion then each
execute twice while rerank executes once.

**Accumulate.** Each stage key holds the total time the query spent in that
stage across every execution.

An earlier draft of this design chose last-write-wins. That was wrong: it would
emit attempt two's retrieval durations beside attempt one's rerank duration, a
mapping describing no single execution and summing to less than the query
actually cost. It also contradicted this change's own requirement to report
every stage that ran, since attempt one's stages ran and would have been
discarded.

Accumulation keeps one clear meaning for every key — "time this query spent
here" — which holds whether a stage ran once or twice, and needs no special
case in the payload.

**Alternative rejected:** attempt-scoped nesting
(`{"attempt_1": {...}, "attempt_2": {...}}`). It is more precise, but it makes
every consumer handle a nested shape for a path that is rare by design, and the
common single-attempt query would carry a pointless `attempt_1` wrapper.

**Discoverability:** a caller who needs to know a re-query happened can read
`rerank_reason`, which already reports the reranker's failure. The timing
payload does not need to encode it a second time.

### D6 — The conformance check derives fields, and excludes only structure

The check builds the implemented surface from the code:

- **Search parameters** come from `inspect.signature(search_documents)`, giving
  names and defaults.
- **Listing keys** come from calling `list_documents` against a stub store that
  returns one row, then reading the result dict's keys. This is the same stubbing
  pattern `tests/test_orphaned_source_visibility.py` already uses.

It then reads `components.schemas.SearchRequest.properties` and
`components.schemas.DocumentInfo.properties` from `openapi.yaml` and asserts no
implemented field is missing.

One maintained set remains: parameters that are structurally not body fields.
Today that set has exactly one member, `collection`, which is a path parameter
in `/v1/collections/{collection}/search` and so belongs in the path rather than
`SearchRequest`. The exclusion set is about REST structure, not about which
fields exist, so it changes only when the URL design changes. The field lists
themselves are never maintained.

Verified against the current tree: the implemented parameter set is
`{query, top_k, similarity_threshold, rerank, hybrid, diagnostics, collection,
metadata_filter}` and `SearchRequest` declares all of them except `diagnostics`
and `collection`. With `collection` excluded structurally, the check fails
naming `diagnostics` alone, which is the intended red state.

**Alternative rejected:** asserting a hardcoded expected field list. It would
pass today and rot the first time a field is added, which is the failure this
change exists to prevent.

**Search results are checked in both modes.** The result surface is derived
twice: once from a default search and once with diagnostics enabled. The default
keys must be declared and required; the diagnostics-only keys must be declared
and not required. Without the two-mode derivation the check would either miss
the diagnostic fields entirely or wrongly demand them on every response.

**Accepted limitation:** the check verifies presence and defaults, not type
fidelity. A field declared with the wrong type still passes. Type checking would
require a mapping from Python annotations to OpenAPI types that is itself a
maintained list, trading one rot surface for another. Presence is where the
observed drift happened.

**Accepted limitation, stated honestly:** the listing and result surfaces are
derived by executing the code against a stub, so they expose the keys that
*those* executions produce. A future key emitted only on a branch the stub does
not reach would be missed. The stub therefore uses a fully-populated lineage row
— the shape production ingestion always writes — and the proposal claims the
check catches *unconditional* new fields automatically, not every conceivable
conditional one.

### D7 — Default comparison has four explicit rules

`openapi.yaml` currently declares no `default` key on any `SearchRequest`
property. A check written as `schema.get("default") == python_default` would
therefore compare `None` against `None` and pass `top_k`,
`similarity_threshold`, `rerank` and `hybrid` for entirely the wrong reason,
while failing `diagnostics` because `False != None`. It would be a check that
appears to work.

The rules, using `"default" in schema` rather than `.get`:

1. **Required parameter** (no Python default, e.g. `query`): the schema MUST
   list it under `required` and MUST NOT declare a `default`.
2. **Concrete Python default** (e.g. `diagnostics=False`): the schema MUST
   declare `default` and it MUST equal the Python value.
3a. **`None` meaning profile-resolved** (`top_k`, `similarity_threshold`,
    `rerank`, `hybrid`): the schema MUST NOT declare a `default`, and its
    `description` MUST say the value is resolved from the collection profile
    when omitted. A description asserting a concrete default is a defect.
3b. **`None` meaning absent, not resolved** (`metadata_filter`): the schema
    MUST NOT declare a `default`, and its `description` MUST NOT assert a
    concrete default. It must not claim profile resolution, because omitting
    the parameter means "no filter", which is not a profile decision.
4. **Explicit `default: null`**: rejected. It is indistinguishable from rule 3a
   to a reader and adds nothing, so the check treats a declared null default as
   a failure with a message pointing at rule 3a.

Rules 3a and 3b both start from a `None` Python default, and
`inspect.signature` cannot tell the two meanings apart on its own. The check
therefore carries one small semantic set: the names of the profile-resolved
parameters. That set changes only when a new profile-resolved parameter is
introduced, so the "no maintained field lists" property is preserved for
unconditional fields. This mirrors D6's structural exclusion of `collection`,
which is likewise a maintained set about REST structure rather than about
which fields exist.

Rule 3a is why `similarity_threshold`'s current description ("default 0.0 — no
filtering") has to change: the Python default is `None`, and 0.0 is merely what
the `documents` profile happens to resolve to today.

### D8 — Timings ride on rows, and a query with no rows reports none

The payload attaches to each result row, matching every existing per-row
diagnostic. A query that returns nothing therefore reports no timings, including
the early return when the collection is empty (`pipeline.py:244`) and the case
where thresholding removes every candidate.

That is a real gap: a slow query returning nothing is exactly one an operator
might want to time. It is accepted here rather than fixed, because the
alternative is a response envelope wrapping the result list, which changes the
return type of `search()` for every caller and every transport — a far larger
change than this one, and one that would undo the "no transport change"
property.

The limitation is written into the spec so it is a known boundary rather than a
surprise. If timing an empty query becomes a real need, an envelope is the
follow-up, and it should be proposed on its own terms.

### D9 — The cache test counts provider calls, it does not compare durations

Asserting that the second embedding of an identical query is *faster* than the
first compares two wall-clock measurements on a shared CI runner. That is
flaky by construction: a scheduler hiccup on the second call inverts it.

The cache-hit scenario is instead verified by counting calls to the embedding
provider — one call across two identical queries proves the cache served the
second. Where a duration assertion is genuinely wanted, inject a controlled
clock rather than measuring real time.

This follows the repository's rule that a test must fail when the behaviour it
covers breaks, and must not fail otherwise.

### D10 — No transport changes in either thread

Thread A touches `openapi.yaml` and a new test module. Thread B touches
`core/retrieval/`. Neither adds a line to `transports/mcp.py`, which has five
lines of headroom. This is a constraint the design satisfies rather than a
coincidence: if timing had needed a transport parameter, the module split would
have had to land first.

## Risks / Trade-offs

**Timing overhead on the query path.** `perf_counter()` is a nanosecond-scale
monotonic read. Calls are per stage, not per candidate row, so a query adds at
most ten reads. Negligible against a vector search, and the calls are taken
unconditionally so enabling diagnostics does not change the code path being
measured.

**Measuring only under diagnostics would be cheaper but less honest.** Taking
the timestamps unconditionally and only *reporting* them under the flag means
the measured path is the same path production runs. A flag-gated measurement
would time a different code path from the default one.

**The concurrency caveat has to be communicated.** A payload with
`dense_seconds` and `sparse_seconds` invites addition. The spec forbids a total
and the design states why; the field documentation should repeat it, because
that is where a caller will read it.

**The conformance check couples a test to `openapi.yaml`'s structure.**
Renaming `SearchRequest` or `DocumentInfo` breaks the check. That is acceptable:
the schema names are part of a versioned published contract, and a rename is a
contract change that should be deliberate.

**Deriving listing keys requires constructing a store stub in a test.** If
`list_documents` later gains a code path that emits keys conditionally, the stub
may exercise only one branch and the check could miss a field. Mitigated by
having the stub return a row that exercises the populated-lineage path, which is
the one production ingestion always produces.
