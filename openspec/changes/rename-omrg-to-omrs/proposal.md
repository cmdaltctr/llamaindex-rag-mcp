# Proposal

## Why

The project name OMRG ("Opinionated Modular RAG") sits one letter from OMMS ("Opinionated Modular Memory System"), the owner's other project. The two names collide in conversation, in tool prefixes (`mcp__omrg__*` and `mcp__omms__*`), in skills and in file paths. OMRS ("Opinionated Modular RAG System") makes the pair read as a matched set: OMRS retrieves, OMMS remembers.

Why now: v4 is the integration branch and no v4 feature has shipped. Two v4 changes (`authority-aware-retrieval`, `mantiq-reasoning-gates`) are planned but not implemented, so they can adopt the new name at no cost. Each later feature adds more code, specs and docs that carry the old name. The v3 rename from `rag_mcp` to `omrg` (ADR-060) set the pattern: one mechanical change, no shim.

## What Changes

- **Python package.** `src/omrg/` becomes `src/omrs/`. All `from omrg...` and `import omrg` statements move to `omrs` (about 2,500 import statements in 467 files, found by ast-grep), plus about 940 dotted-path strings such as `patch("omrg.x.y")` and `import_module`.
- **Distribution and command.** `pyproject.toml` name, console script, hatch paths, import-linter contracts (about 100 module strings), coverage source, CI and `codecov.yml` paths all move to `omrs`. `uv.lock` is regenerated. The `omrg` console command is removed with no alias (same rule as ADR-060).
- **Display name.** "OMRS, Opinionated Modular RAG System" replaces "OMRG, Opinionated Modular RAG" in live docs, CLI help, the web workspace title, the OpenAPI title and the MCP server name.
- **Settings surface.** Env prefix `OMRG_` becomes `OMRS_` (13 variables). Config file `omrg.jsonc` becomes `omrs.jsonc`. Config folder `~/.config/omrg` becomes `~/.config/omrs`. Data folder `~/.omrg` becomes `~/.omrs`. Secret references `file://~/.config/omrg/secrets/...` become `file://~/.config/omrs/secrets/...`.
- **Runtime identifiers.** MCP server name, macOS keychain service, launchd labels (`com.omrg.web`, `com.omrg.watch.*`), the log folder, the logger name, the session cookie and the `omrg_bt_` / `omrg_bs_` / `omrg_ss_` token prefixes, and the `x-omrg-*` OpenAPI extensions all move to `omrs`.
- **Web workspace.** `web/package.json` name, page title, logo file and five browser storage keys (`omrg-preferences`, `omrg-nav-collapsed`, `omrg-canvas-draft:`, `omrg-canvas-session`, `omrg-workspace-ui`) move to `omrs`.
- **Stored keys.** The LanceDB key `omrg_dataset_epoch` and the workspace layout key `omrg_task` move to `omrs`. Old tables fall back to the existing unmarked-table path until their next write, so no re-ingest is needed.
- **No migration code.** The owner is the only user. There is no startup check and no `omrs migrate` command. The owner's install moves once, by hand, after the merge (design Migration Plan).
- **Large-data folder.** `~/Development/DATA/omrg/` becomes `DATA/omrs/`, with its symlinks, registry and the preserve skill updated.
- **Live docs and specs.** `README.md`, `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, per-folder `AGENTS.md`, `docs/guides/`, `docs/proposals/`, `.env.example`, the live `openspec/specs/` baselines and the five active changes are rewritten.
- **History stays.** ADRs, TDRs, archived OpenSpec changes (128), run experiment records and `CHANGELOG.md` keep the old name. Only unrun experiments are renamed. One note in `docs/adr/ADR_README.md` explains the rename. ADR file names keep `omrg` so existing links hold.
- **ADR-092** records the decision.
- **Owner hand-off (outside the repo).** Edit the MCP client key in `~/.claude.json`, rename the `omrg-design` and `s-preserve-omrg` skills, update `DATA_LOCATIONS.md`, rename the NiftyPM source file and decide on the GitHub repository name. The change lists each step. The repo change cannot do them.

**BREAKING.** Import path, console command, env prefix, config and data folders, MCP tool prefix, launchd labels, keychain service and auth token prefixes all change. Stored vector data stays compatible. A major version bump follows from `feat!:`.

## Capabilities

### New Capabilities

- `project-identity`: the one place that states the project name, display name, package and distribution name, console command, MCP server name, env prefix, config and data folder names, keychain service, launchd labels, auth prefixes and browser storage key prefix; the stored-data identifiers that deliberately keep an old name; and the guard that stops live files from naming the old identity.

### Modified Capabilities

- `public-library-api`: the requirement "Package identity is `omrg`" becomes "Package identity is `omrs`". The scenarios for the import path, the entry point and the removed command move to the new names. The `omrg` command is itself absent after the change.
- `settings-file`: the settings file name, the config folder, the `OMRS_CONFIG_DIR` variable and the secret-reference path move to `omrs`.

Other live specs (about 32 more, 124 requirement blocks) change only the name token inside text. They are rewritten in place during apply, as the v3 rename did, and recorded in design.md. They need no delta because no behaviour in them changes.

## Impact

- **Code:** `src/omrg/` (189 files), `tests/` (395 files), `scripts/`, `experiments/*.py`, `ocr-workers/*/src/omrg_ocr_*`, `web/` (98 files mention the name).
- **Config and tooling:** `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, `codecov.yml`, `.coderabbit.yaml`, `scripts/local_ci.sh`, `.env.example`, `.gitignore`.
- **Tests that pin the name:** `tests/unit/test_verification_gaps_boundaries.py`, `tests/test_clean_base_tripwire.py` (its executed and deselected counts must not change), `tests/test_file_size_ceiling.py`, `tests/test_docs_references.py`, `tests/conftest.py`.
- **Specs and docs:** about 460 name occurrences in live specs, about 860 in live docs, about 120 in the five active changes.
- **Users:** the owner moves their install once, by hand. MCP clients lose the `mcp__omrg__*` tools until the client key changes.
- **Distribution:** a new PyPI project name. `omrs` is free (404 on 2026-10-22); re-check before the first release.
- **Dependencies:** none added.
