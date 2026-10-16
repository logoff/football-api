# Spec Delta

## MODIFIED Requirements

### Requirement: Curated adjustments

The system SHALL apply the entries of `seeds/standings.yaml`, each with a reason and a source:

- **Point adjustments** for a team in a season, optionally effective from a date.
- **Orders** for teams level on points that a play-off or a non-sporting criterion separated: they apply when the order's teams are exactly a set level on points, or a set the tie-breakers leave level.
- **Awarded winners** for an awarded match the source records with a level score and no goals awarded: the named winner gets the win and the other team the loss, while the goals stay as recorded.

Rows SHALL show the adjustments applied. An entry naming an unknown competition, season or team SHALL fail the seed load.

#### Scenario: Point deduction

- **GIVEN** `seeds/standings.yaml` deducts 8 points from Everton in the 2023-24 Premier League
- **WHEN** a client GETs that season's standings
- **THEN** Everton's points are 8 fewer than its results give, and its row lists the deduction with its reason and source

#### Scenario: Tie settled off the table

- **GIVEN** two teams finish level on every tie-breaker, and `seeds/standings.yaml` orders them as a play-off decided
- **WHEN** a client GETs the standings
- **THEN** the teams appear in that order, both marked `tied`

#### Scenario: Awarded win without goals

- **GIVEN** Bastia v Lyon 2016-17 is stored as `0-0`, awarded, and `seeds/standings.yaml` names Lyon the winner
- **WHEN** a client GETs the 2016-17 Ligue 1 standings
- **THEN** Lyon has the win and its three points, and both teams' goals count the match as 0-0

## ADDED Requirements

### Requirement: Group play-offs

In a group played once round, a pairing that meets again SHALL be treated as a play-off and left out of the table. Groups played home and away keep both legs.

#### Scenario: World Cup play-off

- **GIVEN** Northern Ireland and Czechoslovakia met in Group 1 of the 1958 World Cup and again in a play-off listed under the group
- **WHEN** a client GETs the 1958 standings
- **THEN** each team in Group 1 has played 3

### Requirement: Standings verification

With `--verify`, the system SHALL compare each final table of a synced season with the English Wikipedia standings table that holds the same teams. The tables come from the season article named in the seeds, and from its group sub-articles.

Provisional tables SHALL keep no status.

#### Scenario: Agreeing table

- **GIVEN** the 2023-24 Premier League table, with Everton's deductions in `seeds/standings.yaml`
- **WHEN** verification runs
- **THEN** all 20 rows are `VERIFIED`

#### Scenario: Missing deduction

- **GIVEN** a final table whose team had points deducted that `seeds/standings.yaml` doesn't list
- **WHEN** verification runs
- **THEN** that team's row is `MISMATCH`, and the log shows both point totals

#### Scenario: Provisional table

- **GIVEN** a season in progress
- **WHEN** verification runs
- **THEN** its table rows have no verification status

### Requirement: Standings verification statuses

Each row of a compared table SHALL get a status against the reference `wikipedia`:

- `VERIFIED` when position, played, won, drawn, lost, goals for, goals against and points all agree.;
- `MISMATCH` when any of them differs, logged with both sets of values;
- `UNCONFIRMED` when no Wikipedia table holds exactly the table's teams.

#### Scenario: Table without a counterpart

- **GIVEN** a final group table whose teams no Wikipedia table holds exactly
- **WHEN** verification runs
- **THEN** its rows are `UNCONFIRMED`

### Requirement: Standings verification tolerances

Teams marked `tied` SHALL agree on any position within their tied block, since a reference may share such positions or order them by lots. Reference rows with no games played, such as withdrawn teams, SHALL be ignored when pairing tables.

#### Scenario: Shared position

- **GIVEN** Chile and the United States both finished on 2 points in the 1950 World Cup's Group 2, which Wikipedia shows as a shared position
- **WHEN** verification runs
- **THEN** both rows are `VERIFIED`

### Requirement: Standings verification in the API

The API SHALL expose each standings row's status as `verification` (`status`, `reference`, `checked_at`), or `null` when it has none. Wikipedia's values SHALL never be stored or served.

#### Scenario: Row with a status

- **GIVEN** a verified final table
- **WHEN** a client GETs its season's standings
- **THEN** each row has `verification.status` `VERIFIED` and `verification.reference` `wikipedia`
