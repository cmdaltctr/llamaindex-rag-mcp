## Context

See `proposal.md` — Why. This section records only what shapes the approach.

**What the code actually does today.** Dispatch is five flat, per-domain lazy
registries, all following one contract:

```python
_registry: dict[str, str] = {}                    # name -> "module:attr"
def register(name: str, import_path: str) -> None
def get(name: str) -> Callable[..., Any]          # resolves + caches
def available() -> list[str]                      # sorted names
```

Live registrations, verified:

| Registry | Names |
| --- | --- |
| `core/providers/embeddings/registry.py` | `ollama`, `llamacpp`, `openrouter` |
| `core/providers/llm/registry.py` | `ollama`, `llamacpp` |
| `core/metadata/registry.py` | `keyword`, `ollama`, `llamacpp`, `llamaindex`, `openrouter` |

There is no `_build_provider`, no `LOCAL_*`/`CLOUD_*` dict, and no `if/elif`
over strategy names — CLAUDE.md invariant 10 forbids the last one.

**Two ADR consequences are stale in the *opposite* direction from the guide.**
The guide over-claims a mechanism that is gone; the ADRs under-claim progress
that was made:

- ADR-026:104 and ADR-027:67 record the LLM path as a known gap still using
  if/elif. It is **closed**. `_dispatch_local_extraction`
  (`core/metadata/extractor.py:61`) survives only as a named entry point for
  `llamaindex.py`'s degradation path; its docstring states "Dispatch itself
  goes through the registry — this only maps provider configuration to a
  strategy name."
- ADR-026:106 records that cloud dispatch "hardcodes `openrouter` without
  checking `CLOUD_BACKEND`". Also closed: `_local_strategy_name` reads
  `settings.cloud_backend` through `_CLOUD_BACKENDS`.

**ADR-026 already carries a forward note that is itself stale.** Its
`## Update (2026-08-04, Phase 2)` section says the dicts were "**physically
relocated**" with names preserved, and that "the LLM dispatch path itself was
not rewritten in this phase". Both statements were true when written and are
false now. This is second-order rot, and it constrains the fix: the repo layers
dated notes rather than editing them, so the 2026-08-04 note is preserved and a
2026-08-07 note is appended below it.

**Established forward-note conventions** (from `git log -p` on this branch) —
both are in use and the choice is by scope:

- Inline blockquote `> **Update (<change-id>, YYYY-MM-DD):** …` — placed
  adjacent to the stale claim, for narrow corrections (e.g. ADR-037's classify
  table at line 119).
- Trailing section `## Update (YYYY-MM-DD, <label>)` — for corrections spanning
  the whole record (e.g. ADR-026's Phase 2 note, ADR-031's amendments).

## Goals / Non-Goals

**Goals:**

- Every surviving statement about provider dispatch is true on 2026-08-07.
- A contributor can add a provider by following `providers.md` alone.
- The registry-name class of rot fails CI instead of ageing.

**Non-Goals:**

- Rewriting ADR decision text. ADRs are immutable; notes are appended.
- Any `src/` change. The code is correct; the documents are wrong.
- A general-purpose documentation linter — see Decision 4.
- Env-var names, in any file (owned by
  `tripwire-retirement-and-provider-symmetry`).

## Decisions

### 1. Layer a second dated note on ADR-026 rather than correct the first

**Chosen:** append `## Update (2026-08-07, doc-rot-sweep)` beneath the existing
Phase 2 note, explicitly superseding two of its claims.

**Why:** editing the 2026-08-04 note would destroy the record of what was
believed and shipped at Phase 2 — the same reason the repo does not edit
decision text. A reader following the file top-to-bottom gets the decision, then
what Phase 2 changed, then what is true now. The cost is a longer file; the
benefit is that the ADR remains a history rather than a snapshot.

**Alternative rejected:** collapsing both notes into one accurate "current
state" block. Cheaper to read, but it silently rewrites history and would set a
precedent that dated notes are editable.

### 2. Correct ADR-027 with an inline blockquote, not a trailing section

ADR-027's rot is one bullet (line 67) plus one reference line (line 89). Scope
is narrow, so the inline convention applies — the note sits where the false
claim is, which is what a reader skimming Consequences needs. ADR-026's rot
spans four separate lines across Consequences and References, so it takes the
trailing-section form.

### 3. `providers.md` is rewritten, not annotated

A guide has no historical value — it is read as instruction. The "Registry
pattern" section (lines 110–126) is replaced wholesale with the real mechanism
and a real four-step "add a provider" procedure. No dated note: nobody wants a
guide's archaeology.

### 4. Prevention: two narrow pinned checks, **not** a general identifier checker

This is the load-bearing decision, so it is argued from measurement rather than
assertion.

**The tempting option** — assert every code identifier cited in
`docs/guides/*.md` resolves somewhere in `src/` — was prototyped against the
current tree. Result: **192 unique backticked bare identifiers, 181 resolve, 11
flagged.** Of those 11 flags:

| Flagged | Verdict |
| --- | --- |
| `LOCAL_EMBED_PROVIDERS`, `CLOUD_EMBED_PROVIDERS`, `LOCAL_LLM_PROVIDERS`, `CLOUD_LLM_PROVIDERS` | **true positive** (4) |
| `LLAMACPP_CHAT_MODEL`, `LLAMACPP_CHAT_URL`, `LLAMACPP_EMBED_MODEL`, `LLAMACPP_EMBED_URL`, `LITEPARSE_NUM_WORKERS` | false positive — env-var names assembled by pydantic prefix/alias, so the literal string never appears in `src/` (5) |
| `asyncio_mode` | false positive — a `pyproject.toml` key, not a `src/` symbol (1) |
| `RETRIEVAL__TOPK` | false positive — a **deliberately wrong** example, documenting that a bad nested key fails loudly (`configuration.md:76`) (1) |

**Measured precision: 4/11 ≈ 36%.** And the false positives are not a one-time
cleanup cost — they are structural. Documentation must be able to name env vars
(which do not exist as `src/` literals) and to show counterexamples (which must
not exist). Making the checker usable therefore requires a second oracle for
env-var names plus an inline suppression vocabulary, and every future doc author
must learn both. That is a linter to maintain, not a test.

**The decisive argument is what it would not catch.** Of the four rot instances
this sweep fixes, the identifier checker catches only the registry names. It
does not catch the dangling `src/rag_mcp/config.py` path, and — critically — it
cannot catch either of the two errors that actually mislead a *user*: "the
reranker is enabled by default" and the stale `sys.modules` fixture description.
Those are prose claims about values and behaviour. **No static checker of this
family catches them.** Buying a 36%-precision checker to cover the least
harmful failure, while the most harmful failures stay uncovered, is a bad trade.

**Chosen instead — two checks with exact-match oracles, both ~0% false positive
by construction:**

**(a) Documentation path resolution** (`tests/test_docs_references.py`). Every
`src/rag_mcp/**.py` path cited anywhere in `docs/` must exist on disk. A path
either resolves or it does not — there is no judgement, so no suppression
mechanism is needed. Measured against the current tree: **1 flag, 1 true
positive, 100% precision** (`providers.md:121`). Roughly 25 lines.

**(b) Documented provider names pinned to the registries** (extending
`tests/test_registry_contract.py`). Parse the provider names listed in
`providers.md`'s registry section and assert set-equality against
`embed_registry.available()` and `llm_registry.available()`. This compares two
lists, so it cannot produce a false positive; it fails exactly when someone adds
or renames a provider without touching the guide — the precise event that
produced this change. `test_registry_contract.py` already imports all five
registries and defines `ALL_REGISTRIES`, so this is an extension of an existing
contract, not a new concept. Roughly 20 lines.

Both are cheap, both have a real oracle, and neither needs a suppression syntax.
Together they cover the two mechanical rot classes; Decision 5 covers the prose
class that no test can reach.

**Alternative rejected:** doc-value pinning (parsing "enabled by default" style
claims and comparing to the settings model). Correct in principle and it *would*
have caught the reranker error, but it requires either a machine-readable
annotation on every factual claim in prose or NLP-grade extraction. The
annotation burden lands on every doc author for a payoff of a handful of
claims. Revisit only if defaults-drift recurs.

### 5. A process control for the class no test can cover

Prose claims about behaviour ("enabled by default") drift silently and no
checker proposed here catches them. The cheap mitigation is procedural: the
change workflow already routes through `tasks.md`, so the sweep adds a standing
item to the ADR/change checklist — *when a default value changes, grep
`docs/guides/` for the old value*. This is documentation, not automation, and it
is offered as an honest partial: it depends on discipline and will sometimes be
skipped. It is still strictly better than the current state, which is nothing.

## Risks / Trade-offs

| Risk | Mitigation |
| --- | --- |
| Merge conflict with `tripwire-retirement-and-provider-symmetry` in `getting-started.md` (both edit lines 48–56) | Boundary table in `proposal.md`; this change edits only the sentence at line 50 and leaves the fenced `RERANK_ENABLED` block at 52–54 untouched. Whichever lands second rebases one hunk. |
| Check (b) is brittle if `providers.md` is restructured | Parse from an explicit HTML-comment-delimited block in the guide rather than by loose regex over prose, so a rewrite that keeps the block keeps the test passing, and one that drops it fails loudly. |
| Check (a) may flag legitimately deleted paths in historical ADRs | Scope the check to `docs/guides/` + `tests/TEST_README.md`. ADRs are historical records and legitimately cite paths that no longer exist; forcing them to resolve would fight Decision 1. |
| Forward notes accumulate; ADR-026 gains a third layer | Accepted. Length is the cost of an accurate history. If a fourth is ever needed, that is the signal to supersede ADR-026 with a new ADR instead. |
| The 2026-08-07 note could itself go stale | Unavoidable in principle, but check (b) now fails when the registries change, so the next drift surfaces as a red test rather than a quiet contradiction. |

## Open Questions

None blocking. One deferrable: whether check (a) should later widen from
`docs/guides/` to all of `docs/`, excluding `docs/adr/`. That is a one-line
change to a path glob, decidable after the check has run in CI for a while, and
it does not affect the specs, the approach, or the task breakdown.
