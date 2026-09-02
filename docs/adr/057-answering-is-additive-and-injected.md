# ADR-057: Answering Is Additive and Injected

**Date:** 2026-09-02
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The `add-grounded-answer-synthesis-3` change adds the project's first
query-time generation path: retrieve evidence through the existing search
pipeline, then synthesise one answer with citations. Four forces shaped the
decision:

1. **Generation is expensive and optional.** `search_documents` returns
   ranked chunks with no model call. Answering performs one or more
   completion calls, so it must stay additive — an opt-in capability on
   top of retrieval, never a replacement for it, and never a new hard
   dependency of the base install.
2. **The import contract has exactly one exemption today.** The
   `core-business-avoids-providers-transports` contract keeps `core/`
   free of provider and transport imports. Its single named exemption,
   `metadata.llamaindex`, exists because metadata extraction runs deep
   inside ingestion where injection was awkward. A second exemption
   would start to normalise the leak.
3. **An empty context is the failure this capability exists to prevent.**
   A model asked a question with no evidence is at its most likely to
   answer from parametric memory. Whatever the answering path does, it
   must never put a model in that position.
4. **Two completers can exist.** An MCP client may carry its own model
   (sampling), and the server may carry one (the provider registry).
   Their preference order, the deprecated legacy back-channel's place
   in it, and who answers each query needed an explicit contract.

## Decision

1. **The LLM is injected at the composition boundary (design D1).**
   `compose.build_answer_llm()` resolves `answer.provider` through the
   same LLM registry metadata extraction uses and hands the provider
   builder an `answer_model` override, so answering never silently
   reuses the small classification model. `core/answer/` receives an
   async completion callable and never imports a provider module. The
   import-linter contract gained only a source module
   (`rag_mcp.core.answer`) — no new ignore entry. Answering is a
   top-level entry point like `search` and `ingest_path_async`
   (ADR-037), which is precisely where this project resolves
   dependencies; copying the `metadata.llamaindex` exemption here would
   copy the exception instead of the rule. `answer.enabled=false` or a
   missing optional extra resolves to `None`, and the tools return an
   actionable error naming `ANSWER__PROVIDER`/`ANSWER__MODEL` and the
   client-sampling alternative. An unknown provider name fails startup
   validation.

2. **There is no second retrieval path (design D3).**
   `core/answer/retriever.py` adapts `search()` to LlamaIndex's
   `BaseRetriever`, converting result dicts to `NodeWithScore` with
   lineage preserved in node metadata. Profile resolution, hybrid
   fusion, reranking, and context assembly run exactly as they do for a
   plain search. Synthesis drift would require someone to add a second
   retrieval path, which review rejects.

3. **Completion preference is client-first and always reported
   (design D6).** On a modern session (protocol ≥ 2026-07-28) with the
   sampling capability and `answer.prefer_client_sampling`, the client's
   model answers through the bounded MRTR resolver chain (`Resolve` /
   `Sample`, at most four rounds); the deprecated
   `ctx.session.create_message()` is never called on a modern session.
   On a negotiated legacy session with capability and
   `answer.allow_legacy_sampling`, the deprecated back-channel runs as a
   labelled compatibility seam. Otherwise the lazy configured server
   model runs. When neither exists, the caller receives an actionable
   error naming both options. Every result reports `completion_source`
   (`client_mrtr`, `client_legacy`, `server`, or `none`), and COMPACT
   refinement rounds are bounded with each round following the same
   mechanism.

4. **Empty retrieval never reaches the model (design D7).** With no
   evidence rows, the operation returns `no_evidence` before any
   completion call. This is both cheaper and safer: a model handed an
   empty context is at its most likely to answer from parametric
   memory, which is exactly the failure this capability exists to
   prevent.

Supporting decisions in the same change: `core/answer/` is a new
sibling subpackage rather than an addition to `core/retrieval/`
(design D2); citations are built from chunk lineage and intersected
with the answer, so a model-invented, out-of-range, malformed, or
duplicate ordinal is dropped or deduped, and a substantive answer with
no valid citation is reported `generation_unverified` with the evidence
still returned (design D5); the response mode is COMPACT
(`CompactAndRefine`) over an injected async adapter (design D4). The
context budget is a deterministic character count
(`answer.context_window`), not a token estimate. When the evidence
needs more rounds than `answer.max_rounds` allows, the per-round budget
widens so later rounds absorb the overflow — no evidence is dropped.
LlamaIndex `simple_summarize` was rejected for exactly the silent
truncation this project refuses elsewhere.

**MCP clients generating their own answers from `search_documents`
chunks remain a supported and preferred mode.** The `answer_documents`
tool exists for CLI, HTTP-contract, and evaluation consumers, and for
MCP callers who knowingly choose generation with its completion cost.

## Consequences

### Positive

- Retrieval behaviour cannot drift between `search_documents` and
  `answer_documents`; both run through one `search()` path.
- No new import-contract exemption. The registry-and-injection shape
  matches ADR-026 and ADR-031.
- `completion_source` makes the completing party auditable on every
  result, including the legacy seam.
- `no_evidence` costs nothing beyond retrieval and can never answer
  from parametric memory.
- Evidence is returned on every generation failure, so retrieval work
  is never wasted by a bad answer.

### Negative

- The tool performs one or more completion calls. Callers who only need
  chunks must keep using `search_documents`; the tool description says
  so.
- The legacy sampling seam keeps deprecated API surface alive behind an
  explicit flag until the pre-2026-07-28 population is gone.
- A character-based context budget is deterministic but not
  token-exact; token counts vary by model tokenizer.

### Neutral

- `answer.enabled=false` leaves the retrieval tools untouched;
  answering is purely additive.
- The MRTR chain depth (four rounds) and `answer.max_rounds` bound the
  same synthesis independently; the effective cap is the smaller of the
  two.
- The OpenAPI contract (`POST /collections/{collection}/answer`) is
  contract-first; no runtime HTTP server ships yet.

## Alternatives Considered

| Option | Rejected because |
| --- | --- |
| A named import-contract ignore for `core/answer` | A second exemption normalises the leak. Injection needs none, and answering is exactly the kind of top-level entry point ADR-037 resolves at the composition boundary. |
| A second retrieval path tuned for synthesis | Two paths to keep in sync; drift silently changes evidence quality. The adapter adds no path. |
| `simple_summarize` (one call, silent truncation) | Drops evidence the ranker selected, invisibly. Round-bound widening keeps every row. |
| `tree_summarize` | Its benefit appears at a `top_k` far above this project's defaults, and it costs more calls without a hierarchy the project does not have. |
| Token-based context budget | Needs a tokenizer that varies per model; a character budget is deterministic and dependency-free. |
| Always use the server model, ignore client sampling | Wastes the client's model, adds latency, and blocks headless deployments with no provider configured. |
| Allow `create_message` on modern sessions | Deprecated API on a protocol that replaces it; the MRTR resolver chain covers the same need, bounded. |
| Answer from parametric memory when retrieval is empty | The exact ungrounded failure the capability prevents, plus a wasted completion call. |

## References

- OpenSpec change: `openspec/changes/add-grounded-answer-synthesis-3/`
  (design decisions D1–D8; capability spec
  `specs/grounded-answer-synthesis/`)
- Contract owners: `src/rag_mcp/core/answer/` (`pipeline.py`,
  `synthesis.py`, `citations.py`, `retriever.py`, `prompt.py`,
  `settings.py`), `src/rag_mcp/compose.py` (`build_answer_llm`),
  `src/rag_mcp/transports/mcp/answer.py`,
  `src/rag_mcp/transports/cli/answer.py`,
  `src/rag_mcp/transports/api/openapi.yaml`
- Guides: [MCP tools](../guides/mcp-tools.md#answer_documents),
  [CLI reference](../guides/cli-reference.md#answer),
  [Configuration](../guides/configuration.md#answering--answer__)
- Related decisions: ADR-026 (provider registry), ADR-031
  (config/compose/DI), ADR-037 (architecture v2 conformance), ADR-052
  (stable source and chunk lineage), ADR-056 (context assembly and
  `chunk_ids`)
