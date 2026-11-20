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
| Segunda División           | CLUB      | DOMESTIC         | LEAGUE     |
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
| UEFA Cup Winners' Cup      | CLUB      | CONTINENTAL      | TOURNAMENT |
| CONMEBOL Copa Libertadores | CLUB      | CONTINENTAL      | TOURNAMENT |
| CONMEBOL Copa Sudamericana | CLUB      | CONTINENTAL      | TOURNAMENT |
| FIFA Club World Cup        | CLUB      | INTERCONTINENTAL | TOURNAMENT |
| FIFA World Cup             | NATIONAL  | INTERCONTINENTAL | TOURNAMENT |
| UEFA European Championship | NATIONAL  | CONTINENTAL      | TOURNAMENT |
| CONMEBOL Copa América      | NATIONAL  | CONTINENTAL      | TOURNAMENT |
| CAF Africa Cup of Nations  | NATIONAL  | CONTINENTAL      | TOURNAMENT |

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
- a start and end date, null for a season whose matches have no dates
- a status: `SCHEDULED`, `IN_PROGRESS`, `COMPLETED`

The seasons ingested for each competition are those listed in its seed. The five domestic leagues list every season their source provides: Premier League 1992-93, Bundesliga 2010-11, La Liga 1929 (up to 2011-12 from English Wikipedia, without match dates, see `season-sources`), Serie A 2013-14 and Ligue 1 2014-15, each up to 2026-27. Segunda División lists every season its source provides in full, 2012-13 to 2024-25. The domestic cups list every completed season their source provides in full: FA Cup, EFL Cup and DFB-Pokal 2018-19 to 2024-25, Copa del Rey and Coppa Italia 2020-21 to 2024-25, and Coupe de France 2024-25. The international competitions list every edition their source provides with a date for every match: UEFA Champions League 1955-56 to 2025-26 (the European Cup up to 1991-92; up to 2010-11 from English Wikipedia, see `season-sources`), UEFA Europa League 1971-72 to 2024-25 (the UEFA Cup up to 2008-09; up to 2019-20 from English Wikipedia), UEFA Cup Winners' Cup 1960-61 to 1998-99 (from English Wikipedia), UEFA Conference League 2021-22 to 2024-25, CONMEBOL Copa Libertadores 2012 to 2026, FIFA Club World Cup 2000 to 2025, FIFA World Cup 1930 to 2026, UEFA European Championship 1960 to 2024 (1984 and 1992 from English Wikipedia), CONMEBOL Copa América 1916 to 2024 (every edition up to 2019 from English Wikipedia, except 2011), CONMEBOL Copa Sudamericana 2012 to 2025 (2025 from English Wikipedia), and CAF Africa Cup of Nations 1957 to 2025 (from English Wikipedia). Editions in progress are included.

#### Scenario: Listing seasons for a competition

- **WHEN** a client GETs `/v1/seasons?competition_id={uuid}`
- **THEN** the API responds 200 with all seasons of that competition

#### Scenario: Several seasons of one competition

- **GIVEN** the Bundesliga is seeded with the 17 seasons from 2010-11 to 2026-27
- **WHEN** a client GETs `/v1/seasons?competition_id={bundesliga}` after a sync
- **THEN** the response lists those 17 seasons, each with 306 matches
- **AND** 2026-27 has status `IN_PROGRESS` while it has both played and unplayed matches

#### Scenario: Full history of another league

- **GIVEN** the Premier League is seeded with the 35 seasons from 1992-93 to 2026-27
- **WHEN** a client GETs `/v1/seasons?competition_id={premier-league}` after a sync
- **THEN** the response lists those 35 seasons
- **AND** the 22-club seasons 1992-93 to 1994-95 have 462 matches each and every later season has 380

#### Scenario: Second tier

- **GIVEN** Segunda División is seeded with the 13 seasons from 2012-13 to 2024-25
- **WHEN** a client GETs `/v1/seasons?competition_id={segunda-division}` after a sync
- **THEN** the response lists those 13 seasons, each with 22 clubs and 462 matches
- **AND** 2025-26 is not listed, because its source stops after 131 results

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

#### Scenario: Full history of a tournament

- **GIVEN** the FIFA World Cup is seeded with every edition from 1930 to 2026
- **WHEN** a client GETs `/v1/seasons?competition_id={world-cup}` after a sync
- **THEN** the response lists 23 seasons, the 1930 one with 18 matches and the 2026 one with 104

#### Scenario: Edition without dates for every match

- **GIVEN** a tournament edition whose source dates some of its matches and lists others without a date
- **WHEN** the seeds are reviewed
- **THEN** that edition is read from English Wikipedia if its match boxes have every date, and otherwise isn't listed and the README names it as a known gap

#### Scenario: Euro editions without dates in openfootball

- **GIVEN** Euro 1984 and Euro 1992, whose openfootball files list the group matches without a date, are seeded from Wikipedia
- **WHEN** a client GETs `/v1/seasons?competition_id={euro}` after a sync
- **THEN** the response lists 17 seasons from 1960 to 2024
- **AND** 1984 and 1992 have 15 matches each, every one with a date

#### Scenario: European Cup history

- **GIVEN** the Champions League is seeded with 1955-56 to 2010-11 from Wikipedia and 2011-12 onwards from openfootball
- **WHEN** a client GETs `/v1/seasons?competition_id={champions-league}` after a sync
- **THEN** the response lists every season from 1955-56, the 1955-56 one with 29 matches
- **AND** seasons up to 1993-94 hold every round, since all of them were the competition proper, while from 1994-95 the qualifying rounds are left out

#### Scenario: La Liga history

- **GIVEN** La Liga is seeded with 1929 to 2011-12 from Wikipedia and 2012-13 onwards from openfootball
- **WHEN** a client GETs `/v1/seasons?competition_id={la-liga}` after a sync
- **THEN** the response lists 96 seasons, from `1929` with 90 matches, with no seasons from 1936-37 to 1938-39
- **AND** the seasons up to 2011-12 have no start or end date, and every one of their matches has a null kickoff

#### Scenario: Cup Winners' Cup

- **GIVEN** the Cup Winners' Cup is seeded with 1960-61 to 1998-99 from Wikipedia
- **WHEN** a client GETs `/v1/seasons?competition_id={cup-winners-cup}` after a sync
- **THEN** the response lists 39 seasons, each a knockout from its first round to the final
- **AND** from 1994-95 the qualifying round is left out

#### Scenario: UEFA Cup history

- **GIVEN** the Europa League is seeded with 1971-72 to 2019-20 from Wikipedia and 2020-21 onwards from openfootball
- **WHEN** a client GETs `/v1/seasons?competition_id={europa-league}` after a sync
- **THEN** the response lists every season from 1971-72
- **AND** 2004-05 to 2008-09 have eight groups of five teams, each played once

#### Scenario: Copa América history

- **GIVEN** the Copa América is seeded with every edition from 1916 to 2019 from Wikipedia, except 2011, and 2011, 2021 and 2024 from openfootball
- **WHEN** a client GETs `/v1/seasons?competition_id={copa-america}` after a sync
- **THEN** the response lists 48 seasons, from `1916` with 7 matches
- **AND** the two editions played in 1959 are labelled `1959 Argentina` and `1959 Ecuador`
- **AND** 1967 has no qualifying round

#### Scenario: Africa Cup of Nations history

- **GIVEN** the Africa Cup of Nations seeded with its 35 editions from 1957 to 2025, pinned to Wikipedia revisions
- **WHEN** a client GETs `/v1/seasons?competition_id={afcon}` after a sync
- **THEN** the response lists those 35 seasons, the 2021 edition labelled `2021` with its matches in January and February 2022
- **AND** each season's `source` names English Wikipedia and `CC-BY-SA-4.0`

#### Scenario: Copa Sudamericana from two sources

- **GIVEN** the Copa Sudamericana seeded with 2012 to 2024 from openfootball and 2025 pinned to a Wikipedia revision
- **WHEN** a client GETs `/v1/seasons?competition_id={sudamericana}` after a sync
- **THEN** the response lists 14 seasons, 2012 to 2025
- **AND** the 2016 final's two legs are `CANCELLED` without a score
