# ADR-092: Rename OMRG to OMRS

- **Date:** 2026-10-22
- **Status:** Proposed
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-060](060-omrg-is-a-framework-mcp-is-a-transport.md) (the earlier rename to OMRG, no shim), [ADR-087](087-settings-live-in-omrg-jsonc.md) (settings file), [ADR-088](088-persistent-workspace-sign-in-secret.md) (sign-in secret)
- **Change:** `openspec/changes/rename-omrg-to-omrs/` (design D1 to D11)

## Context

The project was named OMRG ("Opinionated Modular RAG"). The name differs by one
letter from OMMS ("Opinionated Modular Memory System"), the owner's other
project. The two names collided in speech, in tool prefixes (`mcp__omrg__*` and
`mcp__omms__*`), in skills and in file paths.

The old name lived in about 3,000 code locations, 34 live specs, 31 live
documents and every runtime identifier. The owner, the only user, also had a live
install: a settings file, secrets, a keychain entry and a login item under the
old names.

No v4 feature had shipped when the rename started. Two v4 changes were planned
but not built. They could adopt the new name at no cost. Each later feature
would add more code and text under the old name.

## Decision

Rename the project to OMRS ("Opinionated Modular RAG System") in one change.
The package, distribution, command, environment prefix, config and data
folders, MCP server name, keychain service, launchd labels, auth prefixes,
OpenAPI extensions and browser storage keys all move to `omrs`.

Rules:

1. **Clean cut, no migration code.** The old names stop working. There is no
   alias, no shim, no startup check and no migration command. The owner is the
   only user, so migration code would be dead weight after one run. This follows
   ADR-060. A startup check and an `omrs migrate` command were built and tested,
   then removed on the owner's call.
2. **Stored keys move too.** The LanceDB key becomes `omrs_dataset_epoch` and the
   workspace layout key becomes `omrs_task`. A table written before the rename
   takes the existing unmarked-table path: it opens unchanged, BM25 uses the
   process-local counter, and the next write gives it an epoch. No re-ingest.
3. **Auth and wire names move.** The session cookie, the token prefixes and the
   `x-omrg-*` OpenAPI keys move. Old bearer tokens stop working. Sessions
   re-issue at the next sign-in. Browser drafts reset once. There is no shim.
4. **History stays.** ADRs, TDRs, archived changes, run experiment records and
   `CHANGELOG.md` keep the old name. Only unrun experiments are renamed. A guard
   test (`tests/test_no_old_identity.py`) fails when a live file names the old
   identity. Each exemption states a reason.
5. **`DATA/omrg/` becomes `DATA/omrs/`.** A same-disk rename of 90 GB, with its
   symlinks, registry and the preserve skill updated. Receipts and recovery
   files inside keep the old path as history.
6. **Release.** The commit type is `feat!:`, so python-semantic-release makes a
   major version. `omrs` was free on PyPI on 2026-10-22. `omrg` was never
   published, so no stub is needed.

## Consequences

### Positive

- The two projects read as a matched set: OMRS retrieves, OMMS remembers.
- No tool-prefix collision between the two projects.
- The guard test stops the old name returning unnoticed.
- Stored vector data stays readable with no re-ingest.

### Negative

- A breaking change for every install: import path, command, environment
  prefix, folders, MCP tool prefix, login items, keychain service and tokens.
- MCP clients lose their tools until the client key changes to `omrs`.
- The owner moves the live install by hand, once (steps below).
- The BM25 cache of an old table uses the process-local counter until that
  table's next write.
- "System" makes the long name longer. Tables and help text wrap more.
- The names OMRS and OMMS differ by one letter, so typos between them are likely.

### Neutral

- The GitHub repository name `llamaindex-rag-mcp` already differed from `omrg`
  and stays as it is.
- The rollback is a revert of the merge commit, plus the reverse of the folder
  moves below, with the previous package version installed.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Display name only** | Leaves the `omrg` command and the tool-prefix collision that caused the change (D1). |
| **Dual-read with a fallback to the old names** | A silent fallback hides a half-migrated install, doubles the settings paths to test, and needs its own retirement date. |
| **A startup check and an `omrs migrate` command** | Built and tested, then removed. The owner is the only user; a one-off manual move is cheaper than code to keep. |
| **Keep `omrg_dataset_epoch` and `omrg_task`** | Leaves the old name in live code for good. The store already handles a table with no epoch. |
| **Read old bearer tokens and storage keys, then write new ones** | Needs a shim with its own retirement date. The owner chose a clean cut. |
| **Keep the name `DATA/omrg/`** | Leaves the old name in live paths and docs. The rename is instant on the same disk. |
| **Do nothing** | The collision stays and grows with every feature. |

## Old and new names

| Item | Old | New |
| --- | --- | --- |
| Python package and command | `omrg` | `omrs` |
| Environment variables | `OMRG_*` | `OMRS_*` |
| Settings file | `omrg.jsonc` | `omrs.jsonc` |
| Config folder | `~/.config/omrg` | `~/.config/omrs` |
| Data folder | `~/.omrg` | `~/.omrs` |
| MCP tool prefix | `mcp__omrg__*` | `mcp__omrs__*` |
| Keychain service | `omrg` | `omrs` |
| Login items | `com.omrg.*` | `com.omrs.*` |
| Cookie and token prefixes | `omrg_session`, `omrg_bs_`, `omrg_ss_`, `omrg_bt_` | `omrs_session`, `omrs_bs_`, `omrs_ss_`, `omrs_bt_` |
| OpenAPI keys | `x-omrg-*` | `x-omrs-*` |
| Browser storage keys | `omrg-*` | `omrs-*` |
| Stored LanceDB key | `omrg_dataset_epoch` | `omrs_dataset_epoch` |
| Stored layout key | `omrg_task` | `omrs_task` |
| Large-data folder | `~/Development/DATA/omrg` | `~/Development/DATA/omrs` |

## Migration steps

For the owner's install, once. Done on 2026-10-22 from the feature branch, before the merge. Stop the app first.

1. Install the new package and remove the old `omrg` tool.
2. Move the folders: `mv ~/.omrg ~/.omrs` and `mv ~/.config/omrg ~/.config/omrs`.
   Rename `omrg.jsonc` to `omrs.jsonc` and change `/omrg/secrets/` to
   `/omrs/secrets/` inside it.
3. In `~/.omrs/workspace/workspace.db`, replace `"omrg_task"` with `"omrs_task"` in
   `pipelines.layout_json`, and `/.omrg/` with `/.omrs/` in `runs.inputs_json`.
4. Copy the keychain entries from service `omrg` to `omrs`.
5. Unload `com.omrg.web`, delete its plist and run `omrs web install`.
6. Rename any `OMRG_*` variables in the shell profile. Rename the MCP client key
   to `omrs` and restart the clients. Create new bearer tokens if any were in use.

Rollback, with the previous package version installed:

```bash
mv ~/.omrs ~/.omrg
mv ~/.config/omrs ~/.config/omrg
```

## References

- `tests/test_no_old_identity.py`: the guard and its exemptions.
- `openspec/changes/rename-omrg-to-omrs/design.md`: decisions D1 to D11.
- [ADR-060](060-omrg-is-a-framework-mcp-is-a-transport.md): the earlier rename.
