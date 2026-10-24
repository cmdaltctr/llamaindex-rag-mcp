# Design

## Context

`InstallJob` runs `uv pip install --python <sys.executable> <requirements>` (ADR-094). `uv pip install` resolves the new requirements against the installed packages and may change their versions. It does not promise that every installed package still fits. The live check moved `python-dateutil` from 3.0.0 to 2.9.0.post0. That move was harmless, because pandas needs `>=2.8.2` and the project lock file holds 2.9.0.post0.

## Decisions

### D1. Check the environment after the install

After exit code 0, the job runs `uv pip check --python <own Python>` as a second argument list, with the same environment, output buffer, redaction and 600 s limit as the install. Exit code 0 means `succeeded`. Any other code means `failed` with the reason `check-failed` and that exit code. The extra does not go into `restart_needed`.

The packages stay installed after `check-failed`. The fix is the lasting command on the entry. It rebuilds the whole environment in one resolve, so it either gives a consistent set or fails before it changes anything. A restart with a broken set could stop the app from starting, so the page says to use the command before a restart.

Alternative rejected: pass a constraint file that forbids downgrades. Every install that needs a lower version would then fail, including the Anthropic one, which is safe.

### D2. `status-unknown` refuses the install

`install_reason` returns `status-unknown` when the availability is `unknown`. The check comes after `not-installable-here` and before `already-installed`. The page already hides the Install button when `installable` is false, so the card shows the copy command only. The 409 reply and the page get one plain line for the reason.

### D3. An install caution is catalogue data

`Integration` gets an optional `caution` text. `describe_entry` returns it as `install_caution` (string or null). The text is fixed in code and is not tied to the installed versions. The card shows it in a red callout while the entry is `not-installed` or `unknown`, and hides it once the entry is `available` or waits for a restart.

Anthropic text: installing it also installs Amazon's `botocore`, which needs `python-dateutil` below version 3, so uv can move `python-dateutil` back to 2.9. The app checks all packages after the install.

### D4. Guard the metadata, keep the parser

`_without_extra` stays as it is. A test reads `Requires-Dist` from the installed OMRS metadata. For every allowed extra (the declared extras without `web` and `torch`), it fails when a line for that extra has `or` in its marker or names the `omrs` distribution. A second test feeds the same check bad lines, so the guard is known to fail. `packaging` is not added as a dependency.

## Risks

- The caution text can go stale if `botocore` allows `python-dateutil` 3. The check in D1 still protects the user.
- `uv pip check` reports conflicts that existed before the install too. The install then shows `check-failed` although it did not cause the conflict. The output lines name the packages, and the lasting command fixes both cases.
