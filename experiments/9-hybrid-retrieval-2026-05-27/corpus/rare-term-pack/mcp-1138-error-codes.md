# MCP-1138 troubleshooting reference

The **MCP-1138** error code is emitted by the build orchestrator when the
pre-flight workspace integrity check detects a partial checkout of a Git
submodule. It is unrelated to the older **MCP-1037** (stale lockfile) or
**MCP-1140** (network timeout) codes, which are sometimes confused with it
because of the proximity of the numeric range.

## Symptom

The build fails during the `setup-workspace` step with:

```
ERROR MCP-1138: workspace integrity check failed
  hint: submodule 'vendor/foo' is checked out at <unknown>
  hint: run `git submodule update --init --recursive` and retry
```

## Root cause

**MCP-1138** fires when the orchestrator's `git submodule status --recursive`
output contains a leading `-` character on at least one line — the conventional
indicator that the submodule is not initialised. This usually happens after:

1. A partial `git pull` that did not recurse into submodules.
2. A CI cache restore that elided the submodule blob store.
3. Manually deleting `.git/modules/<name>` without re-running submodule init.

## Resolution

The canonical fix for **MCP-1138** is:

```
git submodule sync --recursive
git submodule update --init --recursive --force
```

If the error persists after a full re-init, escalate to the platform team
with the orchestrator log and the output of `git submodule status --recursive`.
Do not silence **MCP-1138** by deleting the integrity check — the code exists
because every previous attempt to skip it produced silent build artefacts that
failed at deploy time.
