# Proposal

## Why

To add an optional integration (for example the Anthropic Chat provider), the user must leave the app, run a `uv` command in a terminal and restart the server. The Integrations page shows `uv sync --extra <name>` for every entry. That is the right command only in a development checkout. It is the wrong command for the usual install, a `uv tool` install that runs as the login item. The user wants one Install button that does the work.

## What Changes

- **BREAKING (spec rule):** the Integrations page may now install packages. The current rule "the page SHALL NOT install, download or modify packages itself" is replaced by a guarded install action.
- Add an Install button to each integration that is not installed, when the server can install into itself. Pressing it opens a confirm dialog that names the packages. Confirming installs the extra's requirements into the running server's own Python environment. It does not rebuild OMRS.
- After a successful install, offer the existing restart action. The entry shows "Installed, restart to use" until the restart.
- Show live progress and, on failure, the last lines of the install output.
- Allow only one install at a time. Allow only extras from a fixed list built into the server. Exclude `web` (already present when the page runs) and `torch` (several GB, opt-in only, ADR-073).
- Show the button only when the server runs as a `uv tool` install (it finds `uv-receipt.toml` beside its own Python) and can find the `uv` program. Otherwise, show the command to copy.
- Show the correct copy command for each install type:
  - `uv tool` install: `uv tool install --reinstall "omrs[<current extras>,<extra>] @ <source>"`, read from the receipt
  - development checkout: `uv sync --extra <extra>`
- Tell the user that a later manual reinstall drops a package added by the button unless they use the lasting command shown on the entry.
- Provider cards under Settings > Providers link "Not installed" to the matching Integrations entry instead of printing a command.

## Capabilities

### New Capabilities

- `integration-install`: the server-side install action for optional extras, including the install type detection, the allowed extras, the single running install, progress, and the safety limits.

### Modified Capabilities

- `workspace-integrations`: entries get an Install button and the correct copy command for the install type. The rule that the page never installs is replaced.
- `llm-provider-settings`: a provider card that is not installed links to its Integrations entry.

## Impact

- New routes: `POST /v1/integrations/{extra}/install` (browser session, `manage` scope) and `GET /v1/integrations/install` (status of the running or last install). The OpenAPI contract gets both.
- `transports/api/integrations_catalogue.py`: adds the install type, the lasting command and whether each entry can be installed. A new module runs the install job.
- The server starts a subprocess: `uv pip install --python <own Python> <requirements of the extra>`. The command is a list of arguments with no shell and no user text. It uses the network to reach the package index.
- Web: `web/src/integrations/IntegrationCard.tsx` and a confirm dialog; `web/src/settings/ProviderCard.tsx`.
- No new dependency.
- Records: an ADR for "the app may install extras into itself" (task 6.1).
- Docs: `docs/guides/web-workspace.md` (Integrations section) and `docs/guides/cli-reference.md` (lasting install command).
- Interaction with `add-chat-reasoning-and-usage`: its "fix" line for a provider that is not installed links to the Integrations entry. Implement this change after that one, in the same worktree.
