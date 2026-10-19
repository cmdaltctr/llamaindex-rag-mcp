# Spec Delta

## ADDED Requirements

### Requirement: Extra browser origins are approved only at launch
The operator SHALL be able to approve extra loopback browser origins when the server starts, one exact origin per value. An approved origin SHALL pass every origin check for that run only. The server SHALL accept no other extra origin and SHALL change no other request check.

#### Scenario: An approved origin signs in
- **WHEN** the server starts with an approved loopback origin and a page from that origin posts the one-time bootstrap secret
- **THEN** the server SHALL issue the session cookie, as it does for the server's own address

#### Scenario: An approved origin submits a state-changing request
- **WHEN** a signed-in page from an approved origin sends a state-changing request
- **THEN** the server SHALL admit the request, subject to the same session and scope rules as any other request

#### Scenario: No origin is approved
- **WHEN** the server starts without an approved origin
- **THEN** the server SHALL accept only its own loopback origins, with the same results as before this requirement

#### Scenario: An unapproved origin is rejected
- **WHEN** a page from any origin that is neither the server's own nor approved sends an API request
- **THEN** the server SHALL return 403 before core work is admitted

#### Scenario: A non-loopback origin is requested
- **WHEN** the operator approves an origin whose host is not a loopback name or address
- **THEN** the server SHALL refuse to start, SHALL exit with code 2 and SHALL state the loopback rule

#### Scenario: A malformed or wildcard origin is requested
- **WHEN** the operator approves a value that has a wildcard, a path, a query, a fragment, user information or a scheme other than `http` or `https`
- **THEN** the server SHALL refuse to start, SHALL exit with code 2 and SHALL name the value

#### Scenario: The Host and fetch-metadata checks still apply
- **WHEN** a request from an approved origin carries a foreign `Host` header or cross-site fetch metadata
- **THEN** the server SHALL reject it as it does for any other request

#### Scenario: The operator sees what is approved
- **WHEN** the server starts with approved origins
- **THEN** the server SHALL print each approved origin before it prints the launch link
