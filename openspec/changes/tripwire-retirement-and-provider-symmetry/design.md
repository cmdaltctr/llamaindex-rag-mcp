## Context

Two unfinished threads from the v2 migration, bundled because both are
"the mechanism was described but never completed" and both want the open v3
line.

`_RETIRED_ENV_VARS` in `src/omrg/config/legacy.py` holds 27 entries — 25
pre-v2 flat names retired by v2.0.0, and 2 v2 nested names retired by the
classify rename. `legacy.py`, CLAUDE.md gotcha #11, and ADR-037 all state the
removal trigger as v3.0.0. The classify rename is itself a breaking change on
the v3 line, so under that trigger its two entries expire in the release that
creates them.

Separately, ADR-026 introduced provider registries and ADR-027 recorded, in its
Consequences, that the LLM half was not yet wired: *"the LLM path will follow
when a second LLM sub-provider is added."* OpenRouter was added. The follow-up
was not.

## Goals / Non-Goals

**Goals**

- A retirement lifetime rule that cannot collide with the release that applies
  it.
- Preserve the actual guarantee — an operator who sets a dead name is told so —
  rather than preserving the current implementation of it.
- Finish the registry wiring ADR-027 deferred, and make the finished state
  machine-checkable.
- Stop documentation drift at the point where it hurts: instructions that fail.

**Non-Goals**

- Rewriting the settings system. The tripwire is a small list; the problem is
  its stated lifetime, not its design.
- Sweeping every mention of a retired name from the repository. Most mentions
  are correct (see D3).
- The stale registry *descriptions* in ADR-026/027 and `providers.md`, and the
  incorrect reranker default claim in `getting-started.md:49`. Those belong to
  the parallel `doc-rot-sweep` change. This change touches
  `getting-started.md` only at line 54.

## Decisions

### D1. The lifetime rule is shape-aware, because detection is shape-dependent

The obvious rule — "one major version, then delete" — is wrong, and measurement
is what showed it.

Probing the real `Settings` model:

| Variable set | Result |
| --- | --- |
| `METADATA__NONSENSE_KEY=1` | `ValidationError: metadata.nonsense_key — Extra inputs are not permitted` |
| `TOP_K=99` | constructs cleanly, value silently discarded |

The asymmetry is structural. Every settings block is `extra="forbid"`, so a
nested key under a recognised block prefix is caught by pydantic regardless of
the retirement list. A flat name matches no field at root, and pydantic-settings
never collects env vars that match no field — so the root model never sees it.

The tempting fix, `extra="forbid"` on the root `Settings`, **does not work**.
Verified directly against a minimal `BaseSettings` with `extra="forbid"`: an
unknown unprefixed variable is not collected, so there is nothing for `forbid`
to reject. The check passes and the variable is still ignored.

Consequences:

- For the **2 nested** classify entries, the tripwire is message quality only.
  Deleting them after one major is safe: the failure survives, the message
  degrades from "use `METADATA__CLASSIFY_TIMEOUT`" to a pydantic
  `extra_forbidden` error naming the field. Acceptable.
- For the **25 flat** entries, the tripwire is the *only* detector. Deleting
  them at v3.0.0 as scheduled would restore exactly the silent misconfiguration
  they exist to prevent, for anyone upgrading v1-era configuration to v3.

So the previously scheduled deletion of the flat entries is **reversed**, and
recorded as a decision. The cost of retention is 25 dictionary lines with no
runtime cost beyond one set intersection at startup. The cost of deletion is a
silently wrong retrieval configuration. That is not a close call.

**Alternative considered — scan the whole environment and reject anything
resembling a setting.** Rejected: outside a controlled container the environment
belongs to the user, and there is no way to distinguish "a dead rag-mcp
variable" from "an unrelated variable that happens to be called `TOP_K`" without
a curated list. A curated list is what the tripwire already is; this would only
change its shape.

### D2. The policy is stated as a rule, in one place

`legacy.py`'s module docstring becomes the single authority: nested entries
expire one major after retirement; flat entries persist while an upgrade path
exists. CLAUDE.md gotcha #11 references the rule rather than restating the
version. ADR-037's v3.0.0 trigger gets a dated forward-note rather than an edit,
since it is a record.

The rule is phrased so it never names the current version. A rename lands, its
entries carry their own expiry by shape, and no future change has to re-litigate
this.

### D3. Documentation enforcement keys on assignment, not mention

The naive check — "does any doc contain a retired name" — fails on contact with
the tree. Measured: 35 files match, and almost all matches are correct.
`.env.example:13`, `README.md:208`, `docs/guides/configuration.md:70`,
`docs/guides/architecture.md:110`, and CLAUDE.md gotcha #11 all name flat
variables precisely in order to teach the migration. Suppressing those would
make the documentation worse.

Restricting to assignment form — `^\s*#?\s*NAME=` — over operator-facing paths
(`.env.example`, `README.md`, `docs/guides/`) yields **exactly one** match
across the tree: `docs/guides/getting-started.md:54`, `RERANK_ENABLED=true`,
which is the real bug. One true positive, zero false positives.

The commented-out form (`# TOP_K=10`) is deliberately included: `.env.example`
teaches by commented assignment, so a commented retired assignment is just as
misleading as a live one.

Historical records — `CHANGELOG.md`, `docs/adr/`, `docs/tdr/`,
`docs/brainstorm/`, `openspec/changes/archive/` — are excluded by path. They
describe what was true when written and are not instructions.

**Alternative considered — check every code identifier cited in the guides
still resolves.** Deferred to `doc-rot-sweep`, which owns identifier-level rot.
Bundling it here would couple a precise, cheap check to a broad, noisy one.

### D4. OpenRouter moves to its own module in both registries

Target shape, matching `ollama` and `llamacpp` exactly:

```
core/metadata/openrouter.py          _extract_openrouter_chat_async
core/providers/llm/openrouter.py     build
```

with one `register()` line each, and the inline `OpenAILike(...)` construction
at `core/metadata/llamaindex.py:179-184` replaced by a registry lookup.
`_CLOUD_BACKENDS = {"openrouter": "openrouter"}` — a one-entry identity dict —
is deleted with its single caller.

**Config surface: unchanged, therefore not breaking.** `openrouter_llm_model`,
`openrouter_api_key`, and `cloud_backend` keep their names and meanings; only
the module that reads them moves. The endpoint moves from a literal to the
provider definition, which is where the other providers already keep theirs.

**The real risk is patch-target movement, not behaviour** (CLAUDE.md gotcha 8b).
`_extract_openrouter_chat_async` leaving `extractor.py` moves the patch target
used by the structured-output downgrade tests, and the PEP 562 `_NAMES` map in
`core/metadata/__init__.py` must move with it. Patching the re-exporting module
is a silent no-op, so a mistake here makes tests pass while testing nothing. The
tasks sequence this explicitly.

### D5. Symmetry is asserted, not documented

The reason this gap survived three releases is that nothing failed when it
appeared. ADR-027 wrote the intention into prose, and prose does not run.

The symmetry test enumerates both registries and asserts that every LLM-backed
backend appears in each under the same name, and that no metadata backend
resolves to the dispatch module. It is the mechanism that makes D4 stick.

## Risks / Trade-offs

- **Retaining 25 flat entries indefinitely looks like hoarding.** It is a
  deliberate trade against silent misconfiguration; D1 records the reasoning so
  a future reader does not "clean it up" without re-deriving the measurement.
  Revisit if v1 upgrade paths are ever formally dropped.
- **The guard test's exclusion list is a maintenance surface.** New
  operator-facing docs must be added to the scanned set or they go unchecked.
  Mitigated by scanning directories (`docs/guides/`) rather than enumerating
  files.
- **Moving OpenRouter can silently neuter its tests.** Mitigated by running the
  OpenRouter tests before and after the move and confirming the count and the
  patch targets, not just that the suite is green.
- **Two threads in one change.** Justified by shared cause and shared release
  window; they touch disjoint files, so either can be reverted independently.

## Migration Plan

Sequence matters in two places:

1. The classify entries must not be deleted until v3.0.0 has actually shipped —
   they are the migration path *into* v3. The task list marks this as
   post-release.
2. The OpenRouter module move and its patch-target updates must land in the same
   commit, or the intervening state has tests that pass without exercising the
   code (gotcha 8b).

Everything else is independent and can land in any order.

## Open Questions

- Should the guard test also cover `docs/guides/*` code fences that show shell
  `export` form (`export TOP_K=10`)? Not currently present anywhere in the tree;
  the regex covers it incidentally via the optional-comment prefix only if the
  line starts with the name. Worth extending if `export` form ever appears.
