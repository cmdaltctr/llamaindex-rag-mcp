# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: The login item reads settings from ~/.omrg/.env`
- TO: `### Requirement: The login item reads omrg.jsonc and an optional ~/.omrg/.env`

## MODIFIED Requirements

### Requirement: The login item reads omrg.jsonc and an optional ~/.omrg/.env

The agent SHALL run with the working folder `~/.omrg`. The app SHALL read `omrg.jsonc` from the user config folder, and SHALL also read `~/.omrg/.env` when that file exists. `install` SHALL create `~/.omrg` when it is missing. The plan SHALL name the `omrg.jsonc` path as the settings file and SHALL say that `~/.omrg/.env` is optional and overrides it. When the folder where `install` runs has a `.env`, the plan SHALL tell the user that the login item does not read it, and SHALL suggest `omrg config init`. The command SHALL NOT read, copy or move any `.env` file.

#### Scenario: Settings file named in the plan

- **WHEN** the user runs `omrg web install --dry-run` in a checkout that has a `.env`
- **THEN** the plan MUST name `~/.config/omrg/omrg.jsonc` as the settings file, MUST say that the checkout `.env` is not read, and MUST suggest `omrg config init`
- **AND** no `.env` file MUST be created or changed

#### Scenario: Settings reach the app

- **WHEN** `omrg.jsonc` sets `embed_model`, `~/.omrg/.env` does not exist, and the login item starts
- **THEN** the running app MUST use that embedding model

#### Scenario: Optional .env overrides

- **WHEN** `omrg.jsonc` sets `embed_model` and `~/.omrg/.env` sets `EMBED_MODEL` to another model
- **THEN** the running app MUST use the `.env` model, and Settings MUST report the source `dotenv`
