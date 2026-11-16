## MODIFIED Requirements

### Requirement: Season catalog

The system SHALL track one or more seasons per competition. Each season has:

- a reference to its competition
- a label (e.g. `2024-25`, `2022`)
- a start and end date
- a status: `SCHEDULED`, `IN_PROGRESS`, `COMPLETED`

The seasons ingested for each competition are those listed in its seed. The five domestic leagues list every season their source provides: Premier League 1992-93, Bundesliga 2010-11, La Liga 2012-13, Serie A 2013-14 and Ligue 1 2014-15, each up to 2026-27. Segunda División lists every season its source provides in full, 2012-13 to 2024-25. The domestic cups list every completed season their source provides in full: FA Cup, EFL Cup and DFB-Pokal 2018-19 to 2024-25, Copa del Rey and Coppa Italia 2020-21 to 2024-25, and Coupe de France 2024-25. The international competitions list every edition their source provides with a date for every match: UEFA Champions League 1955-56 to 2025-26 (the European Cup up to 1991-92; up to 2010-11 from English Wikipedia, see `season-sources`), UEFA Europa League 2020-21 to 2024-25, UEFA Conference League 2021-22 to 2024-25, CONMEBOL Copa Libertadores 2012 to 2026, FIFA Club World Cup 2000 to 2025, FIFA World Cup 1930 to 2026, UEFA European Championship 1960 to 2024, and CONMEBOL Copa América 2011, 2021 and 2024. Editions in progress are included.

#### Scenario: Listing seasons for a competition

- **WHEN** a client GETs `/v1/seasons?competition_id={uuid}`
- **THEN** the API responds 200 with all seasons of that competition

#### Scenario: Several seasons of one competition

- **GIVEN** La Liga is seeded with the 15 seasons from 2012-13 to 2026-27
- **WHEN** a client GETs `/v1/seasons?competition_id={la-liga}` after a sync
- **THEN** the response lists those 15 seasons, each with 380 matches
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

- **GIVEN** a tournament edition whose source lists some matches without a date
- **WHEN** the seeds are reviewed
- **THEN** that edition is not listed, and the README names it as a known gap

#### Scenario: European Cup history

- **GIVEN** the Champions League is seeded with 1955-56 to 2010-11 from Wikipedia and 2011-12 onwards from openfootball
- **WHEN** a client GETs `/v1/seasons?competition_id={champions-league}` after a sync
- **THEN** the response lists every season from 1955-56, the 1955-56 one with 29 matches
- **AND** seasons up to 1993-94 hold every round, since all of them were the competition proper, while from 1994-95 the qualifying rounds are left out

### Requirement: Team catalog

The system SHALL maintain a catalog of teams of two kinds: `CLUB` (e.g. Real Madrid) and `NATIONAL` (e.g. Spain).

A team has:

- a display name
- a primary country
- the kind (`CLUB` | `NATIONAL`)
- a many-to-many relationship with seasons (the seasons in which this team participated)

External identifiers for a team are stored exclusively in `external_ref`.

Team identity is defined by the curated seed file `seeds/teams.yaml`, which lists each team's name, kind, country, Wikidata QID, and every Open Football spelling of its name. A team that appears only in seasons sourced from Wikipedia needs no spelling: its QID identifies it. An entry is matched to its existing row through those external identifiers, so editing a name never creates a second team. Sync SHALL NOT create a team that is not in this file.

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

#### Scenario: Team known only from Wikipedia seasons

- **GIVEN** a team seeded with name, kind, country and QID, and no Open Football spelling
- **WHEN** the seeds load and a Wikipedia season linking its article syncs
- **THEN** the load succeeds and the team takes part in that season
