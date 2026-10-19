## ADDED Requirements

### Requirement: The navigation foot holds four quick controls

The side navigation SHALL end with a foot of four icon controls in this order: a theme button, a Settings link, a power control and a GitHub link. The foot SHALL have no language control, because the interface is English only. Every control SHALL have an accessible name. The existing top bar theme controls SHALL stay unchanged.

The theme button SHALL show the theme in effect and SHALL switch between Light and Dark in one click. Its accessible name SHALL state the theme it switches to. It SHALL write the stored theme preference, and the Settings theme select SHALL show the same value.

The Settings link SHALL open the Settings view.

The power control SHALL show a light that follows `GET /v1/health`: green while the app answers and grey when it does not. Pressing it SHALL open a panel. The panel SHALL say "Running" with the running version while the app answers, and "Not answering" when it does not. The panel SHALL show the commands `omrg web restart` and `omrg web open`. The panel SHALL offer no Restart button and no Stop button. The state SHALL NOT rely on colour alone.

The GitHub link SHALL point to https://github.com/cmdaltctr/llamaindex-rag-mcp, SHALL open in a new tab and SHALL carry a `rel` value with `noopener` and `noreferrer`.

#### Scenario: Four controls in order

- **WHEN** the navigation renders
- **THEN** the foot MUST hold exactly four controls, in this order: theme button, Settings link, power control, GitHub link
- **AND** the foot MUST hold no language control

#### Scenario: Theme in one click, light to dark

- **WHEN** the theme in effect is light and the user presses the theme button
- **THEN** the app MUST render the dark theme, the stored preference MUST be `dark`, and the Settings theme select MUST read Dark
- **AND** the button's accessible name MUST state that it switches to the light theme

#### Scenario: Theme in one click, dark to light

- **WHEN** the theme in effect is dark and the user presses the theme button
- **THEN** the app MUST render the light theme, the stored preference MUST be `light`, and the Settings theme select MUST read Light
- **AND** the button's accessible name MUST state that it switches to the dark theme

#### Scenario: Settings link

- **WHEN** the user presses the Settings control
- **THEN** the address bar MUST read `#/settings`

#### Scenario: Power light follows health

- **WHEN** `GET /v1/health` answers
- **THEN** the power icon MUST be green and its panel MUST say "Running" with the running version
- **AND** when `GET /v1/health` does not answer, the power icon MUST be grey and its panel MUST say "Not answering"
- **AND** the panel text MUST state the state, so the state does not rely on colour alone

#### Scenario: Power panel names the commands

- **WHEN** the user opens the power panel
- **THEN** the panel MUST show the commands `omrg web restart` and `omrg web open`
- **AND** the panel MUST offer no Restart button and no Stop button

#### Scenario: GitHub link

- **WHEN** the navigation renders
- **THEN** the GitHub link MUST point to https://github.com/cmdaltctr/llamaindex-rag-mcp
- **AND** the link MUST open in a new tab and MUST carry a `rel` value with `noopener` and `noreferrer`

#### Scenario: Collapsed navigation

- **WHEN** the navigation shows as its icon column
- **THEN** the four controls MUST render as icons in one column
- **AND** below the `md` breakpoint the four controls MUST stay reachable
