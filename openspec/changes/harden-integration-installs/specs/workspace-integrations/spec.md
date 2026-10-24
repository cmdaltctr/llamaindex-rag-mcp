## ADDED Requirements

### Requirement: A card warns before an install that changes other packages

An entry MAY carry an `install_caution` line. While the entry is `not-installed` or `unknown`, the card SHALL show that line in a red callout above the Install button and the copy command. The card SHALL NOT show the callout once the entry is `available` or waits for a restart.

#### Scenario: Anthropic caution

- **WHEN** the Anthropic entry is not installed and carries a caution about `python-dateutil`
- **THEN** the card MUST show the caution in a red callout before the Install button

#### Scenario: Installed entry

- **WHEN** the Anthropic entry is `available`
- **THEN** the card MUST NOT show the caution
