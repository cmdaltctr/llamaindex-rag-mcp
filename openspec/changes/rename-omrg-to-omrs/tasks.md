## 1. Set up

- [x] 1.1 Check `git worktree list` and that the main checkout is on `main`. Create the sibling worktree: `git worktree add -b feat/rename-omrg-to-omrs ../llamaindex-rag-mcp-feat-rename-omrg-to-omrs v4`. Verify `git rev-parse --show-toplevel` and `git branch --show-current` match before any command that changes state.
- [x] 1.2 In the new worktree run `uv sync --frozen --extra web`. Do not use `--all-extras`. Do not copy `.env`.
- [x] 1.3 Record the baseline: `./scripts/local_ci.sh` result, the executed and deselected counts from `tests/test_clean_base_tripwire.py`, and `uv run lint-imports`. Save the numbers in the change folder as `baseline.md`.
- [x] 1.4 Re-check that no active change modifies a baseline requirement heading that contains `omrg` (design D9). Run the check script from the recon (compare MODIFIED, RENAMED and REMOVED headings in `openspec/changes/*/specs` with the 12 baseline headings). Stop and report if one collides.
- [x] 1.5 `omrs` is free on PyPI (404 on 2026-10-22; `omrg` also 404). Re-check it just before the first release and record the date in `baseline.md`.
- [x] 1.6 Before any move, copy `~/.omrg` and `~/.config/omrg` to a dated backup folder outside the repository (keep secrets local, never upload). Task 7.2 uses a copy of this backup, not the live folders.

## 2. Guard and migration first (old names still in place)

- [x] 2.1 Write the guard test `tests/test_no_old_identity.py`: scan the live surface for `omrg` in any case. Use a named exemption list with a reason per entry (design D6). Confirm it FAILS on the current tree.
- [x] 2.2 Write failing tests for the startup check: an `OMRG_*` variable, `~/.omrg`, `~/.config/omrg`, and a `com.omrg.` plist each stop `omrs web start`, the CLI and the stdio MCP server with the replacement named. The stdio server writes to stderr only. A keychain entry alone does not stop startup and the check never calls the keychain. A clean install passes. `omrs migrate` and `--help` skip the check. Use a temp `HOME`.
- [x] 2.3 Implement the startup check in `config/legacy.py` or a sibling module, following the shape-aware retirement rule in its docstring. Keep `OMRG_*` flat names in the tripwire. Make the tests pass.
- [x] 2.4 Write failing tests for `omrs migrate`: dry run changes nothing; full migration (folders, `omrg.jsonc` to `omrs.jsonc`, secret references, keychain copy, launchd replacement); conflict refusal when both folders exist; second run is a no-op; remaining `OMRG_*` variables are listed; LanceDB data opens with unchanged contents. Mock keychain and launchd. Never read the real `~/.config/omrg`.
- [x] 2.5 Implement `transports/cli/migrate.py` (thin wrapper) and the move logic under `core/` or `integrations/` as the folder guides require. Reuse the legacy plist recognition in `_launchagent.py`. Never print secret values. Make the tests pass.
- [x] 2.6 Keep files under 500 lines (`tests/test_file_size_ceiling.py`). Commit: `uv run --no-sync git commit` with a Conventional Commit message.

## 3. Python package and build configuration

- [x] 3.1 `git mv src/omrg src/omrs`. Do the same for `ocr-workers/*/src/omrg_ocr_*` to `omrs_ocr_*` (confirmed by the owner).
- [x] 3.2 Run the ast-grep import rule on `src tests scripts experiments ocr-workers` (design D4). Review `git diff --stat`. Expect about 2,505 `from` statements in 467 files, 20 `import omrg` and 12 `import omrg.X`.
- [x] 3.3 Run the string-path rule for `patch`, `monkeypatch.setattr`, `import_module` and `mock.patch.object` first arguments. List the remaining bare `"omrg"` strings and decide each by hand (MCP name, keychain service, logger name, `metadata.version("omrg")`).
- [x] 3.4 Update `pyproject.toml`: project name, console script (`omrs = "omrs.transports.cli:run_cli"`), hatch `packages` and `force-include`, extras hints, coverage source, and the about 100 import-linter module strings including `root_package`. Remove the `omrg` script. Run `uv lock`.
- [x] 3.5 Update `.github/workflows/ci.yml` (lines near 94, 311, 523, 586), `codecov.yml`, `.coderabbit.yaml`, `scripts/local_ci.sh` and `.gitignore`.
- [x] 3.6 Update the tests that pin the name: `tests/unit/test_verification_gaps_boundaries.py`, `tests/test_clean_base_tripwire.py` (counts must match 1.3), `tests/test_file_size_ceiling.py`, `tests/test_docs_references.py`, `tests/conftest.py`.
- [x] 3.7 Run `uv run lint-imports`. Delete any stale `ignore_imports` entry it reports. Run `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q`, then the tripwire on its own. Fix until green.
- [x] 3.8 Commit this group.

## 4. Settings surface and runtime identifiers

- [x] 4.1 Rename the 13 `OMRG_*` variables to `OMRS_*` in `config/user_config.py`, `core/plugins/editor.py`, `core/vectordb/lancedb/meta.py` and every other reader. Update `.env.example`.
- [x] 4.2 Rename `omrg.jsonc` to `omrs.jsonc` and the config and data folder defaults (`config/user_config.py`, `core/workspace/cleanup.py`, `compose_profile_setup.py`, `transports/cli/web*.py`, `transports/cli/config.py`). Check that `omrs config init` builds its template from the `Settings` model with no template edit.
- [x] 4.3 Rename the secret reference path in the writer and the reader (`file://~/.config/omrs/secrets/<name>.key`).
- [x] 4.4 Rename the MCP server name (`transports/mcp/server.py`), keychain service (`integrations/keychain.py`), launchd labels and log folder (`_web_login_item.py`, `_launchagent.py`), logger name (`transports/api/security.py`) and the version-line regex in `_web_login_item.py`. Extend the legacy plist recognition to `com.omrg.*` (design D2).
- [x] 4.5 Rename the cookie and token prefixes (`transports/api/security.py`, `confirmations.py`) and the `x-omrg-*` keys in `transports/api/openapi.yaml`. Confirm the CI OpenAPI validation still passes.
- [x] 4.6 Keep `omrg_dataset_epoch` in `core/vectordb/lancedb/meta.py` and `omrg_task` (`TASK_LAYOUT_KEY`) in `core/workspace/records.py` as one constant each, with a comment (design D3). Add a test that opens a LanceDB fixture written with the old key and checks the BM25 cache token stays equal.
- [x] 4.7 Update the CLI help text and the `omrg web ...` hints in messages (about 30). Check `omrs --help` has no `OMRG`.
- [x] 4.8 Run the fast suite and the guard test. Commit this group.

## 5. Web workspace

- [x] 5.1 Load the `omrg-design` skill (the owner may have renamed it by now; use whichever name exists). Rename `web/package.json` name, `web/index.html` title and logo, `web/public/omrg-logo.svg`, and update `web/DESIGN.md` and `web/src/AGENTS.md`.
- [x] 5.2 Rename the five storage keys and their tests (`lib/preferences.ts`, `lib/navCollapsed.ts`, `studio/storage.ts` and the session and UI keys). Rename the `omrg_bt_` display text in `settings/McpHttpPanel.tsx`.
- [x] 5.3 Update `web/vite.config.ts` (`OMRS_API_URL`, build output `../src/omrs/transports/api/static`).
- [ ] 5.4 Run the web lint, typecheck, unit tests and build. Do a browser check at 1280 px and 390 px. Warn the owner before starting the dev server or a browser run.
- [x] 5.5 Commit this group.

## 6. Docs, specs and active changes

- [x] 6.1 Run the scripted pass (design D4, D5, D6) over `README.md`, `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, per-folder `AGENTS.md` and `CLAUDE.md` files, `docs/guides/`, `docs/proposals/`, `docs/roadmap/`, `plugins/`, `.agents/skills/omrg-design` (path only if tracked) and `.env.example`. Review the prose hits by hand.
- [x] 6.2 Update the project instructions: the Quick Reference commands, the `~/.config/omrs` text in gotcha 18, the `DATA/omrg/` text in gotcha 15 (keep the folder name, add the note from design D7) and the last-known-good block.
- [x] 6.3 Rewrite the live baseline specs in place: the token pass over the 124 requirement blocks and the 12 headings (design D9). Do not touch the two requirements that the delta files cover.
- [x] 6.4 Rewrite the five active changes with the same pass, including paths such as `src/omrg/core/...` in their tasks.
- [x] 6.5 Add one note to `docs/adr/ADR_README.md`: the project was named OMRG until this change and ADRs keep that name. Leave the ADR, TDR, archived-change, experiment and `CHANGELOG.md` files unchanged.
- [x] 6.6 Write `docs/adr/092-rename-omrg-to-omrs.md` with the decision, the alternatives from design D2 and D8, and the migration steps. Load `s-adr` first.
- [x] 6.7 Write a migration guide in `docs/guides/` (or extend `getting-started.md`) with the six user steps from design.md, the MCP client key step first.
- [x] 6.8 Do the documentation drift check: grep `docs/guides/` for `omrg`, `OMRG`, `~/.omrg` and `omrg.jsonc`. The guard test must pass. Then grep `openspec/specs/` and `openspec/changes/` (not `archive/`) for `omrg`. Each remaining hit must sit in a requirement that describes the old identity (design D9). List the hits in the commit message.
- [x] 6.9 Run `openspec validate --all --strict`. Commit this group.

## 7. Verify

- [x] 7.1 Run `./scripts/local_ci.sh` and compare with `baseline.md`. The tripwire executed and deselected counts must match. Coverage must stay at or above the floors.
- [x] 7.2 Run `omrs migrate` against a copy of the owner's real folders in a temp `HOME` (copy `~/.omrg` and `~/.config/omrg`; mock the keychain and launchd). Check the report and that the copied collections open and return search results.
- [x] 7.3 Run `openspec validate rename-omrg-to-omrs --strict`.
- [x] 7.4 Run `/opsx:verify` for this change.
- [x] 7.5 Build the wheel in a throwaway environment and check that `omrs` imports, `omrs --help` runs, the packaged YAML defaults load, and no `omrg` console script exists.
- [ ] 7.6 Open the pull request into `v4`: `gh pr create --base v4`. Title `feat!: rename OMRG to OMRS`. Wait for the required checks.

## 8. Owner hand-off (outside the repository; the agent cannot do these)

- [ ] 8.1 Rename the `omrg` key in `~/.claude.json` to `omrs`. Check `~/.claude/settings*.json`, `~/.config/opencode/` and `~/.codex/` for prompts or allow-lists that name `mcp__omrg__*`. Restart the clients.
- [ ] 8.2 Run `omrs migrate --dry-run`, then `omrs migrate`, on the owner's machine. Set `OMRS_*` variables for the ones the report lists. Create new bearer tokens if needed.
- [ ] 8.3 Rename the `omrg-design` and `s-preserve-omrg` skill folders and their frontmatter `name`, plus any `.claude/skills/` copies.
- [ ] 8.4 Add a note to `DATA/omrg/DATA_LOCATIONS.md` that the project is now OMRS and the folder name is historical (design D7).
- [ ] 8.5 Rename `niftypm/omrg.json` and the NiftyPM project title.
- [ ] 8.6 Decide on the GitHub repository name. Update the Sonar project key if it changes.
- [ ] 8.7 After the pull request merges, remove the worktree. Copy preserve-class gitignored data first (gotcha 15), verify the copy and never copy `.env`.
- [ ] 8.8 Archive the change with `/opsx:archive`.
