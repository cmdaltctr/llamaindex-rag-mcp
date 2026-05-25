## Context

The verified review separated major behavior changes from smaller cleanups. These items are mostly cosmetic or latent-risk fixes and should not be mixed into functional PRs unless implementation naturally overlaps.

## Goals / Non-Goals

**Goals:**
- Clarify internal code intent.
- Remove misleading comments/dead branches.
- Reduce theoretical concurrency ambiguity without changing behavior.
- Keep tests deterministic and easy to reason about.

**Non-Goals:**
- Changing ingestion behavior for supported/unsupported files.
- Reworking watcher concurrency or deduplication policy.
- Changing benchmark output semantics.

## Decisions

- Keep this as a single low-risk cleanup change rather than separate PRs for each tiny issue.
- Do not alter the acknowledged watcher hash-cache race trade-off unless changing lock naming makes a safe minimal improvement obvious.
- Add tests only where behavior is clarified, not for pure renames.
- **Benchmark chunking helper boundary (resolved 2026-05-25): add a public `read_and_chunk_file_async()` wrapper in `ingestion.py` that delegates to the existing `_read_and_chunk_file_async()` private implementation. `cli.py benchmark` SHALL import the public wrapper. The private helper SHALL remain available for internal ingestion use to avoid churn in the hot path. This makes the cross-module boundary honest without committing to a wide public API surface.**

## Risks / Trade-offs

- Grouping cleanups can obscure intent → mitigate by keeping tasks small and commits focused.
- Lock renames can touch many lines → mitigate with straightforward mechanical rename and existing watcher tests.
- Public `read_and_chunk_file_async()` wrapper joins the internal-supported surface → mitigate by adding a docstring stating it is intended for benchmark and ingestion internals, and is subject to change between minor releases (not a stable third-party API).
