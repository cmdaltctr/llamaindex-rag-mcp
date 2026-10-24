# Design

## Context

- The live app is a `uv tool` install. Its receipt (`<tool env>/uv-receipt.toml`) records the requirement `omrs[web,hybrid]` built from a project folder. The login item runs `omrs web` from that environment.
- The installed package metadata (`importlib.metadata.distribution("omrs")`) lists every extra (`Provides-Extra`) and its requirements (for example `llama-index-llms-anthropic>=0.11.0; extra == 'anthropic'`). The server can work out what to install without the source folder.
- `GET /v1/integrations` (`integrations_catalogue.py`) already reports availability from the runtime probes, and always prints `uv sync --extra <x>`.
- `POST /v1/server/power` already restarts the login item, needs the `manage` session, and takes a closed set of actions. `RestartDialog.tsx` already drives it.

## Goals / Non-Goals

**Goals:**

- One-click install of an optional extra into the running server's environment, followed by the existing restart.
- A copy command that is correct for each install type.

**Non-Goals:**

- Rebuilding or upgrading OMRS from the app.
- Uninstalling extras.
- Installing `torch` or `web`.
- Installing when the server runs from a checkout, a pip install or a container. These show the copy command.

## Decisions

### D1. `uv pip install` into the server's own Python, not `uv tool install --reinstall`

The job runs `uv pip install --python <sys.executable> <requirements>`, where the requirements are the extra's lines from the installed metadata with the `extra ==` marker removed.

- Why: a reinstall rebuilds OMRS from the receipt's source folder. That folder is a working checkout (the live one is the v3 folder). It can hold uncommitted code and an old web build, because the built pages are not committed. A rebuild could ship that state. `uv pip install` adds only the missing libraries and leaves OMRS as it is.
- Trade-off: a later manual `uv tool install --reinstall` without the extra drops the libraries. The entry shows the lasting command (D4) to prevent this.
- Rejected: `uv tool install --reinstall` with the new extra. It is safe only when the source is a released package, not a folder. It can be revisited if OMRS ships to PyPI.

### D2. Install type detection

- `uv-tool`: `Path(sys.prefix, "uv-receipt.toml")` exists. The receipt is parsed with `tomllib` to read the extras and the source for the copy command.
- `checkout`: the `omrs` package file sits under a folder that holds `pyproject.toml` and `uv.lock`.
- `other`: everything else.

`uv` is found with `shutil.which("uv")`, then `~/.local/bin/uv`, then `~/.cargo/bin/uv`. The login item has a short `PATH`, so the fixed fallbacks are needed.

### D3. A single install job owned by the web runtime

`InstallJob` lives on `WebRuntime`, so there is one per server. It holds the state, the extra, the start time and a ring buffer of the last 40 output lines. It starts the process with `asyncio.create_subprocess_exec` (argument list, no shell, `stdin` closed), reads output line by line, and stops the process after 600 s. The output goes through the existing log redaction before it is kept. The environment passed to the process is the server environment without `*_API_KEY` variables.

After success, the job records the extra in a `restart_needed` set. The catalogue reports `restart-needed` for that entry until the process ends, because the running process cannot import new modules safely in all cases.

### D4. Copy commands

| Install type | Command |
|---|---|
| `uv-tool` | `uv tool install --reinstall "omrs[<receipt extras>,<extra>] @ <receipt source>"` |
| `checkout` | `uv sync --extra <extra>` |
| `other` | `pip install "omrs[<extra>]"` |

The receipt source is shown with the home folder written as `~`.

### D5. Web

- `IntegrationCard` gets an Install button (shared `Button`, `sm`), a confirm dialog that reuses the dialog primitive, a progress line and an output block (`text-code`, max 40 lines, scrolls inside itself).
- The status query polls `GET /v1/integrations/install` every 1 s only while the state is `running`.
- On success, the card shows the Restart action, which opens the existing `RestartDialog`.
- `ProviderCard` replaces the printed command with a link to `#/integrations` that focuses the matching entry.

### D6. Records

An ADR records that the app may install allowed extras into its own environment, with D1 and D3 as the decision and the limits. Its number is the next free one when task 6.1 runs. `add-chat-reasoning-and-usage` takes ADR-093.

## Risks / Trade-offs

- [The install breaks the environment, for example a dependency downgrade] → `uv pip install` keeps installed packages unless the new requirement conflicts. The confirm dialog names the packages. Recovery is the lasting reinstall command, which rebuilds the environment.
- [Someone with a stolen browser session installs packages] → Only the `manage` session can, only listed extras, only from the package index `uv` already uses. This is the same trust level as the existing restart and Settings writes.
- [The process hangs on the network] → The 600 s timeout stops it and reports `timed-out`.
- [The extra's floors differ from the locked versions] → The resolver picks versions compatible with the installed set. `tests/test_dependency_floors.py` keeps floors close to the lock.

## Migration Plan

Additive. Servers that are not `uv tool` installs behave as before, with a corrected copy command. Rollback is a revert of the change.
