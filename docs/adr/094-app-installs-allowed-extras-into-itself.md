# ADR-094: The App Installs Allowed Extras into Its Own Environment

- **Date:** 2026-10-24
- **Status:** Proposed
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-073](073-make-the-torch-extra-a-normal-choice.md) (the torch extra), [ADR-085](085-web-login-item.md) (web login item), [ADR-086](086-web-power-menu.md) (power menu), [ADR-087](087-settings-live-in-omrg-jsonc.md) (settings in `omrs.jsonc`)
- **Change:** `openspec/changes/install-integrations-from-the-app/` (design D1 to D4); amended by `harden-integration-installs` (decisions 7 to 9); `torch` allowed on 2026-10-24 (decision 3)

## Context

An optional integration, such as the Anthropic Chat provider, is a package
extra. To add one, the user had to leave the app, run a `uv` command in a
terminal and restart the server. The Integrations page printed
`uv sync --extra <name>` for every entry. That command is right only in a
development checkout. The usual install is a `uv tool` install that runs as the
login item, and there the command does nothing useful.

The `workspace-integrations` spec said the page "SHALL NOT install, download or
modify packages itself". The user asked for one Install button instead.

Three facts shape the decision:

- The `uv tool` environment holds `uv-receipt.toml`. The receipt records the
  requirement, for example `omrs[web,hybrid]`, built from a project folder.
- That folder is a working checkout. It can hold uncommitted code and a stale
  web build, because the built pages are not committed.
- The installed package metadata lists every extra and its requirements, so
  the server knows what to install without the source folder.

## Decision

1. **Install with `uv pip install` into the server's own Python.** The job runs
   `uv pip install --python <sys.executable> <requirements>`. The requirements
   are the extra's lines from the installed OMRS metadata, with the
   `extra ==` marker removed. OMRS itself is not rebuilt or reinstalled.
2. **Install only from a `uv tool` install with `uv` found.** The server is a
   `uv tool` install when `uv-receipt.toml` sits in its own environment folder.
   `uv` is found on `PATH`, then in `~/.local/bin`, then in `~/.cargo/bin`,
   because the login item has a short `PATH`. A checkout or any other install
   shows a copy command and never installs.
3. **Only a fixed list of extras.** The list is the catalogue extras, without
   `web` (present when the page runs). `torch` was excluded at first; since
   2026-10-24 it is allowed, and its card shows the download size (about
   170 MB on a Mac, several GB for a GPU build) before the install. No request text reaches the command except the choice of a listed
   extra. The argument list is built in code and runs with no shell.
4. **One job per server, with limits.** The job lives on `WebRuntime`. One
   install runs at a time. It stops after 600 s. The process gets the server
   environment without any `*_API_KEY` variable. The last 40 output lines are
   kept after redaction. Both routes need the browser session with the
   `manage` scope, the same trust level as restart and Settings writes.
5. **Restart to use.** After success the entry reports `restart-needed` until
   the process ends. The page offers the existing restart action.
6. **A lasting copy command.** For a `uv tool` install the page shows
   `uv tool install --reinstall "omrs[<receipt extras>,<extra>] @ <source>"`,
   with the home folder written as `~`. A later manual reinstall with this
   command keeps the extra.
7. **Check the packages after the install.** After exit code 0 the job runs
   `uv pip check --python <sys.executable>` with the same limits. A clash
   fails the install with `check-failed` and no restart is offered. The live
   check showed why: installing `anthropic` moved `python-dateutil` from 3.0.0
   to 2.9.0.post0, because `botocore` (through `anthropic[bedrock]`) needs
   `python-dateutil<3`.
8. **Refuse an entry with `unknown` status.** When a probe fails, the server
   does not know what is installed, so the entry reports `status-unknown` and
   shows the copy command only.
9. **Warn on the card before a known version change.** A catalogue entry can
   carry an `install_caution` line. The page shows it in a red callout while
   the entry is not installed. Anthropic carries the `python-dateutil` line.
   A guard test keeps the extra requirement lines simple (`extra ==` joined
   with `and` only, never naming `omrs`).

## Consequences

### Positive

- The user adds a provider or reader from the app in one action, then restarts.
- The live app never gets code from the working checkout through this action.
- The copy command is now right for each install type.

### Negative

- A later `uv tool install --reinstall` without the extra drops the packages
  the button added. The lasting command on the entry prevents this, but only
  if the user uses it.
- The server can now start a process that reaches the package index. A stolen
  browser session could install a listed extra. It cannot install anything
  else.
- A new requirement can change an installed package version. The check in
  decision 7 catches a change that breaks another package. Recovery is the
  lasting reinstall command, which rebuilds the environment in one resolve.
- `uv pip check` also reports a clash that existed before the install, so
  such an install shows `check-failed` although it did not cause the clash.
- The Anthropic caution is fixed text. It goes stale if `botocore` accepts
  `python-dateutil` 3.

### Neutral

- No new dependency. The job uses `asyncio.create_subprocess_exec`.
- Uninstall is out of scope.
- The `workspace-integrations` rule that the page never installs is replaced
  by the guarded install action.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| `uv tool install --reinstall` with the new extra | It rebuilds OMRS from the receipt's source folder, which can hold uncommitted code and an old web build. Safe only when OMRS installs from a released package. Revisit if OMRS ships to PyPI. |
| Keep copy commands only | The user asked for an Install button. The old command was also wrong for the usual install. |
| Install any extra the package declares, including `web` | `web` is present when the page runs. (`torch` was in this row until 2026-10-24; it is now allowed with a size warning.) |
| Forbid downgrades with a constraint file | The Anthropic install needs one and is safe. Every such install would fail. |
| Import the new modules without a restart | A running process cannot load new modules safely in every case. The restart action already exists. |

## References

- `src/omrs/transports/api/integrations_catalogue.py`: install type, copy commands and `installable`
- `src/omrs/transports/api/routes/integrations.py`: `POST /v1/integrations/{extra}/install`, `GET /v1/integrations/install`
- `web/src/integrations/IntegrationCard.tsx`: Install button, confirm dialog, progress and output
- `openspec/changes/install-integrations-from-the-app/design.md`
