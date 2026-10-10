# Catalog Capability

## Purpose

Expose canonical entities — competitions, seasons, teams, players, venues — that all other capabilities reference. Entities are sourced from Open Football data and Wikidata (for identifiers only), normalized into the project's own UUID space. UUIDs are the only identifiers the API accepts or exposes: in paths and in filters.

## ADDED Requirements

### Requirement: Competition catalog

The system SHALL maintain a catalog of competitions, each identified by a UUID.

A competition has:

- a display name
- a country code (ISO 3166-1 alpha-2, or ISO 3166-2 `GB-ENG` / `GB-SCT` / `GB-WLS` / `GB-NIR` for the UK home nations) for domestic competitions, or `null` for international competitions
- a `team_kind`: `CLUB` (contested by clubs) or `NATIONAL` (contested by national teams)
- a `scope`: `DOMESTIC` (within a single country), `CONTINENTAL` (within one confederation — UEFA, CONMEBOL, etc.), or `INTERCONTINENTAL` (across confederations)

External identifiers for a competition (Wikidata QID, Open Football file path, etc.) MUST NOT live on the competition row; they are stored exclusively in `external_ref`.

For v0.1, in-scope competitions are:

| Name                       | team_kind | scope            |
| -------------------------- | --------- | ---------------- |
| Premier League             | CLUB      | DOMESTIC         |
| La Liga                    | CLUB      | DOMESTIC         |
| Bundesliga                 | CLUB      | DOMESTIC         |
| Serie A                    | CLUB      | DOMESTIC         |
| Ligue 1                    | CLUB      | DOMESTIC         |
| UEFA Champions League      | CLUB      | CONTINENTAL      |
| UEFA Europa League         | CLUB      | CONTINENTAL      |
| UEFA Conference League     | CLUB      | CONTINENTAL      |
| CONMEBOL Copa Libertadores | CLUB      | CONTINENTAL      |
| FIFA Club World Cup        | CLUB      | INTERCONTINENTAL |
| FIFA World Cup             | NATIONAL  | INTERCONTINENTAL |
| UEFA European Championship | NATIONAL  | CONTINENTAL      |
| CONMEBOL Copa América      | NATIONAL  | CONTINENTAL      |

#### Scenario: Listing competitions

- **WHEN** a client GETs `/v1/competitions`
- **THEN** the API responds 200 with all in-scope competitions, paginated

#### Scenario: Fetching a competition by ID

- **WHEN** a client GETs `/v1/competitions/{id}` for a known UUID
- **THEN** the API responds 200 with the competition's full record
- **AND** when the UUID is unknown the API responds 404 with the standard error envelope

#### Scenario: Non-UUID identifier is rejected

- **WHEN** a client GETs `/v1/competitions/premier-league` or `/v1/seasons?competition_id=premier-league`
- **THEN** the API responds 422 with the standard error envelope, because every identifier must be a UUID

### Requirement: Season catalog

The system SHALL track one or more seasons per competition. Each season has:

- a reference to its competition
- a label (e.g. `2024-25`, `2022`)
- a start and end date
- a status: `SCHEDULED`, `IN_PROGRESS`, `COMPLETED`

For v0.1, only the most recently completed season per competition is ingested.

#### Scenario: Listing seasons for a competition

- **WHEN** a client GETs `/v1/seasons?competition_id={uuid}`
- **THEN** the API responds 200 with all seasons of that competition

### Requirement: Team catalog

The system SHALL maintain a catalog of teams of two kinds: `CLUB` (e.g. Real Madrid) and `NATIONAL` (e.g. Spain).

A team has:

- a display name
- a primary country
- the kind (`CLUB` | `NATIONAL`)
- a many-to-many relationship with seasons (the seasons in which this team participated)

External identifiers for a team are stored exclusively in `external_ref`.

Team identity is defined by the curated seed file `seeds/teams.yaml`, which lists each team's name, kind, country, Wikidata QID, and every Open Football spelling of its name. An entry is matched to its existing row through those external identifiers, so editing a name never creates a second team. Sync SHALL NOT create a team that is not in this file.

#### Scenario: Fetching a team by ID

- **WHEN** a client GETs `/v1/teams/{id}`
- **THEN** the API responds 200 with the team's record
- **AND** when `?expand=seasons` is provided, the response includes the team's participating seasons

#### Scenario: Teams of a competition season

- **WHEN** a client GETs `/v1/teams?season_id={uuid}`
- **THEN** the API responds 200 with the teams that took part in that season

#### Scenario: Unknown team name in a source file

- **GIVEN** a source match line naming `Manchester Utd FC`, which is not listed under any team in `seeds/teams.yaml`
- **WHEN** sync runs
- **THEN** sync fails with an error naming the file, line number, and unresolved name
- **AND** no team row is created

### Requirement: Player catalog

The system SHALL maintain a catalog of players, created **only** from Open Football squad files.

A player has:

- a UUID
- a `display_name`, exactly as the source writes it
- optional `full_name`, `given_name`, `family_name` — filled only where the source marks the surname (capitals) or from Wikidata; never by guessing a split
- an optional birth year, date of birth, nationality, and primary position

External identifiers for a player are stored exclusively in `external_ref`.

For v0.1, player coverage is:

- **complete** for WC 2022, Euro 2024, Copa América 2024 and Club World Cup 2025 — Open Football publishes full squad lists.
- **none** for all other club competitions — Open Football publishes no squads for them.

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

### Requirement: Venue catalog

The system SHALL maintain a catalog of venues referenced by matches.

A venue has:

- a UUID
- a name
- a city and country

External identifiers for a venue are stored exclusively in `external_ref`.

Venue records are populated only where the source provides them. Matches MAY have a `null` venue reference.

#### Scenario: Venue from a tournament match line

- **GIVEN** a match line ending `@ Lusail Iconic Stadium, Lusail`
- **WHEN** sync runs
- **THEN** a venue named `Lusail Iconic Stadium` in city `Lusail` exists and the match references it
- **AND** a repeat sync reuses the same venue UUID (natural key `(name, city)`)

#### Scenario: Fetching a venue by ID

- **WHEN** a client GETs `/v1/venues/{id}`
- **THEN** the API responds 200 with the venue's record, or 404 with the standard error envelope when unknown

### Requirement: Stable identifiers across sources

Every entity row SHALL be addressable by a server-generated UUID that is the sole canonical identifier for that entity. The system SHALL maintain an `external_ref` mapping that links each canonical UUID to zero or more identifiers in external sources.

No external source SHALL be privileged in the schema: `external_ref.source` is a freeform label (initially `wikidata`, `openfootball`; extensible without schema changes).

#### Scenario: Re-ingestion uses external refs to avoid duplicates

- **GIVEN** a team was previously ingested and has `external_ref(source=wikidata, source_id=Q8682)`
- **WHEN** the same team is encountered in a subsequent sync (from any source that supplies a known external ID)
- **THEN** the existing canonical UUID is reused, the row is updated in place rather than duplicated

#### Scenario: New source adds an external ID to an existing entity

- **GIVEN** a team already exists with `external_ref(source=wikidata, source_id=Q8682)`
- **WHEN** ingestion from Open Football encounters `Real Madrid CF`, listed as an alias of that team in `seeds/teams.yaml`
- **THEN** an `external_ref(source=openfootball, source_id="Real Madrid CF")` row exists pointing at the same canonical UUID
- **AND** no new team row is created
