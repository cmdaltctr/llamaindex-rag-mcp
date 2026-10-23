## ADDED Requirements

### Requirement: A provider that is not installed links to its integration

A provider card under Settings > Providers whose package is not installed SHALL show "Not installed" and a link to the matching entry on the Integrations page. It SHALL NOT print an install command on the card. The Chat and judge forms SHALL use the same link in their fix line.

#### Scenario: Anthropic not installed

- **WHEN** the Anthropic package is not installed
- **THEN** the Anthropic card MUST show "Not installed" with a link to the `anthropic` entry on the Integrations page

#### Scenario: Provider installed

- **WHEN** the provider package is installed
- **THEN** the card MUST NOT show the link
