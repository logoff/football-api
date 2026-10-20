# Spec Delta

## MODIFIED Requirements

### Requirement: Event player resolution

Each lineup entry, substitution player and card SHALL reference a squad player of that team-season when the source name resolves to exactly one, compared case- and accent-insensitively and, when that finds no one, also ignoring spaces (`Park Jisung` and `PARK Ji Sung`). Otherwise it SHALL keep the source name, title-cased like goal scorers, with a null player reference. The name SHALL be stored in both cases.

#### Scenario: Resolved against the squad

- **GIVEN** World Cup 2022, whose squads are ingested, and a lineup name that matches one squad member
- **WHEN** the match is ingested
- **THEN** the lineup entry references that player and has that `player_name`

#### Scenario: Season without squads

- **GIVEN** a 2025-26 Premier League match
- **WHEN** it is ingested
- **THEN** every lineup entry, substitution and card has a null player reference and a `player_name`

#### Scenario: Names split differently

- **GIVEN** World Cup 2010, whose squad lists `PARK Ji Sung` for South Korea, and a lineup that writes `Park Jisung`
- **WHEN** the match is ingested
- **THEN** the lineup entry references that player
