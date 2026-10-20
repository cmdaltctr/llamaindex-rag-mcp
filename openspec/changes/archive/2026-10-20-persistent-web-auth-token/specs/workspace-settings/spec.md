# Spec Delta

## MODIFIED Requirements

### Requirement: A restart-only change offers a restart

After the user saves a setting that applies only after a restart, the page SHALL open a dialog that names the setting and offers "Restart now" and "Later". "Restart now" SHALL use the power menu restart. When the app runs in a terminal, the dialog SHALL show the command to restart instead of "Restart now". "Later" SHALL leave the row marked "Restart to apply".

#### Scenario: Port saved

- **WHEN** the app runs as the login item and the user saves port 9100
- **THEN** a dialog MUST say that port 9100 applies after a restart and MUST offer "Restart now" and "Later"

#### Scenario: Restart now

- **WHEN** the user presses "Restart now"
- **THEN** the page MUST send the power menu restart request and MUST say that the page signs in again by itself, and MUST name `omrg web open` for a restart that moves the app to a new port

#### Scenario: Foreground server

- **WHEN** the app runs in a terminal and the user saves port 9100
- **THEN** the dialog MUST show the restart command and MUST NOT offer "Restart now"

