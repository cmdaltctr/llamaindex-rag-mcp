## Why

The v2 rename made `omrg` the package and primary CLI, but it left a deprecated `rag-mcp` script, new LaunchAgents that depend on it, and old product wording across live surfaces. Version 3 is the scheduled removal point, so retaining a fallback would hide an incomplete upgrade instead of making it fail clearly.

## What Changes

- **BREAKING** Remove the `rag-mcp` console-script entry point. `omrg` is the only supported CLI command.
- Make the login watcher installer resolve only the absolute `omrg` executable. It must fail with an actionable error when `omrg` is unavailable. It must not resolve or fall back to `rag-mcp`.
- Generate new watcher labels as `com.omrg.watch.*` and logs under `~/Library/Logs/omrg`.
- Detect an existing legacy `com.rag-mcp.watch.*` plist for the same watched directory. Require the existing explicit confirmation or `--force` flow to boot it out and replace it with the `omrg` watcher. Do not keep the legacy executable working.
- Remove live `rag_mcp`, standalone `rag-mcp`, and old product-name wording from code, tests, operator documentation, CLI help, and the OpenAPI contract. Use `OMRG — Opinionated Modular RAG` for the full product name and `OMRG` for short references.
- Strengthen the stale-reference guard to reject both old import and standalone console-command names while allowing historical records and the unchanged GitHub repository identifier.
- Remove the untracked empty `src/rag_mcp/` directory as local worktree residue. Historical changelog, ADR, TDR, archived OpenSpec, GitHub URL, and Sonar project-key references remain unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `public-library-api`: require that `omrg` is the only console command and that a legacy LaunchAgent is explicitly migrated, never supported through a retained `rag-mcp` alias.

## Impact

**Code:** `pyproject.toml`; the LaunchAgent planner and installer; CLI, watcher, configuration, composition, API-contract wording; the internal plan-stop sentinel.

**Tests:** LaunchAgent unit and CLI tests; stale-reference guard; CLI wording tests.

**Documentation:** README, AGENTS.md, CLAUDE.md, CONTRIBUTING.md, operator guides, and transport documentation.

**Compatibility:** invoking `rag-mcp` after upgrading to v3 fails. A legacy watcher continues to point at the removed executable until its user reinstalls it through `omrg install-login-watcher`; the installer migrates it only through explicit confirmation or `--force`.

**Release:** commit the implementation with a Conventional Commit breaking-change marker so python-semantic-release publishes v3.0.0.
