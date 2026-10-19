## ADDED Requirements

### Requirement: A login-item server hands over a renewed private sign-in link

When started with `--login-item`, the server SHALL write its one-time sign-in link to `<workspace>/launch-link`, as one line, in a file that only the current user can read (mode 0600), and SHALL NOT print the link to standard output, standard error or any log. After the link is used, or after the failed-attempt limit disables it, the server SHALL create a new link with a new secret and replace the file's content atomically. Each link SHALL work once. The server SHALL remove the file during its shutdown, before the process ends, also when a stop signal ends the process. A login-item server SHALL NOT write access-log lines. Browser sessions SHALL stay in server memory and SHALL end when the server stops.

#### Scenario: Link file is private

- **WHEN** a login-item server starts
- **THEN** `<workspace>/launch-link` MUST exist with mode 0600 and MUST hold a link for the bound port
- **AND** the link MUST NOT appear in standard output, standard error or the log buffer

#### Scenario: Link renews after sign-in

- **WHEN** a browser signs in with the link in the file
- **THEN** the file MUST then hold a different link
- **AND** the first link MUST be refused if used again

#### Scenario: Link renews after the failure limit

- **WHEN** 20 wrong secrets have been posted
- **THEN** the old secret MUST be refused
- **AND** the file MUST hold a new link that signs in

#### Scenario: A failed renewal is retried

- **WHEN** the server cannot write the renewed link, and a later sign-in attempt arrives
- **THEN** the server MUST write the current link to the file again, and the earlier sign-in MUST NOT fail

#### Scenario: Clean shutdown removes the file

- **WHEN** the server receives SIGTERM
- **THEN** `<workspace>/launch-link` MUST NOT exist once the process has ended

#### Scenario: Foreground launch is unchanged

- **WHEN** the user runs `omrg web` without `--login-item`
- **THEN** the server MUST print the one-time link to the terminal, MUST write no `launch-link` file, and MUST accept one sign-in per launch as before
