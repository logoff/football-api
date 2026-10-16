# standings Specification

## Purpose

Serve league tables, and group tables for tournaments, computed from the stored results with each competition's own ranking rules, and with point deductions and off-the-table decisions that are curated, sourced and visible on every row.

## Requirements

### Requirement: Standings endpoint

The system SHALL serve `GET /v1/seasons/{id}/standings`, returning the season's tables computed from its stored results. Each table has a stage (`LEAGUE` or `GROUP`), a phase number, an optional group name, a status (`final` or `provisional`) and its rows.

The endpoint SHALL accept `as_of` (a date), counting only matches played on or before it, and `expand=teams`. A season without league or group matches returns no tables. An unknown season returns 404.

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

### Requirement: Table rows

Each row SHALL have:

- position and team
- played, won, drawn, lost
- goals for, goals against, goal difference
- points
- the point adjustments applied, each with points, reason and source
- `tied`: `true` when results alone could not separate the team from a neighbour

#### Scenario: Row totals

- **GIVEN** a team with 28 wins, 7 draws and 3 losses, 96 goals scored and 34 conceded in a 38-round league with three points for a win
- **WHEN** its row is computed
- **THEN** it reads played 38, won 28, drawn 7, lost 3, goals for 96, goals against 34, goal difference 62, points 91

### Requirement: Matches counted

A table SHALL count each `COMPLETED` match with a score in its stage. Awarded matches count with the score the source records. Each team's points come from the competition's points per win, draw and loss for that season.

#### Scenario: Two points for a win

- **GIVEN** the World Cup's ranking rules give two points for a win until 1990
- **WHEN** a client GETs the standings of the 1986 FIFA World Cup
- **THEN** a group winner with two wins and a draw has 5 points

### Requirement: Groups

Group tables SHALL be formed per phase and group:

- **Phase:** a round label beginning `Second Round` is phase 2; any other label is phase 1.
- **Group:** taken from the label (`Group A`, `Gruppe A`, `Group 1`, `First stage / Group A`, …).
- **Unnamed groups:** when a phase's labels name no group, its groups are the sets of teams connected by the matches they played, and have no name.

#### Scenario: Second-round groups

- **WHEN** a client GETs the standings of the 1982 FIFA World Cup
- **THEN** there are six phase-1 groups and four phase-2 groups

#### Scenario: Groups not named by the source

- **GIVEN** the 2023-24 UEFA Champions League lists its group matches by matchday only
- **WHEN** a client GETs its standings
- **THEN** there are eight `GROUP` tables of four teams with no group name, each holding teams that played each other

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

### Requirement: Curated adjustments

The system SHALL apply the entries of `seeds/standings.yaml`, each with a reason and a source:

- **Point adjustments** for a team in a season, optionally effective from a date.
- **Orders** for teams level on points that a play-off or a non-sporting criterion separated: they apply when the order's teams are exactly a set level on points, or a set the tie-breakers leave level.

Rows SHALL show the adjustments applied. An entry naming an unknown competition, season or team SHALL fail the seed load.

#### Scenario: Point deduction

- **GIVEN** `seeds/standings.yaml` deducts 8 points from Everton in the 2023-24 Premier League
- **WHEN** a client GETs that season's standings
- **THEN** Everton's points are 8 fewer than its results give, and its row lists the deduction with its reason and source

#### Scenario: Tie settled off the table

- **GIVEN** two teams finish level on every tie-breaker, and `seeds/standings.yaml` orders them as a play-off decided
- **WHEN** a client GETs the standings
- **THEN** the teams appear in that order, both marked `tied`
