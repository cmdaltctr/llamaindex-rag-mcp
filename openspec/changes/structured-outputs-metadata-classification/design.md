## Context

See `proposal.md` — Why. The design-relevant state: all three LLM classification backends share
`_build_ollama_prompt`, `_parse_ollama_json_response`, `_get_ollama_max_attempts`, `_get_ollama_timeout`
and `_retry_sleep`, but each builds its own `data` payload and drives its own `for attempt in
range(max_attempts)` loop over `httpx.AsyncClient`. The three loops are near-identical copies.

The constraint that shapes everything below is that the three backends do **not** have equivalent
failure semantics for this feature:

| Backend | Mechanism | If unsupported |
| --- | --- | --- |
| Ollama `/api/generate` | `format: "json"` | field ignored, request succeeds |
| llama.cpp `/v1/chat/completions` | `response_format: {type: json_object}` | field ignored, request succeeds |
| OpenRouter `/v1/chat/completions` | `response_format: {type: json_schema}` | **request fails** |

Ollama and llama.cpp are therefore safe to change unconditionally. OpenRouter is not: its support is
determined per serving *endpoint*, and the same model served by two upstream providers may support the
schema on only one of them. This is documented behaviour, not an inference —
https://openrouter.ai/docs/features/structured-outputs.

## Goals / Non-Goals

**Goals:**
- Reduce how often classification lands on the `uncategorised` fallback, which pollutes the hybrid
  category taxonomy that later prompts are built from.
- Keep local-first behaviour identical in shape and cost — no extra round trips on the common path.
- Keep ADR-024's contract: a cloud feature must degrade to something that still works.

**Non-Goals:**
- Deleting `_strip_markdown_fence` or the unparseable-response fallback. Enforcement reduces their
  hit rate; it does not make them unreachable.
- Unifying the three duplicated retry loops. Real duplication, but a separate refactor with its own
  risk profile — folding it into this change would obscure a behavioural change inside a structural one.
- Adding a settings knob to disable enforcement. See Decision 4.
- Changing the `llamaindex` extraction mode, which goes through LlamaIndex LLM objects rather than
  these hand-built payloads.

## Decisions

### 1. JSON mode for local backends, full JSON Schema for OpenRouter

Ollama and llama.cpp get the cheap flag (`format: "json"` / `response_format: json_object`). OpenRouter
gets a full schema pinning `category`/`keywords`/`summary` with `strict: true`.

*Why the asymmetry:* against a single local server you control, plain JSON mode plus the existing
prompt is sufficient — the parser already normalises missing or oddly typed fields. OpenRouter fans out
to many upstream providers with differing instruction-following quality, so pinning field types is
worth the extra payload. It is also the path OpenRouter documents and gates `require_parameters` on;
`json_object` is comparatively under-specified there.

*Alternative considered:* a JSON Schema on Ollama too (supported since 0.5 via `format: <schema>`).
Rejected for now — it raises the minimum Ollama version for a marginal gain on a server whose output
the parser already handles. Recorded as a follow-up in Open Questions.

### 2. `require_parameters: true` paired with a one-shot downgrade

Sending the schema *without* `require_parameters` lets OpenRouter route to an endpoint that rejects it,
so the request fails anyway. Sending it *with* `require_parameters` narrows routing to endpoints that
honour it — strictly better, except when that leaves nothing routable, which fails hard.

The pairing resolves this: `require_parameters` on the first attempt, and on HTTP 400/404/422 strip both
`response_format` and `provider` and retry. Worst case for a model with no schema-capable endpoint is
one wasted request per document, then today's behaviour.

*Alternatives considered:*
- *Schema with no `require_parameters`* — same hard failure, but nondeterministically, depending on
  which endpoint the router picked. Worse to diagnose.
- *A capability probe at startup* — an extra network call in the composition root, cached state to
  invalidate, and it can go stale mid-run as endpoints change. Disproportionate.
- *Config flag naming known-good models* — pushes an OpenRouter routing detail onto the operator, and
  goes stale silently.

### 3. Downgrade lives inside the existing retry loop, not around it

The downgrade mutates `data` in place and `continue`s, reusing the loop already there rather than
wrapping the call in a second try/except. It deliberately skips the backoff sleep: a rejected payload is
not a transient fault, so waiting achieves nothing.

*Trade-off:* the downgrade consumes one attempt from the budget. With the default of 3 there is room.
At `OLLAMA_CLASSIFY_MAX_ATTEMPTS=1` the downgrade is computed but the loop exits before retrying, so a
schema-incapable model degrades to `uncategorised` — same as if we had not implemented the downgrade.
Accepted rather than restructuring the loop into a `while` with a separate budget; recorded under Risks.

### 4. No configuration surface

Enforcement is unconditional. A flag would need a default, and the safe default is on — leaving the off
switch as dead configuration that exists only to be forgotten. The downgrade covers the case a flag
would have been used for, automatically and per-request rather than per-deployment.

### 5. Narrow status-code list for the downgrade trigger

`{400, 404, 422}` only. 429 is excluded because rate limiting is transient and dropping the schema does
not address it — treating it as a parameter fault would spend the downgrade and then still fail. 401/403
are excluded because an auth failure is not fixed by a smaller payload, and downgrading would make the
resulting log line misleading about the real cause.

## Risks / Trade-offs

- **Ollama JSON mode without a schema can emit unbounded whitespace** (a known Ollama behaviour when the
  prompt does not clearly demand JSON) → the existing prompt already demands JSON explicitly, which is
  the documented mitigation, and `OLLAMA_CLASSIFY_TIMEOUT` bounds the damage per attempt.
- **`require_parameters` narrows routing, which can raise latency or cost** by excluding cheaper
  endpoints → affects the OpenRouter path only, which is already the opt-in cloud path; the downgrade
  bounds the worst case.
- **The downgrade never fires at `max_attempts=1`** (Decision 3) → equivalent to pre-change behaviour,
  not worse; documented, and the default is 3.
- **Older Ollama or llama.cpp builds may not know the field** → both ignore unknown request fields, and
  the fence-stripping path is retained precisely for this.
- **The downgrade branch is the only new logic and is the easiest thing to regress silently** → it is
  covered explicitly by the test tasks; the payload assertions are what make the whole change observable
  to CI at all.

## Migration Plan

None required. No settings, no dependencies, no stored data, no wire format visible to callers. Rollback
is reverting the three payload edits; the downgrade helper is inert once its payload keys are gone.

## Open Questions

- Should Ollama move from `format: "json"` to a full `format: <schema>` once a minimum Ollama version is
  worth pinning? Deferred: it would tighten guarantees on the local path but does not change these specs,
  the approach, or the task breakdown.
- Does OpenRouter's Response Healing plugin make the downgrade redundant for `json_schema` requests?
  Worth measuring later; it does not affect this design, which must handle outright routing failure
  regardless.
