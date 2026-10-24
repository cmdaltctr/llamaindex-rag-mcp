# Proposal

## Why

The live check of `install-integrations-from-the-app` showed that installing Anthropic moved `python-dateutil` from 3.0.0 down to 2.9.0.post0. The reason: `llama-index-llms-anthropic` needs `anthropic[bedrock]`, which needs `botocore`, which needs `python-dateutil<3`. The install reported success. A later extra could break an installed package in the same way, and the user would see it only after the restart.

Two edge cases from the review also stay open:

- An entry whose probe failed (`unknown`) can still be installed, although the server does not know what is there.
- The requirement reader skips a metadata line that joins the extra with `or`. Such a line would make the install leave a package out and still report success. None exists today.

## What Changes

- After `uv pip install` ends with exit code 0, the install job runs `uv pip check --python <own Python>`. A non-zero result makes the install `failed` with the new reason `check-failed`. The entry stays `not-installed`, and the page tells the user to run the lasting command instead of restarting.
- `install_reason` gets the value `status-unknown`. An entry with `unknown` availability is not installable. The page shows its copy command only.
- A catalogue entry can carry an `install_caution` line. The page shows it as a red callout on the card while the entry is not installed. The Anthropic entry gets one about the `python-dateutil` downgrade.
- A guard test reads the real OMRS metadata. It fails when a requirement line for an allowed extra uses `or`, or names `omrs` itself.
- `docs/adr/ADR_README.md` notes that ADR-090 and ADR-091 are numbers reserved by the v4 proposals `authority-aware-retrieval` and `mantiq-reasoning-gates`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `integration-install`: the post-install check, the `status-unknown` reason and the metadata guard.
- `workspace-integrations`: the caution callout on a card.

## Impact

- `transports/api/install_job.py`, `install_environment.py`, `integrations_catalogue.py`, `routes/integrations.py`, `openapi.yaml`.
- Web: `api/integrations.ts`, `IntegrationCard.tsx`, `InstallControls.tsx`, `InstallRefusal.tsx`.
- No new dependency. `uv pip check` ships with `uv`.
- Records: ADR-094 (still Proposed) gets the check step and the caution line.
- Docs: `docs/guides/web-workspace.md` route table.
