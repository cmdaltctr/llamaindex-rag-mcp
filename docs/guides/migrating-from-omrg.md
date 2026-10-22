# Migrating from OMRG to OMRS

The project was named OMRG until ADR-092. It is now OMRS, "Opinionated Modular
RAG System". The old names stop working. An install from before the rename
needs the six steps below, once.

Your vector data stays readable. You do not need to ingest again.

## What changed

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
| Bearer token prefix | `omrg_bt_` | `omrs_bt_` |

Two names stay as they were, because they live inside existing data: the
LanceDB key `omrg_dataset_epoch` and the workspace layout key `omrg_task`.

## Steps

1. **Rename the MCP client key.** Open the config file of each MCP client, for
   example `~/.claude.json`. Rename the server key `omrg` to `omrs`. Search the
   prompts, skills and allow-lists of the client for `mcp__omrg__`, and change
   them to `mcp__omrs__`. The tool prefix follows this key. Restart the client
   after step 3.
2. **Install the new package.** Install `omrs`. The `omrg` command no longer
   exists. After the install, every `omrs` command stops with a message while
   old names remain on the machine. The message names each one.
3. **Move the install.**
   1. Run `omrs migrate --dry-run`. Read the plan.
   2. Run `omrs migrate`. Answer yes when asked. macOS can ask for permission
      to read the keychain.

   The command renames the data and config folders, renames `omrg.jsonc` to
   `omrs.jsonc`, rewrites secret references, copies keychain entries, replaces
   login items and rewrites the upload paths that saved runs hold. It prints no
   secret value. If it stops, fix the cause and run it again. It continues where
   it stopped.
4. **Rename environment variables.** The report lists each `OMRG_*` variable that
   is still set. Rename each one to `OMRS_*` in your shell profile. The command
   does not edit shell profiles. It also lists names found in `~/.omrs/.env`.
5. **Create new bearer tokens.** Old tokens with the `omrg_bt_` prefix stop
   working. Create new ones in the Settings page of the web workspace. Sign in
   again in the browser. Unsent canvas drafts reset once.
6. **Check.** Run `omrs web start` or start your MCP client. Run
   `omrs migrate` again. It must report that nothing is left to migrate.

## Roll back

`omrs migrate` renames folders, so a rollback is two renames, with the previous
package version installed:

```bash
mv ~/.omrs ~/.omrg
mv ~/.config/omrs ~/.config/omrg
```

The keychain copy leaves the old entry in place. The login item has no
automatic rollback. Install it again with the old version.

## Related

- [ADR-092](../adr/092-rename-omrg-to-omrs.md)
- [Configuration](configuration.md)
