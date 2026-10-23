## 1. Set up

- [x] 1.1 Check `git worktree list` and that the main checkout is on `main`. Create the sibling worktree: `git worktree add -b feat/rename-omrg-to-omrs ../llamaindex-rag-mcp-feat-rename-omrg-to-omrs v4`. Verify `git rev-parse --show-toplevel` and `git branch --show-current` match before any command that changes state.
- [x] 1.2 In the new worktree run `uv sync --frozen --extra web`. Do not use `--all-extras`. Do not copy `.env`.
- [x] 1.3 Record the baseline: `./scripts/local_ci.sh` result, the executed and deselected counts from `tests/test_clean_base_tripwire.py`, and `uv run lint-imports`. Save the numbers in the change folder as `baseline.md`.
- [x] 1.4 Re-check that no active change modifies a baseline requirement heading that contains `omrg` (design D9). Run the check script from the recon (compare MODIFIED, RENAMED and REMOVED headings in `openspec/changes/*/specs` with the 12 baseline headings). Stop and report if one collides.
- [x] 1.5 `omrs` is free on PyPI (404 on 2026-10-22; `omrg` also 404). Re-check it just before the first release and record the date in `baseline.md`.
- [x] 1.6 Before any move, copy `~/.omrg` and `~/.config/omrg` to a dated backup folder outside the repository (keep secrets local, never upload). Task 7.2 uses a copy of this backup, not the live folders.

## 2. Guard first (old names still in place)

- [x] 2.1 Write the guard test `tests/test_no_old_identity.py`: scan the live surface for `omrg` in any case. Use a named exemption list with a reason per entry (design D6). Confirm it FAILS on the current tree.
- [x] 2.2 A startup check and an `omrs migrate` command were built and tested against a copy of the owner's data, then removed on the owner's call on 2026-10-22: the owner is the only user (design D2). The owner's install moves by hand (task 8.2).
- [x] 2.3 Keep files under 500 lines (`tests/test_file_size_ceiling.py`). Commit: `uv run --no-sync git commit` with a Conventional Commit message.

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
- [x] 4.6 Rename the stored keys to `omrs_dataset_epoch` (`core/vectordb/lancedb/meta.py`) and `omrs_task` (`core/workspace/records.py`). Old tables use the existing unmarked-table path until their next write (design D3).
- [x] 4.7 Update the CLI help text and the `omrg web ...` hints in messages (about 30). Check `omrs --help` has no `OMRG`.
- [x] 4.8 Run the fast suite and the guard test. Commit this group.

## 5. Web workspace

- [x] 5.1 Load the `omrg-design` skill (the owner may have renamed it by now; use whichever name exists). Rename `web/package.json` name, `web/index.html` title and logo, `web/public/omrg-logo.svg`, and update `web/DESIGN.md` and `web/src/AGENTS.md`.
- [x] 5.2 Rename the five storage keys and their tests (`lib/preferences.ts`, `lib/navCollapsed.ts`, `studio/storage.ts` and the session and UI keys). Rename the `omrg_bt_` display text in `settings/McpHttpPanel.tsx`.
- [x] 5.3 Update `web/vite.config.ts` (`OMRS_API_URL`, build output `../src/omrs/transports/api/static`).
- [x] 5.4 Run the web lint, typecheck, unit tests and build. Do a browser check at 1280 px and 390 px. Warn the owner before starting the dev server or a browser run. Lint, typecheck, 1750 unit tests and the build passed in local CI. Browser check on 2026-10-23 from `v4` at `2d93b01`, in an Orca tab against a scratch `omrs web` server (empty workspace and config folder, own port): Home, Chat, Knowledge Base, Studio, Experiments, Integrations and Settings at 1280 px and 390 px, dark and light. All show the title "OMRS workspace" and the OMRS name, no old name, no horizontal overflow, no console errors. Settings shows `omrs.jsonc`, the `omrs` MCP server key and the `omrs_mcp_` token prefix. The favicon is `omrs-logo.svg`. The theme switch writes `omrs-preferences` and nothing under the old key.
- [x] 5.5 Commit this group.

## 6. Docs, specs and active changes

- [x] 6.1 Run the scripted pass (design D4, D5, D6) over `README.md`, `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, per-folder `AGENTS.md` and `CLAUDE.md` files, `docs/guides/`, `docs/proposals/`, `docs/roadmap/`, `plugins/`, `.agents/skills/omrg-design` (path only if tracked) and `.env.example`. Review the prose hits by hand.
- [x] 6.2 Update the project instructions: the Quick Reference commands, the `~/.config/omrs` text in gotcha 18, the `DATA/omrg/` text in gotcha 15 (keep the folder name, add the note from design D7) and the last-known-good block.
- [x] 6.3 Rewrite the live baseline specs in place: the token pass over the 124 requirement blocks and the 12 headings (design D9). Do not touch the two requirements that the delta files cover.
- [x] 6.4 Rewrite the four active changes that are not run experiments with the same pass, including paths such as `src/omrg/core/...` in their tasks. Keep `experiment-42-clef-flash-confirmation` (run) and the 56 run-experiment scripts that nothing imports as they were (design D6).
- [x] 6.5 Add one note to `docs/adr/ADR_README.md`: the project was named OMRG until this change and ADRs keep that name. Leave the ADR, TDR, archived-change, experiment and `CHANGELOG.md` files unchanged.
- [x] 6.6 Write `docs/adr/092-rename-project-to-omrs.md` with the decision, the alternatives from design D2 and D8, and the migration steps. Load `s-adr` first.
- [x] 6.7 Record the owner's one-off move in design.md (Migration Plan) and ADR-092. No user guide: the owner is the only user.
- [x] 6.8 Do the documentation drift check: grep `docs/guides/` for `omrg`, `OMRG`, `~/.omrg` and `omrg.jsonc`. The guard test must pass. Then grep `openspec/specs/` and `openspec/changes/` (not `archive/`) for `omrg`. Each remaining hit must sit in a requirement that describes the old identity (design D9). List the hits in the commit message.
- [x] 6.9 Run `openspec validate --all --strict`. Commit this group.

## 7. Verify

- [x] 7.1 Run `./scripts/local_ci.sh` and compare with `baseline.md`. The tripwire executed and deselected counts must match. Coverage must stay at or above the floors.
- [x] 7.2 Removed with the migrate command (design D2). The command ran once against a copy of the owner's folders before removal: four collections opened unchanged.
- [x] 7.3 Run `openspec validate rename-omrg-to-omrs --strict`.
- [x] 7.4 Run `/opsx:verify` for this change.
- [x] 7.5 Build the wheel in a throwaway environment and check that `omrs` imports, `omrs --help` runs, the packaged YAML defaults load, and no `omrg` console script exists.
- [x] 7.6 Open the pull request into `v4`: `gh pr create --base v4`. Title `feat!: rename OMRG to OMRS`. Wait for the required checks. Done: PR #125, all required checks green after the tripwire re-pin, merged into `v4` as `2d93b01` on 2026-10-23.

## 8. Owner hand-off (outside the repository; the agent cannot do these)

- [x] 8.1 Replace the `omrg` MCP client entry with `omrs` (`claude mcp remove omrg -s local`, `claude mcp add omrs -s local -- sh -c 'cd "$HOME/.omrs" && exec omrs'`, main checkout). It connects. No settings, OpenCode or Codex config named `mcp__omrg__*`; only old session logs do.
- [x] 8.2 Move the owner's install (2026-10-22): fresh backup in `DATA/omrs/backups/pre-live-move-2026-10-22/` (deleted after the reinstall from `v4` checked out), `omrs[web,hybrid]` installed from this worktree, old app and four `omrg` MCP servers stopped, `~/.omrs`, `~/.config/omrs` and `~/Library/Logs/omrs` moved, `omrs.jsonc` paths rewritten, `workspace.db` updated (1 pipeline, 10 runs), `com.omrs.web` installed and running, old tool removed. All four collections hold the same row counts as before. No keychain entry and no `OMRG_*` variable existed.
- [x] 8.3 Rename the `omrg-design` and `s-preserve-omrg` skill folders and their frontmatter `name` to `omrs-design` and `s-preserve-omrs`. `~/.claude/skills` is a link to `~/.agents/skills`, so there is one copy.
- [x] 8.4 Rename `~/Development/DATA/omrg/` to `DATA/omrs/` (2026-10-22). Repoint the six symlinks in four worktrees. Update `DATA_LOCATIONS.md`, the global agent instructions, the `s-preserve-omrg` skill and the memory file.
- [x] 8.5 Rename `niftypm/omrg.json` and the NiftyPM project title. Done 2026-10-23 with the NiftyPM local MCP: board project `KJ1kaUGQe8` renamed to "OMRS (Opinionated Modular RAG System)" and read back (progress and points unchanged). `niftypm/omrs.json` created in this checkout (49 tasks). The five v3 mirror files were renamed to `omrs*`.
- [x] 8.6 Decide on the GitHub repository name. Update the Sonar project key if it changes. Done 2026-10-23: renamed to `cmdaltctr/omrs` (GitHub redirects the old URL), description set in the OMMS style, `origin` repointed in all five checkouts. The Sonar key `cmdaltctr_llamaindex-rag-mcp` is set in SonarCloud, not in this repo; `.sonarlint/connectedMode.json` is left as is until the SonarCloud project is renamed.
- [x] 8.7 After the pull request merges, remove the worktree. Copy preserve-class gitignored data first (gotcha 15), verify the copy and never copy `.env`. Done 2026-10-23: worktree clean and merged into `origin/v4`; only regenerable files (`.venv`, `node_modules`, build output, `graphify-out`) were ignored, so nothing needed copying. Worktree removed, local and remote branch deleted.
- [x] 8.8 Archive the change with `/opsx:archive`. Done 2026-10-23: delta specs synced to `openspec/specs/` (new `project-identity`, replaced requirements in `public-library-api` and `settings-file`), then archived.
