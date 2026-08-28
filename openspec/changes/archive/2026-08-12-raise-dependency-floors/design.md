## Context

See `proposal.md` for motivation. The design-relevant state:

- Every upper cap in `pyproject.toml` is lifted. `uv lock --upgrade --dry-run`
  reports no changes, so the lock is at ceiling and this change moves only
  lower bounds.
- CI installs with `uv sync --frozen` in all four jobs, so the declared floors
  are inert. Nothing has ever installed them.
- `uv 0.8.4` supports `--resolution lowest-direct` on both `lock` and `sync`,
  which selects the lowest version satisfying each **direct** requirement while
  letting transitives resolve normally. This is the mechanism the gate needs.
- `uv.lock` is plain TOML readable with stdlib `tomllib` on the project's
  Python floor of 3.11. Package entries carry `name` and `version`, so a drift
  test needs no third-party parser.
- `tests/test_file_size_ceiling.py` is the precedent for an executable
  engineering invariant: pure stdlib, no fixtures, fails with the full list of
  offenders rather than the first one.

## Goals / Non-Goals

**Goals:**

- A floor set that installs and passes the fast suite, proven by CI rather
  than asserted in a comment.
- Per-package floors chosen from upstream evidence, so the ADR can defend each
  number independently instead of pointing at "whatever was locked".
- A cheap, always-on drift signal so the next upgrade cycle does not have to
  rediscover this by audit.

**Non-Goals:**

- Upper caps. None exist. Reintroducing one is a separate decision with its own
  ADR, per the pattern in ADR-039 through ADR-041.
- Moving transitives that upstream constrains. Listing them as watch items is
  the whole intervention.
- Automated dependency bots. Out of scope and orthogonal.
- Changing the Python version matrix or `requires-python`.

## Decisions

### D1: Floor = lowest version proven safe, not the locked version

Two candidate policies:

| Policy | Effect |
| --- | --- |
| Floor = locked version | Trivial to apply, zero research, maximally restrictive |
| Floor = lowest version whose API surface satisfies our call sites | Requires per-package evidence, keeps the supported range honest |

Chosen: the second. Floor = locked version is a lie in the opposite
direction. It claims the project breaks on versions it demonstrably works on,
and it forces a floor bump on every routine minor upgrade, which makes the
`BREAKING CHANGE` footer meaningless through repetition.

The research pass therefore asks one question per package: what is the earliest
release that still provides the API this project calls? Where the answer is
genuinely "the locked version", the floor goes there and the ADR says why.
Where a package has had no relevant breaking change in years (`networkx`,
`pyyaml`, `python-dotenv`), the floor moves conservatively, or not at all.

`chromadb` is the exception that proves the rule. Its floor is set by an
observed regression, not by the lock: 0.6.0 changed `list_collections()` to
return strings, 1.x returns `Collection` objects again. The floor is the
version that restored the object return, and the ADR cites the migration log.

### D2: Gate with `uv sync --resolution lowest-direct`, not a second lockfile

Options considered:

1. **Committed `uv-lowest.lock`.** Reproducible, but it is a second artefact to
   keep current and it goes stale exactly like the floors it guards. Rejected:
   it recreates the problem one level up.
2. **`uv sync --resolution lowest-direct` resolving fresh each run.** Not
   byte-reproducible across runs, since transitives float. That is acceptable,
   and arguably desirable: a transitive that breaks us at the floors is a real
   defect we want surfaced on the day it lands, not at the next audit.
3. **`uv pip compile --resolution lowest-direct` then install.** Equivalent
   outcome with an extra step and no lockfile benefit.

Chosen: option 2. The job runs `uv sync --resolution lowest-direct` followed by
the fast suite. It regenerates `uv.lock` inside the runner's checkout, which is
harmless because nothing is committed from CI.

Because that job's regenerated lock sits at the declared floors, the drift test
(D3) passes trivially inside it. No deselection is needed and the job stays a
single `pytest -m "not slow"` invocation.

### D3: Drift check as a test, mirroring the file-size ceiling

The drift test reads floors from `pyproject.toml` and versions from `uv.lock`,
both with `tomllib`, and fails when a floor sits more than one minor below its
locked version, or above it.

Rejected alternative: a pre-commit hook. Hooks are skippable with `--no-verify`
and do not run in CI, so the invariant would hold only for developers who
remembered to install them. The file-size ceiling made this call already and
this change follows it rather than inventing a second mechanism.

The "one minor" tolerance is deliberate. Zero tolerance would force a floor
bump on every routine patch upgrade and make the check noise. Two or more
minors of drift is the point at which "supported" and "tested" have visibly
diverged.

Packages exempt from the check: none by default. If a package needs a wider
gap, the exemption goes in the test with a comment naming the reason, so it is
reviewable. A silent skip list is how the floors rotted in the first place.

### D4: Fail first, fix second

Task order puts the CI job and the drift test **before** the floor edits, so
the failing state is recorded in history. This is the same sequencing as
`complete-architecture-v2-conformance` (design.md D7), where each import-linter
contract landed before the violation it caught was fixed.

The practical benefit is that the first floor-job run tells us which floors are
actually wrong, rather than us guessing and then finding out. The research pass
predicts the answer, the job confirms it.

### D5: One commit, one ADR, `BREAKING CHANGE` footer

Consistent with ADR-039 (mcp 2.0) and ADR-040 (huggingface-hub 1.0): the floor
raise is a breaking change to the install contract even though no runtime
behaviour changes. Semantic-release only reads the footer, so it must name the
packages and their new minimums explicitly.

ADR-042 carries the per-package evidence table. The design does not duplicate
it: a table of version numbers in a design document is stale the moment the
next upgrade lands, whereas an ADR is a dated record and is supposed to freeze.

### D6: The `llama-index` floor follows the tightest sibling, not the loosest

The research pass surfaced a contradiction inside the family. Reading PyPI
`requires_dist` at each historical version:

| Package | Earliest version needing core 0.13.0 | What the locked version needs |
| --- | --- | --- |
| `llama-index-vector-stores-chroma` | 0.5.0 | `core>=0.13.0,<0.15` |
| `llama-index-readers-file` | 0.5.0 | `core>=0.13.0,<0.15` |
| `llama-index-embeddings-ollama` | 0.7.0 | `core>=0.13.0,<0.15` |
| `llama-index-llms-ollama` | 0.7.0, then **0.9.0 jumps to core>=0.14.5** | `core>=0.14.5,<0.15` |

Answering "earliest core compatible with the chroma adapter" gives 0.13.0.
Answering "earliest core the whole locked family can share" gives 0.14.5.
Declaring 0.13.0 would mean the stated floors only work because the resolver
happens to pick newer patches, which is precisely the class of accident this
change exists to remove.

Chosen: `llama-index>=0.14.5`, with `llama-index-llms-ollama>=0.9.0` as the
sibling that sets it. Floors must be self-consistent when read alone. The ADR
records the 0.13.0 alternative and why it was rejected, so a future reader does
not "correct" it back down.

### D7: Two floors are wrong, and they fail differently

Both broken floors get the same treatment, but the ADR must not flatten them
into one story, because the detection cost differs.

`chromadb` 0.6.0 to 0.9.x fails loudly. `AttributeError` on `.name`, first call
to `list_collections()`, immediately visible.

`tree-sitter-language-pack` 1.8.0 to 1.12.2 fails quietly on Python 3.14. The
vendored parser constructed fine and produced unusable trees, and
`ast_extract.py` wraps the call in a broad `except Exception`, so the symptom
is a logged warning per file and a silently empty code graph. On Python below
3.14 the same range broke at import instead. The project's
`requires-python = ">=3.11"` spans both.

The design consequence: the `lowest-direct` job must run the AST tests, not
just import the package. A smoke test that only checks the package imports
would pass on Python 3.14 while the parser returns rubbish. Group 2's job runs
the full fast suite for this reason, rather than a cheaper subset.

## Risks / Trade-offs

**The floor job fails on first run and blocks the change** → Expected, and D4
sequences for it. If a floor cannot be made to pass without an unreasonable
raise, the fallback is to set that one package's floor to its locked version
and record the reason in the ADR. The gate stays; only the ambition of the
individual floor is reduced.

**Floors chosen from changelogs are still guesses** → Changelogs miss things.
The `lowest-direct` job is the actual proof, and it runs the same suite as the
normal job. A floor that passes the suite is supported in the only sense the
project can back up.

**Transitive float makes the floor job intermittently red for reasons outside
this change** → Accepted. That is the job doing its work. The mitigation is
that it fails loudly with a resolution or test error naming the package, so
triage is fast. If it proves genuinely noisy in practice, the escape hatch is
to make the job non-blocking and keep the signal, which is the same call TDR-007
made for the Codecov project checks.

**Consumers pinned to old chromadb or llama-index now fail to install** →
Intended. They failed at runtime before; failing at resolution is strictly
better. The `BREAKING CHANGE` footer and ADR-042 give them the migration path.

**Raising the llama-index family floors together could over-constrain** → The
five packages are a coupled set under chromadb 1.x, in the same way
huggingface-hub and transformers were coupled in ADR-040. Splitting them would
permit combinations nobody resolves. The ADR records the coupling explicitly so
a future reader does not unpick it by accident.

**The drift test's one-minor tolerance is arbitrary** → It is. It is also
reviewable in one place and cheap to change. The alternative, no tolerance, was
tried in spirit by the "documentation drift check" in AGENTS.md and depends on
discipline, which is what failed here.

## Migration Plan

No data migration and no runtime change, so there is nothing to roll back at
run time. The rollback for this change is `git revert` of the single commit.

Deployment order within the change:

1. Land the drift test and the CI job while they fail, per D4.
2. Land the floor edits until both are green.
3. Land ADR-042 with the evidence table and watch items.

`uv.lock` must not change. If `uv sync` produces lock churn after the floor
edits, a floor has been set above its locked version, which the drift test
catches as a failure rather than letting it pass silently.
