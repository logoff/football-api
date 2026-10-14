# Spec Delta

## MODIFIED Requirements

### Requirement: Competition catalog

The system SHALL maintain a catalog of competitions, each identified by a UUID.

A competition has:

- a display name
- a country code (ISO 3166-1 alpha-2, or ISO 3166-2 `GB-ENG` / `GB-SCT` / `GB-WLS` / `GB-NIR` for the UK home nations) for domestic competitions, or `null` for international competitions
- a `team_kind`: `CLUB` (contested by clubs) or `NATIONAL` (contested by national teams)
- a `scope`: `DOMESTIC` (within a single country), `CONTINENTAL` (within one confederation — UEFA, CONMEBOL, etc.), or `INTERCONTINENTAL` (across confederations)
- a `format`: `LEAGUE` (round-robin), `CUP` (knockout open to the national pyramid), `LEAGUE_CUP` (knockout restricted to league clubs), `SUPER_CUP` (champions' play-off) or `TOURNAMENT` (a group or league phase followed by knockouts)

External identifiers for a competition (Wikidata QID, Open Football file path, etc.) MUST NOT live on the competition row; they are stored exclusively in `external_ref`.

In-scope competitions are:

| Name                       | team_kind | scope            | format     |
| -------------------------- | --------- | ---------------- | ---------- |
| Premier League             | CLUB      | DOMESTIC         | LEAGUE     |
| La Liga                    | CLUB      | DOMESTIC         | LEAGUE     |
| Bundesliga                 | CLUB      | DOMESTIC         | LEAGUE     |
| Serie A                    | CLUB      | DOMESTIC         | LEAGUE     |
| Ligue 1                    | CLUB      | DOMESTIC         | LEAGUE     |
| FA Cup                     | CLUB      | DOMESTIC         | CUP        |
| EFL Cup                    | CLUB      | DOMESTIC         | LEAGUE_CUP |
| Copa del Rey               | CLUB      | DOMESTIC         | CUP        |
| DFB-Pokal                  | CLUB      | DOMESTIC         | CUP        |
| Coppa Italia               | CLUB      | DOMESTIC         | CUP        |
| Coupe de France            | CLUB      | DOMESTIC         | CUP        |
| UEFA Champions League      | CLUB      | CONTINENTAL      | TOURNAMENT |
| UEFA Europa League         | CLUB      | CONTINENTAL      | TOURNAMENT |
| UEFA Conference League     | CLUB      | CONTINENTAL      | TOURNAMENT |
| CONMEBOL Copa Libertadores | CLUB      | CONTINENTAL      | TOURNAMENT |
| FIFA Club World Cup        | CLUB      | INTERCONTINENTAL | TOURNAMENT |
| FIFA World Cup             | NATIONAL  | INTERCONTINENTAL | TOURNAMENT |
| UEFA European Championship | NATIONAL  | CONTINENTAL      | TOURNAMENT |
| CONMEBOL Copa América      | NATIONAL  | CONTINENTAL      | TOURNAMENT |

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

#### Scenario: Filtering competitions by format

- **WHEN** a client GETs `/v1/competitions?format=CUP`
- **THEN** the response lists the FA Cup, Copa del Rey, DFB-Pokal, Coppa Italia and Coupe de France, and no other competition

#### Scenario: Unknown format filter

- **WHEN** a client GETs `/v1/competitions?format=FRIENDLY`
- **THEN** the API responds 422 with the standard error envelope

### Requirement: Season catalog

The system SHALL track one or more seasons per competition. Each season has:

- a reference to its competition
- a label (e.g. `2024-25`, `2022`)
- a start and end date
- a status: `SCHEDULED`, `IN_PROGRESS`, `COMPLETED`

The seasons ingested for each competition are those listed in its seed. The five domestic leagues list every season their source provides: Premier League 2000-01, Bundesliga 2010-11, La Liga 2012-13, Serie A 2013-14 and Ligue 1 2014-15, each up to 2026-27. The domestic cups list every completed season their source provides in full: FA Cup, EFL Cup and DFB-Pokal 2018-19 to 2024-25, Copa del Rey and Coppa Italia 2020-21 to 2024-25, and Coupe de France 2024-25. Every other competition lists only its most recently completed season.

#### Scenario: Listing seasons for a competition

- **WHEN** a client GETs `/v1/seasons?competition_id={uuid}`
- **THEN** the API responds 200 with all seasons of that competition

#### Scenario: Several seasons of one competition

- **GIVEN** La Liga is seeded with the 15 seasons from 2012-13 to 2026-27
- **WHEN** a client GETs `/v1/seasons?competition_id={la-liga}` after a sync
- **THEN** the response lists those 15 seasons, each with 380 matches
- **AND** 2026-27 has status `IN_PROGRESS` while it has both played and unplayed matches

#### Scenario: Full history of another league

- **GIVEN** the Premier League is seeded with the 27 seasons from 2000-01 to 2026-27
- **WHEN** a client GETs `/v1/seasons?competition_id={premier-league}` after a sync
- **THEN** the response lists those 27 seasons, each with 380 matches

#### Scenario: League size changes between seasons

- **GIVEN** Ligue 1 has 20 clubs up to 2022-23 and 18 from 2023-24
- **WHEN** Ligue 1 is synced
- **THEN** 2022-23 has 380 matches and 2023-24 has 306

#### Scenario: Season stopped early

- **GIVEN** Ligue 1 2019-20, stopped after 279 matches, with its remaining fixtures marked cancelled in the source
- **WHEN** it is synced
- **THEN** the season has 380 matches: 279 `COMPLETED` and 101 `CANCELLED` without a score
- **AND** the season's status is `COMPLETED`

#### Scenario: Cup season

- **GIVEN** the DFB-Pokal 2024-25, with two rounds numbered by the source and then named rounds down to the final
- **WHEN** it is synced
- **THEN** the season has 63 `COMPLETED` matches and status `COMPLETED`
