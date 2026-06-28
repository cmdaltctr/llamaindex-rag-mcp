# TDR-004: `--no-build` flag incompatible with editable installs in CI

**Date:** 2026-06-28
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Tags:** ci | uv | sonarqube | security

## Context

SonarQube flags `uv sync` and `uv run` commands without `--no-build` as a
security risk (rule: execution of setup scripts from source distributions).
To satisfy this warning, `--no-build` was added to all `uv sync` and `uv run`
commands in `.github/workflows/ci.yml`.

CI immediately failed on all three jobs (ubuntu, macos, sonarcloud) with:

```
error: Distribution `rag-mcp==1.8.0 @ editable+.` can't be installed because
it is marked as `--no-build` but has no binary distribution
```

### Root Cause Analysis

The project is installed as an **editable package** (`editable+.` in `uv.lock`),
which requires a build step to create the `.pth`/`__editable__` files that link
the source tree into the virtual environment. `--no-build` tells uv to never
build source distributions — this includes the project itself, not just
third-party dependencies. Since an editable install has no pre-built wheel, uv
cannot install it with `--no-build`.

The SonarQube warning is designed for scenarios where untrusted third-party
packages might execute arbitrary code during build. In this case, the only
package being built is the project's own editable install — not arbitrary
third-party code.

## Decision

Remove `--no-build` from all `uv sync` and `uv run` commands. Keep `--frozen`
(which locks the dependency set to `uv.lock`) and `--no-sync` on `uv run`
(which skips re-syncing).

```yaml
# Before (broken):
run: uv sync --frozen --no-build
run: uv run --no-sync --no-build pytest ...

# After (working):
run: uv sync --frozen
run: uv run --no-sync pytest ...
```

Mark the SonarQube `--no-build` warnings as **SAFE** with justification: the
only distribution requiring a build is the project's own editable install, and
`--frozen` ensures all third-party dependencies are locked to `uv.lock`.

## Consequences

### Positive

- CI passes — editable install builds successfully
- `--frozen` still ensures reproducible dependency resolution
- `--no-sync` still prevents unnecessary re-syncs during `uv run`

### Negative

- SonarQube security warnings about missing `--no-build` persist and must be
  marked SAFE manually after each scan

### Neutral

- Build time is negligible (editable install only creates `.pth` files)

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Keep `--no-build` and switch to non-editable install | Would require rebuilding on every code change; breaks development workflow |
| Keep `--no-build` and build a wheel first | Adds unnecessary complexity; the editable install is the standard uv pattern |
| Suppress SonarQube rule globally | Too broad; the rule is valuable for non-editable projects |

## How to Recognise / Handle This Again

1. **Symptom**: CI fails with `can't be installed because it is marked as
   --no-build but has no binary distribution`
2. **Diagnostic**: Check if the project uses an editable install — look for
   `editable+.` in `uv.lock` or `[tool.uv]` config in `pyproject.toml`
3. **Recovery**: Remove `--no-build` from `uv sync` and `uv run` commands.
   Keep `--frozen` for dependency locking. Mark SonarQube warnings as SAFE.

## Revisit Triggers

- uv adds support for `--no-build` that excludes the project's own editable
  install (e.g., `--no-build-deps` or similar)
- Project switches from editable to non-editable install
- SonarQube rule is updated to distinguish editable vs. third-party builds

## References

- [uv sync docs](https://docs.astral.sh/uv/reference/cli/#uv-sync)
- SonarQube rule: "Omitting --no-build can lead to the execution of setup scripts"
- `.github/workflows/ci.yml` — CI workflow file
- PR #11 — `fix/sonarqube-all-issues` branch
