# Spec Delta

## ADDED Requirements

### Requirement: The page carries a persistent workspace sign-in secret

The server SHALL keep one sign-in secret in `<workspace>/.auth-token`. It SHALL create the file on its first start with a new random secret of at least 256 bits, in a file that only the current user can read (mode 0600), and SHALL create a missing workspace folder with mode 0700. Every later start with the same workspace SHALL read and use the same secret. A file with a mode looser than 0600 SHALL get a warning, and the server SHALL set the mode to 0600 when the current user owns the file. A file that holds no valid secret SHALL get a warning and SHALL be replaced. Neither case SHALL stop the server.

The server SHALL put the secret into the application page that it serves only when the `Host` header is one of its own loopback names with the bound port, any `Origin` header is the server's own origin or an origin approved with `--allow-origin`, and the fetch metadata shows a same-origin request or a navigation. Any other request SHALL get the page without the secret, or the `Host` refusal. A page that carries the secret SHALL be sent with `Cache-Control: no-store`.

`POST /v1/session` SHALL accept the secret in its `bootstrap` field, with the same `Origin` check, and SHALL set the same session cookie as for the one-time link. A sign-in with the secret SHALL NOT use, renew or disable the one-time link. Wrong values SHALL count toward the failure limit of the one-time link and SHALL NOT disable the secret.

The page SHALL sign in with the secret on load when the address has no one-time link, or when that link is refused. When an API request gets 401, the page SHALL sign in with the secret once and SHALL send the request once more. Requests that get 401 at the same time SHALL share one sign-in.

The secret SHALL NOT appear in a log line, an API response body, an error message, a URL or the terminal.

#### Scenario: First start creates a private secret

- **WHEN** the server starts with a workspace that has no `.auth-token`
- **THEN** `<workspace>/.auth-token` MUST exist with mode 0600
- **AND** a workspace folder that the server created MUST have mode 0700

#### Scenario: Later starts reuse the secret

- **WHEN** two servers start one after the other with the same workspace
- **THEN** both MUST put the same secret into their page

#### Scenario: A loose mode is tightened

- **WHEN** `.auth-token` has mode 0644 at start
- **THEN** the server MUST log a warning that names mode 0600 and MUST NOT log the secret
- **AND** the file MUST then have mode 0600 and MUST hold the same secret

#### Scenario: An open tab survives a restart

- **WHEN** a page signed in, the server restarts with the same workspace, and the page sends its next API request with the old cookie
- **THEN** the request MUST get 401, the page MUST sign in with the secret it holds, and the repeated request MUST succeed
- **AND** no one-time link MUST be needed

#### Scenario: A foreign Host never gets the secret

- **WHEN** a request for the page carries a `Host` that is not one of the server's own loopback names with its port
- **THEN** the server MUST answer 400 and the body MUST NOT hold the secret

#### Scenario: A foreign reader gets the page without the secret

- **WHEN** a request for the page carries a foreign `Origin`, or cross-site or same-site fetch metadata that is not a navigation
- **THEN** the page MUST NOT hold the secret

#### Scenario: An approved preview origin signs in

- **WHEN** the server starts with an approved origin and that origin loads the page and posts the secret
- **THEN** the page MUST hold the secret and the server MUST set the session cookie

#### Scenario: Sign-in with the secret leaves the link unused

- **WHEN** a login-item server signs a page in with the secret
- **THEN** `<workspace>/launch-link` MUST hold the same link as before, and that link MUST still sign in

#### Scenario: Wrong guesses do not lock out the page

- **WHEN** more than 20 wrong values have been posted
- **THEN** the one-time link MUST be refused and the secret MUST still sign in

#### Scenario: One retry only

- **WHEN** an API request gets 401 and the sign-in with the secret is refused
- **THEN** the page MUST report the 401 and MUST NOT send the request again

## MODIFIED Requirements

### Requirement: A login-item server hands over a renewed private sign-in link

When started with `--login-item`, the server SHALL write its one-time sign-in link to `<workspace>/launch-link`, as one line, in a file that only the current user can read (mode 0600), and SHALL NOT print the link to standard output, standard error or any log. After the link is used, or after the failed-attempt limit disables it, the server SHALL create a new link with a new secret and replace the file's content atomically. Each link SHALL work once. The server SHALL remove the file during its shutdown, before the process ends, also when a stop signal ends the process. A login-item server SHALL NOT write access-log lines. Browser sessions SHALL stay in server memory and SHALL end when the server stops. A page that the server served SHALL then sign in again with the workspace sign-in secret, as "The page carries a persistent workspace sign-in secret" states.

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
- **THEN** the server MUST print the one-time link to the terminal, MUST write no `launch-link` file, and MUST accept that link once, as before
