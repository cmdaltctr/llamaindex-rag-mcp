## Context

See `proposal.md` for the motivation and ordered-change context.

Core retrieval owns the complete diagnostics lifecycle. Its `search()` entry
point accepts `include_diagnostics=False`
(`src/rag_mcp/core/retrieval/pipeline.py:117-126`). Hybrid and dense query paths
receive that value (`pipeline.py:271,283`). The pipeline attaches policy,
threshold, reranker, and effective sparse-backend details when requested
(`pipeline.py:347-365`). It strips internal rank fields when diagnostics are
disabled (`pipeline.py:101-114,367-368`).

The MCP tool delegates through `asyncio.to_thread`, but does not pass the flag
(`src/rag_mcp/transports/mcp.py:178-186,230-241`). The CLI has the same gap
(`src/rag_mcp/transports/cli/search.py:21-42,59-67`). Its JSON path already
serialises the complete result dictionary (`cli/search.py:86-88`). The Rich
table reads only fixed display keys (`cli/search.py:90-103`).

The design must preserve architecture invariant 3 in `AGENTS.md`: transports
validate inputs, delegate to core, and format outputs. The MCP tool must also
retain its never-raise contract and existing `ToolAnnotations`.

## Goals / Non-Goals

**Goals:**

- Add one default-off diagnostics control to each existing search transport.
- Map both controls directly to the existing core flag.
- Preserve the complete core-produced diagnostics in MCP and CLI JSON results.
- Test the transport boundary without duplicating core retrieval tests.

**Non-Goals:**

- Change core retrieval code, diagnostic content, or defaults.
- Add diagnostic fields or transport-owned diagnostic formatting.
- Change ranking, filtering, hybrid retrieval, or reranker behaviour.
- Change the REST/OpenAPI contract in this implementation.

## Decisions

### D1. Each public control maps to the existing core flag

The MCP tool gains `diagnostics: bool = False`. The CLI gains a boolean
`--diagnostics` option. Each transport passes its value as
`include_diagnostics=<value>` on every search call.

Passing the value explicitly makes both default and opt-in behaviour visible to
transport tests. It also prevents a later core default change from altering the
public transport default.

**Alternative considered:** expose `include_diagnostics` as the public MCP name.
The shorter `diagnostics` name matches the user-facing CLI flag and keeps the
core implementation term inside the delegation boundary.

### D2. Diagnostics remain off unless a caller opts in

Diagnostics can add internal identifiers, rank positions, scores, and policy
reasons to every result. MCP clients often place the complete response in model
context. The default remains `false` to preserve the current response size and
shape.

**Alternative considered:** enable diagnostics by default. This would increase
client context and change every existing response without an explicit request.

### D3. Existing output formatters need no diagnostic branch

The MCP handler already returns core result dictionaries. CLI JSON already uses
`json.dumps(results)`, so it preserves extra fields without new formatting. The
Rich table selects `score`, `source`, `page_label`, and `text`; extra keys are
ignored safely.

The implementation adds no table columns. Diagnostics remain available through
JSON for inspection and scripts.

**Alternative considered:** add diagnostic columns to the Rich table. The field
set is wider than a terminal table and varies by retrieval path. This would add
presentation logic outside the requested passthrough.

### D4. Transport tests prove both forwarding and output shape

The MCP test spies on retrieval and asserts that `diagnostics: true` reaches
`include_diagnostics=True`. Existing exact-call assertions must include the new
default keyword.

The CLI test uses controlled search results for both flag states. It asserts
the forwarded boolean, parses stdout as JSON, and checks that diagnostic keys
appear only for the enabled case. This follows the keyword-spy pattern at
`tests/test_experiment_14_harness.py:217-225`.

Core semantics remain covered by `tests/test_retrieval.py:423-474` and
`tests/test_rerank_policy.py:305-342`. Transport tests do not repeat ranking or
reranker assertions.

**Alternative considered:** rely only on core tests. They cannot detect a
missing MCP parameter or CLI flag because neither transport currently exposes
the core control.

### D5. MCP failure and annotation behaviour stay unchanged

The new argument enters the existing nested `try` and outer exception handling.
No exception branch changes. `ToolAnnotations(read_only_hint=True,
destructive_hint=False)` remains attached without modification.

**Alternative considered:** add diagnostics-specific exception handling. The
flag triggers existing core behaviour and introduces no new failure category.

### D6. REST parity is deferred but recorded

`transports/api/openapi.yaml` describes a future REST search operation. This
change does not edit that contract because REST/OpenAPI surface changes are out
of scope. Before a REST runtime is built, its implementer must decide whether
the search operation gains an optional, default-off diagnostics parameter.
Recording this gap prevents the future transport from silently omitting a
capability available through MCP and CLI.

### D7. `mcp.py` is at the 500-line ceiling

`src/rag_mcp/transports/mcp.py` is exactly 500 lines.
`tests/test_file_size_ceiling.py` fails any file over that limit. Tasks 1.1
and 1.2 add lines to this file, so the change frees the same number of lines
inside it by compressing the `search_documents` docstring. A package split of
`transports/mcp.py` stays out of scope; it would deserve its own change.

## Risks / Trade-offs

- **Enabled responses can be larger.** → Keep both public controls default-off
  and document their debugging purpose.
- **Exact mock-call tests will fail after the new keyword is always passed.** →
  Update existing expectations and add explicit default-state assertions.
- **A stub could return diagnostic keys without proving passthrough.** → Assert
  the `include_diagnostics` call argument as well as parsed output.
- **Core diagnostics can evolve.** → Keep transports schema-free and test a
  representative set of existing keys rather than generating fields locally.
- **MCP coverage can regress through a small branch change.** → Run the targeted
  MCP suite with coverage and preserve the 95% module floor.

## Migration Plan

1. Free the needed lines in `mcp.py` per D7, then add the MCP parameter and
   pass it to core retrieval.
2. Add the CLI flag and pass it to core retrieval.
3. Update exact-call tests for the explicit default.
4. Add enabled and disabled transport tests.
5. Update both user guides.
6. Run targeted tests and strict OpenSpec validation.

No data or configuration migration is required. Rollback removes the optional
controls and their keyword forwarding. Existing callers remain unaffected
because the default is unchanged.

## Open Questions

- When the REST transport is implemented, should
  `transports/api/openapi.yaml` expose a default-off `diagnostics` parameter on
  its search operation? Resolve this in the REST implementation change. Do not
  edit the OpenAPI contract here.
