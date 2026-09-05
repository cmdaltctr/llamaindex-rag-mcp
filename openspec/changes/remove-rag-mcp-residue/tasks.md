## 1. Lock the v3 contract and regression guard

- [ ] 1.1 Update the baseline `public-library-api` specification to require legacy watcher migration and forbid the `rag-mcp` alias, matching this change delta; verify `openspec validate "remove-rag-mcp-residue" --strict` accepts the complete modified requirement.
- [ ] 1.2 Extend `tests/test_docs_references.py` to detect both `rag_mcp` and standalone `rag-mcp` across the live surface while exempting only the `llamaindex-rag-mcp` repository identifier and historical records; run the test and confirm it fails on the current legacy references before removing them.
- [ ] 1.3 Add regression coverage proving that `omrg` is the only packaged console script and that OMRG does not redirect a `rag-mcp` invocation; verify the new test fails before the alias is removed.

## 2. Remove the alias and migrate login watchers

- [ ] 2.1 Delete the `rag-mcp` entry from `[project.scripts]`, retaining only `omrg`; build the wheel in a clean temporary directory and verify its console entry points include `omrg` and exclude `rag-mcp`.
- [ ] 2.2 Change the LaunchAgent planner to resolve only `omrg` from `PATH` or the interpreter bin directory, with an actionable error when neither exists; add a regression test where only `rag-mcp` is discoverable and verify resolution still fails.
- [ ] 2.3 Change new watcher labels to `com.omrg.watch.*` and new logs to `~/Library/Logs/omrg`; verify rendered plists persist an absolute `omrg` command, the new label, and the new log paths.
- [ ] 2.4 Extend existing-plist discovery to inspect both OMRG and legacy label prefixes, verify the persisted watch path, and use the existing confirmation or `--force` removal flow to replace a matching legacy watcher; add tests for refusal without consent and successful forced migration.
- [ ] 2.5 Update installer and watcher help, errors, console output, docstrings, and test fixtures to name `omrg`; run `uv run pytest tests/unit/test_launchagent.py tests/test_install_login_watcher.py -q`.

## 3. Remove remaining live product-name residue

- [ ] 3.1 Replace product wording in CLI help, composition and configuration docstrings/comments, the OpenAPI contract, and transport documentation with `OMRG` or `OMRG — Opinionated Modular RAG`; rename the private `__RAG_MCP_PLAN_STOP__` sentinel and verify its sole producer and consumer still agree.
- [ ] 3.2 Update README, AGENTS.md, CLAUDE.md, CONTRIBUTING.md, `docs/ADR_README.md`, and `docs/guides/` example paths and prose; remove the README alias notice and point the absent NiftyPM bundle reference at `niftypm/omrg.json` without creating a new bundle.
- [ ] 3.3 Reconcile current baseline and active OpenSpec prose that still names the old product or stale `src/rag_mcp` paths, preserving each change's scope; use the OpenSpec update workflow for active changes and leave CHANGELOG, ADR, TDR, archived-change, GitHub URL, and Sonar project-key history unchanged.
- [ ] 3.4 Run ast-grep over Python string literals and identifiers plus a literal documentation scan; verify no live project reference remains to `rag_mcp`, standalone `rag-mcp`, or the old product name, and verify LlamaIndex library references and the GitHub repository identifier remain valid.

## 4. Clean up and validate

- [ ] 4.1 Confirm `git ls-files src/rag_mcp` is empty, then delete the untracked `src/rag_mcp/` directory and verify no tracked source file was removed.
- [ ] 4.2 Run the stale-reference guard and targeted CLI and LaunchAgent tests; verify the package exposes `omrg`, legacy watcher migration requires consent, and no fallback to `rag-mcp` occurs.
- [ ] 4.3 Run `openspec validate --all --strict`, update the graph with `graphify update .`, and run the required Aikido scan over changed source files; resolve every finding or record it as an explicit blocker.
- [ ] 4.4 With owner approval, run `uv run pytest -m "not slow" --cov=omrg`; record the command output and coverage result before the breaking-change commit.
- [ ] 4.5 Commit the completed implementation with a Conventional Commit breaking marker, such as `feat!: remove rag-mcp compatibility alias`, and verify semantic-release will publish v3.0.0.
