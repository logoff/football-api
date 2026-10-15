# Spec Delta

## MODIFIED Requirements

### Requirement: Season catalog

The system SHALL track one or more seasons per competition. Each season has:

- a reference to its competition
- a label (e.g. `2024-25`, `2022`)
- a start and end date
- a status: `SCHEDULED`, `IN_PROGRESS`, `COMPLETED`

The seasons ingested for each competition are those listed in its seed. The five domestic leagues list every season their source provides: Premier League 1992-93, Bundesliga 2010-11, La Liga 2012-13, Serie A 2013-14 and Ligue 1 2014-15, each up to 2026-27. The domestic cups list every completed season their source provides in full: FA Cup, EFL Cup and DFB-Pokal 2018-19 to 2024-25, Copa del Rey and Coppa Italia 2020-21 to 2024-25, and Coupe de France 2024-25. The international competitions list every edition their source provides with a date for every match: UEFA Champions League 2011-12 to 2025-26, UEFA Europa League 2020-21 to 2024-25, UEFA Conference League 2021-22 to 2024-25, CONMEBOL Copa Libertadores 2012 to 2026, FIFA Club World Cup 2000 to 2025, FIFA World Cup 1930 to 2026, UEFA European Championship 1960 to 2024, and CONMEBOL Copa América 2011, 2021 and 2024. Editions in progress are included.

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
