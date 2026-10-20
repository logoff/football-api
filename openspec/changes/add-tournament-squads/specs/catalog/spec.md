# Spec Delta

## MODIFIED Requirements

### Requirement: Player catalog

The system SHALL maintain a catalog of players, created **only** from Open Football squad files.

A player has:

- a UUID
- a `display_name`, exactly as the source writes it
- optional `full_name`, `given_name`, `family_name` — filled only where the source marks the surname (capitals) or from Wikidata; never by guessing a split
- an optional birth year, date of birth, nationality, and primary position

External identifiers for a player are stored exclusively in `external_ref`.

Player coverage is:

- **complete** for every FIFA World Cup (1930–2026) and FIFA Club World Cup (2000–2025), and for Euro 2021 and 2024 and Copa América 2021 and 2024: Open Football publishes full squad lists for them.
- **none** for the other seasons, including every domestic league and cup: Open Football publishes no squads for them.

#### Scenario: Listing players for a team-season

- **WHEN** a client GETs `/v1/players?team_id={spain}&season_id={euro-2024}`
- **THEN** the API responds 200 with players who appeared in that team-season

#### Scenario: Names are not split by guessing

- **GIVEN** a squad line `Frenkie de Jong, MF`
- **WHEN** the player is ingested
- **THEN** `display_name` is `Frenkie de Jong`
- **AND** `given_name` and `family_name` are null

#### Scenario: Capitalised surname marks the split

- **GIVEN** a Club World Cup squad line `Lionel MESSI`
- **WHEN** the player is ingested
- **THEN** `display_name` is `Lionel Messi`, `given_name` is `Lionel`, `family_name` is `Messi`
- **AND** no stored name field contains the source capitalisation

#### Scenario: Fully capitalised name is a known-as name

- **GIVEN** a Club World Cup squad line `MARQUINHOS (BRA)`
- **WHEN** the player is ingested
- **THEN** `display_name` is `Marquinhos`
- **AND** `given_name` and `family_name` are null

#### Scenario: Documented missing coverage

- **WHEN** a client GETs `/v1/players?team_id={manchester-united}&season_id={premier-league-2024-25}`
- **THEN** the API responds 200 with an empty list
- **AND** the response includes a `coverage` field indicating `players: "none"`

#### Scenario: Squad list without shirt numbers

- **GIVEN** the 1930 World Cup squad line `Jimmy DOUGLAS, GK, b. 1898/01/12`, with no shirt number
- **WHEN** the squads are ingested
- **THEN** a player `Jimmy Douglas` exists for the United States in 1930, with goalkeeper as position and no shirt number
