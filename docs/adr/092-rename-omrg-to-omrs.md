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
documents and every runtime identifier. The owner also had a live install: a
settings file, secrets, a keychain entry and a login item under the old names.

No v4 feature had shipped when the rename started. Two v4 changes were planned
but not built. They could adopt the new name at no cost. Each later feature
would add more code and text under the old name.

## Decision

Rename the project to OMRS ("Opinionated Modular RAG System") in one change.
The package, distribution, command, environment prefix, config and data
folders, MCP server name, keychain service, launchd labels, auth prefixes,
OpenAPI extensions and browser storage keys all move to `omrs`.

Rules:

1. **Clean cut.** The old names stop working. There is no alias, no shim and no
   silent fallback. This follows ADR-060.
2. **Startup check.** Every transport checks for an install from before the
   rename and stops, naming the replacement and the command `omrs migrate`.
   The check reads only environment variables, folder names and file names in
   `~/Library/LaunchAgents`. It never calls the keychain.
3. **`omrs migrate`.** The command moves the data folder and config folder,
   rewrites secret references, copies keychain entries (the old entries stay),
   replaces login items and rewrites the absolute paths that `workspace.db`
   stores in `runs.inputs_json`. It has a dry run, refuses to overwrite a target
   and is safe to run again.
4. **Stored identifiers keep their name.** The LanceDB key `omrg_dataset_epoch`
   and the workspace layout key `omrg_task` live inside existing data. A rename
   would make every BM25 cache token compare unequal and would stop job
   pipelines being recognised. Each is one constant with a comment.
5. **Auth and wire names move.** The session cookie, the token prefixes and the
   `x-omrg-*` OpenAPI keys move. Old bearer tokens stop working. Sessions
   re-issue at the next sign-in. Browser drafts reset once. There is no shim.
6. **History stays.** ADRs, TDRs, archived changes, experiment reports and
   `CHANGELOG.md` keep the old name. A guard test (`tests/test_no_old_identity.py`)
   fails when a live file names the old identity. Each exemption states a reason.
7. **`DATA/omrg/` keeps its name.** It holds 90 GB, a checksum registry and copy
   receipts, and `s-preserve-omrg` and gotcha 15 hard-code the path.
8. **Release.** The commit type is `feat!:`, so python-semantic-release makes a
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
- The owner must do several steps outside the repository.
- "System" makes the long name longer. Tables and help text wrap more.
- The names OMRS and OMMS differ by one letter, so typos between them are likely.

### Neutral

- The GitHub repository name `llamaindex-rag-mcp` already differed from `omrg`
  and stays as it is.
- The rollback is a revert of the merge commit, plus `mv ~/.omrs ~/.omrg` and
  `mv ~/.config/omrs ~/.config/omrg` on an installed machine.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Display name only** | Leaves the `omrg` command and the tool-prefix collision that caused the change (D1). |
| **Dual-read with a fallback to the old names** | A silent fallback hides a half-migrated install, doubles the settings paths to test, and needs its own retirement date (D2). |
| **Keychain entry as a startup sign** | `omrs migrate` leaves the old entry in place, so a correct migration would still be refused. A keychain read can also show a system prompt on every start (D2a). |
| **Rename `omrg_dataset_epoch` and `omrg_task`** | Both are stored inside existing data. A rename breaks the BM25 cache token and the job-pipeline marker (D3). |
| **Read old bearer tokens and storage keys, then write new ones** | Needs a shim with its own retirement date. The owner chose a clean cut (D8). |
| **Rename `DATA/omrg/` now** | 90 GB, a checksum registry and hard-coded paths. A later, separate decision (D7). |
| **Do nothing** | The collision stays and grows with every feature. |

## Migration steps

For an existing install:

1. Upgrade the package.
2. Run `omrs migrate --dry-run` and read the plan.
3. Run `omrs migrate`.
4. Set `OMRS_*` for each old variable that the report lists.
5. Rename the MCP client key to `omrs` and restart the client.
6. Create new bearer tokens if any were in use.

## References

- `src/omrs/config/legacy_install.py`: the startup check.
- `src/omrs/integrations/legacy_migration.py` and `src/omrs/transports/cli/migrate.py`: the migrate command.
- `tests/test_no_old_identity.py`: the guard and its exemptions.
- [Migration guide](../guides/migrating-from-omrg.md)
- [ADR-060](060-omrg-is-a-framework-mcp-is-a-transport.md): the earlier rename.
