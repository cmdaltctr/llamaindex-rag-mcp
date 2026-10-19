# marimo notebook plugin for OMRG

This folder holds an optional plugin manifest for the marimo notebook editor.
The folder is not part of the OMRG wheel. OMRG does not depend on marimo.

## Status

- The tested range is `>=0.25.1,<0.26.0`. Task 8.4 qualified marimo 0.25.1, installed with `uv tool install marimo` (uv 0.12.18).
  The launch flags, the startup settings, the login, the connection file and the update procedure were checked with that version.
- marimo 0.25.0 is outside the range. Its probe passes, but the startup behaviour was not checked on it.
- The editor that OMRG starts gets only allow-listed environment variables, plus `OMRG_CONNECTION_FILE`.
  That file tells the starter notebook how to reach OMRG. The notebook kernel receives it.
  See [What task 8.4 confirmed](../../docs/guides/notebooks.md#what-task-84-confirmed).

## Trust and the full procedure

Read [Notebooks](../../docs/guides/notebooks.md) before you register this plugin. It explains the trust model,
the experiment workspace, the starter notebook, and the stop, update, recheck and start procedure.

- Notebook Python runs with your filesystem and network permissions. A tool environment is not an operating-system sandbox.
- Registration needs your explicit approval. Each launch needs your consent.
- A notebook credential is bound to one experiment. It cannot read or change the live library.
- The editor opens in a separate browser tab. The OMRG workspace never embeds the editor in its own page.
- The OMRG workspace works without this plugin.

## Starter notebook

`starter_notebook.py` runs graphs through the protected OMRG graph API.

1. Copy it into an approved experiment workspace.
2. When the OMRG workspace opens the editor, OMRG writes a private connection file (mode 600) into the private launch directory.
   It sets `OMRG_CONNECTION_FILE` to that file. The file names a separate token file (mode 600) that holds a new credential bound to the experiment.
   OMRG revokes the credential and deletes both files when the editor stops.
   For an editor that you start yourself, set `OMRG_API_URL`, `OMRG_TOKEN_FILE` (a file with mode 600) and `OMRG_EXPERIMENT_CONTEXT` instead.
3. Open it. Nothing runs until you press **Run graph**.

Each run writes a checkpoint below `output/runs/`. See [Notebooks](../../docs/guides/notebooks.md#use-the-starter-notebook).

## What OMRG does and does not do

OMRG reads this manifest, probes the executable that you register, and starts and stops the editor.

OMRG never installs, upgrades or replaces marimo. It never runs `uvx`, `uv tool install` or `pip`.
You install and update marimo outside OMRG.

## Install marimo outside OMRG

1. Install marimo in its own tool environment:

   ```bash
   uv tool install marimo
   ```

2. Find the path of the executable:

   ```bash
   command -v marimo
   ```

3. Keep this path. You give it to OMRG when you register the plugin.

## Register the plugin

Registration is a trust decision. A notebook runs Python with your user permissions.
It can read and write your files and use your network. A separate tool environment does not contain it.

1. Read `manifest.json`.
2. Register the manifest and the absolute executable path. Give your explicit approval.
3. Run a compatibility check (recheck).

OMRG stores the SHA-256 of the manifest and the identity of the executable (path, size, modification time, SHA-256).
If you edit the manifest, OMRG disables the plugin until you register it again.
If the executable changes, OMRG disables the plugin until a recheck passes.

## What the compatibility check runs

The check runs only these commands. It runs them without a shell.

```text
<executable> --version
<executable> edit --help
```

The plugin stays disabled if:

- the version is outside the tested range, or
- the help output does not list a required launch option.

The message names the version or the missing capability.

## What a launch does

A launch needs your consent each time. Before the launch, OMRG runs the compatibility check again.

The launch command is:

```text
marimo edit <notebook> --headless --host 127.0.0.1 --port <port>
  --token-password-file <launch-dir>/access-token --skip-update-check --no-sandbox
```

- `--host 127.0.0.1` binds the editor to loopback only.
- `--token-password-file` gives a new token for each launch. The token is in a file with mode `0o600`.
  The token is not in the command line, the environment or a log.
- `--headless` stops marimo from opening a browser. The workspace opens the editor in a separate browser tab. It never embeds the editor.
- `--skip-update-check` stops the check for a new marimo version.
- `--no-sandbox` stops marimo from creating a sandbox environment that installs dependencies.

OMRG also writes `.marimo.toml` into the private launch directory and starts marimo in that directory:

```toml
[runtime]
auto_instantiate = false
on_cell_change = "lazy"
```

`auto_instantiate = false` stops the notebook from running its cells at startup.
`on_cell_change = "lazy"` marks dependent cells as stale. It does not run them.

The launch directory has mode `0o700`. OMRG removes it when the editor stops. It also holds the connection file and the API token file when OMRG opens the starter notebook.

### Limits to know

- marimo uses the first `.marimo.toml` that it finds: the current directory, then parent directories, then `~/.marimo.toml`.
  The launch directory file wins over `~/.marimo.toml` (confirmed with marimo 0.25.1).
- A `pyproject.toml` with a `[tool.marimo.runtime]` table overrides the launch directory file.
  marimo looks for it in the notebook directory and in each parent directory.
  It can turn startup execution back on. Do not keep an experiment workspace below a project whose `pyproject.toml` sets `auto_instantiate`.
- A notebook header (PEP 723 script metadata) cannot turn startup execution on. marimo 0.25.1 ignores
  `runtime.auto_instantiate` there and logs a warning. A header can still change `runtime.on_cell_change`. Check notebooks before you trust them.
- marimo installs a package only after your action in the editor (the package panel or the missing-package prompt). It is not automatic.
- marimo writes a session cache below `__marimo__/session/` beside the notebook. It holds cell outputs, not the tokens.
- The editor prints its login address, with the token, to its own output. The OMRG launcher keeps that output in memory only and replaces the token with `[redacted]`.
- The editor gets only a small set of environment variables (for example `PATH`, `HOME`, `LANG`).
  OMRG provider keys are not passed to it.

## Ports

OMRG tries its permitted ports in order. If another program uses a port, OMRG uses the next permitted port.
If no permitted port is free, the launch fails with a message.
OMRG never stops or adopts a program that it did not start.
marimo 0.25.1 does not pick another port by itself. It exits with "address already in use".

## Stop

Use Stop in the workspace, or stop the OMRG web application.

1. OMRG sends SIGTERM to the editor process group that it started.
2. OMRG waits for a limited time.
3. If the group is still running, OMRG sends SIGKILL.

Your notebook files stay as they are. OMRG removes only the private launch directory.

## Update marimo

1. Stop the editor in the workspace.
2. Update marimo outside OMRG:

   ```bash
   uv tool upgrade marimo
   ```

   If you installed an exact version (for example `uv tool install marimo==0.25.1`), `uv tool upgrade` does not change it.
   Use `uv tool install marimo@latest` instead.

3. Run a recheck in the workspace. OMRG shows `unchecked` until you do, because the executable changed.
4. If the recheck passes, start the editor again.
5. If the version is outside the tested range, keep the earlier version, or update this manifest after you qualify the new version.
   Then register the edited manifest again.

## Remove the plugin

1. Stop the editor.
2. Remove or move the registered manifest file. A registration without its approved manifest stays disabled.
3. Uninstall marimo outside OMRG if you no longer need it.
