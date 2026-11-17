## MODIFIED Requirements

### Requirement: Standings endpoint

The system SHALL serve `GET /v1/seasons/{id}/standings`, returning the season's tables computed from its stored results. Each table has a stage (`LEAGUE` or `GROUP`), a phase number, an optional group name, a status (`final` or `provisional`) and its rows.

The endpoint SHALL accept `as_of` (a date), counting only matches played on or before it, and `expand=teams`. A season with matches without a date counts them in its tables, and SHALL refuse `as_of` with 422, since those matches can't be placed before or after a date. A season without league or group matches returns no tables. An unknown season returns 404.

#### Scenario: League table

- **GIVEN** the 2023-24 Premier League in the database
- **WHEN** a client GETs `/v1/seasons/{id}/standings`
- **THEN** the API responds 200 with one `LEAGUE` table of 20 rows, status `final`
- **AND** Manchester City is first with 91 points

#### Scenario: Table on a past date

- **WHEN** a client GETs `/v1/seasons/{premier-league-2023-24}/standings?as_of=2023-12-31`
- **THEN** each row counts only matches played on or before 31 December 2023, and the status is `provisional`

#### Scenario: Group tables

- **WHEN** a client GETs the standings of the 2022 FIFA World Cup
- **THEN** the API responds with eight `GROUP` tables, `A` to `H`, of four rows each

#### Scenario: Season without dates

- **GIVEN** La Liga 1955-56, whose matches have no date
- **WHEN** a client GETs `/v1/seasons/{id}/standings`
- **THEN** the API responds 200 with one `LEAGUE` table of 16 rows, status `final`, counting all 240 matches

#### Scenario: Past date on a season without dates

- **WHEN** a client GETs `/v1/seasons/{la-liga-1955-56}/standings?as_of=1956-01-01`
- **THEN** the API responds 422 with an error saying the season's matches have no dates

### Requirement: Ranking rules

Each competition SHALL declare its ranking rules in `seeds/competitions.yaml` as eras, each with points per win, draw and loss and an ordered list of tie-breakers. A season uses the last era starting at or before it.

Teams SHALL be ordered:

1. by points (or by points per game, when the season is declared to rank that way);
1. then by the tie-breakers in order, with head-to-head criteria computed among the teams still level.

Teams still level after the last tie-breaker are marked `tied`.

#### Scenario: Goal difference first

- **GIVEN** the Premier League's tie-breakers are goal difference, then goals scored
- **WHEN** two teams finish level on points
- **THEN** the one with the better goal difference is placed higher, whatever their head-to-head results

#### Scenario: Head-to-head first

- **GIVEN** La Liga's tie-breakers start with head-to-head points
- **WHEN** two teams finish level on points
- **THEN** the one that took more points in their two matches is placed higher, even with a worse overall goal difference

#### Scenario: Points per game

- **GIVEN** the 2019-20 Ligue 1 season is declared to rank by points per game
- **WHEN** a client GETs its standings
- **THEN** teams are ordered by points divided by matches played

#### Scenario: Two points for a win in older La Liga seasons

- **GIVEN** La Liga's ranking rules give two points for a win until 1994-95 and three from 1995-96
- **WHEN** a client GETs the standings of La Liga 1994-95 and of 1995-96
- **THEN** each win is worth 2 points in the first table and 3 in the second
