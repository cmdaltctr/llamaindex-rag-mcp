## Context

See proposal.md for motivation. The v2 package rename made `omrg` the primary package and CLI, but `[project.scripts]` still installs `rag-mcp`. The login watcher installer then resolves that alias, writes `com.rag-mcp.watch.*` plists, and stores logs in `~/Library/Logs/rag-mcp`.

The current `public-library-api` specification requires `omrg` identity but permits either legacy-plist migration or retaining the alias. The current `login-watcher-installer` specification already requires an `omrg` executable, `com.omrg.watch.*` labels, and OMRG log paths. Implementation must now meet that contract without a compatibility command.

## Goals / Non-Goals

**Goals:**

- Remove the legacy console command for v3.
- Make every new watcher use OMRG names and an `omrg` executable.
- Move an existing legacy watcher only through the established confirmation or `--force` path.
- Prevent future live references to the old import or command names.
- Use `OMRG — Opinionated Modular RAG` consistently in user-facing product text.

**Non-Goals:**

- Rename the GitHub repository or Sonar project key.
- Rewrite changelog entries, ADRs, TDRs, or archived OpenSpec changes.
- Preserve an unattended legacy watcher after the upgrade.
- Change stored vectors, metadata, collection names, or require re-ingestion.
- Add a Python compatibility shim or a fallback command.

## Decisions

### 1. Remove the console alias as a v3 breaking change

Delete the `rag-mcp` entry from `[project.scripts]`. Keep `omrg` as the only entry point. The implementation commit uses a Conventional Commit breaking marker so semantic release produces v3.0.0.

ADR-060 reserved this removal for the next major version. Keeping the alias longer hides old commands and makes the retirement date meaningless.

**Alternative considered:** retain the alias for another major. Rejected because it silently extends the deprecated surface.

### 2. Resolve only `omrg` for new watcher plists

The installer searches `PATH` for `omrg`, then the running interpreter's bin directory for an `omrg` sibling. It reports an actionable error if neither exists. It never searches for `rag-mcp`.

The existing absolute `--command-path` override remains an explicit operator choice. Documentation and tests use an `omrg` path. It is not an automatic compatibility path.

**Alternative considered:** fall back to `rag-mcp` when `omrg` is missing. Rejected by user decision: it makes an incomplete upgrade silent.

### 3. Use OMRG labels and logs, and explicitly migrate legacy plists

New plans use `com.omrg.watch.` and `~/Library/Logs/omrg`. Existing-plist discovery scans both the new and legacy prefixes, then verifies the persisted watch path before treating a candidate as a match.

A matching legacy watcher takes the existing different-label flow. The user must confirm removal interactively or pass `--force`; only then does the installer boot it out, delete its plist, and write the new OMRG plist. This is migration cleanup, not executable fallback.

**Alternative considered:** leave legacy plists undiscovered. Rejected because a new watcher would duplicate ingestion while the old watcher fails after the alias disappears.

### 4. Treat old-name detection as a live-surface invariant

Extend `tests/test_docs_references.py` to reject both `rag_mcp` and standalone `rag-mcp` in live source, tests, operator documentation, and package metadata. The matcher excludes the unchanged `llamaindex-rag-mcp` GitHub repository identifier. Historical directories remain exempt.

Use a targeted pattern rather than a raw substring search so framework references to LlamaIndex remain valid and repository URLs do not become false positives.

### 5. Complete the product-text and internal-symbol cleanup

Update CLI help, watcher and installer docstrings, API contract text, transport documentation, root documentation, and guides to use OMRG branding. Remove the obsolete README alias note. Rename the internal `__RAG_MCP_PLAN_STOP__` sentinel to its OMRG equivalent because it is private and has one in-process use.

The untracked empty `src/rag_mcp/` directory is deleted as worktree residue after confirming Git tracks no files there.

## Risks / Trade-offs

- [A legacy watcher fails after a v3 upgrade] → This is deliberate loud failure. Release notes instruct users to rerun `omrg install-login-watcher`; the installer then offers explicit migration.
- [Legacy and new labels can describe the same watch path] → Scan both prefixes and verify persisted arguments before asking to remove anything.
- [The stale-reference guard can block repository URLs] → Exempt only the `llamaindex-rag-mcp` repository identifier, not arbitrary old command references.
- [Large fixture update misses a surface] → First extend the guard test, confirm it fails, then update all live fixtures and run targeted LaunchAgent tests plus the fast suite.

## Migration Plan

1. Release v3 with no `rag-mcp` console entry point.
2. Tell users with a login watcher to run `omrg install-login-watcher` for each watched folder. The existing consent or `--force` flow replaces a matching legacy plist.
3. A user who does not reinstall gets a visible launchd command failure. OMRG does not mask it with a fallback.
4. If rollback is necessary, reinstall the last v2 distribution. Stored data needs no rollback or re-ingestion.
