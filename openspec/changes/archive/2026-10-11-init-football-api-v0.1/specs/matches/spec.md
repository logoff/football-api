# Matches Capability

## Purpose

Expose fixtures (scheduled matches) and results (completed matches) for all in-scope competitions, including goal scorers where the source provides them. Match records are immutable post-completion; pre-completion they may carry placeholder data.

## ADDED Requirements

### Requirement: Match record

The system SHALL store each match with:

- a UUID
- a reference to its season
- references to home and away teams
- an optional reference to a venue
- a kickoff timestamp in UTC, and an optional `original_kickoff_utc` set when the kickoff is first observed to change
- a status: `SCHEDULED`, `COMPLETED`, `CANCELLED`, `POSTPONED`
- home and away scores at the end of play, including extra time (nullable until `COMPLETED`)
- `decided_by`: `REGULAR`, `EXTRA_TIME`, or `PENALTIES` (nullable until `COMPLETED`)
- home and away penalty-shootout scores (null unless `decided_by` is `PENALTIES`)
- a stage: `QUALIFYING`, `LEAGUE`, `GROUP`, `PLAYOFF`, `R32`, `R16`, `QF`, `SF`, `THIRD_PLACE`, or `FINAL`; an optional matchday number; and the source's round label

#### Scenario: Filtering matches by competition and season

- **WHEN** a client GETs `/v1/matches?season_id={premier-league-2024-25}`
- **THEN** the API responds 200 with all matches of that competition-season

#### Scenario: Filtering matches by team

- **WHEN** a client GETs `/v1/matches?team_id={real-madrid}&competition_id={la-liga}`
- **THEN** the API responds 200 with all matches where the team appears as home or away

#### Scenario: Expanding related resources

- **WHEN** a client GETs `/v1/matches/{id}?expand=teams,venue,scorers`
- **THEN** the response embeds the home/away team objects, the venue object (when present), and the array of goal records

#### Scenario: Match decided on penalties

- **GIVEN** the source line `Argentina 3-3 a.e.t. (2-2, 2-0), 4-2 pen. France`
- **WHEN** the match is ingested
- **THEN** `home_score`=3, `away_score`=3, `decided_by`=`PENALTIES`, `home_pens`=4, `away_pens`=2
- **AND** the shootout kicks are not stored as goals

#### Scenario: Postponed match keeps a single row

- **GIVEN** a match previously synced with kickoff `2025-01-11T15:00:00Z`
- **WHEN** the source moves it to `2025-02-05T19:30:00Z` and sync runs
- **THEN** the same match UUID now has `kickoff_utc` `2025-02-05T19:30:00Z` and `original_kickoff_utc` `2025-01-11T15:00:00Z`
- **AND** no second row exists for that `(season, stage, home, away)`

#### Scenario: Same pairing in two stages of one season

- **GIVEN** Arsenal v Paris Saint-Germain in both the UCL 2024-25 league phase and semi-final
- **WHEN** sync runs
- **THEN** two distinct matches exist, one with stage `LEAGUE` and one with stage `SF`

### Requirement: Goal scorers

The system SHALL record goal scorers for a match where the source data includes them. Each goal has a UUID and is linked to:

- the match, with an `ordinal` (1-based position within the match in source order)
- the scoring player when the scorer string resolves to a unique squad member (case- and accent-insensitive); otherwise `scorer_name` holds the raw source text and the player reference is null
- the side (`HOME` or `AWAY`)
- an optional `minute` and an optional `added_minute` for time added at the end of a half or of extra time (`90+5'` → 90 and 5, distinct from `95'`)
- flags: `is_own_goal`, `is_penalty`

Scorer coverage in v0.1 is `full` for WC 2022, Euro 2024, Copa América 2024 and Club World Cup 2025, and `none` for every other competition. This MUST be stated in OpenAPI descriptions and the README.

#### Scenario: Partial coverage is exposed honestly

- **GIVEN** a Premier League match where the source does not provide scorers
- **WHEN** a client requests the match with `?expand=scorers`
- **THEN** the `scorers` array is empty
- **AND** the match record includes a `coverage` field indicating `scorers: "none"`

#### Scenario: Unresolved scorer kept as text

- **GIVEN** a scorer string `Koulibaly 70'` and no unique squad member matching it
- **WHEN** the match is ingested
- **THEN** the goal has `scorer_player_id` null and `scorer_name` `Koulibaly`

#### Scenario: Goal in added time

- **GIVEN** a scorer string `Davy Klaassen 90+9'`
- **WHEN** the match is ingested
- **THEN** the goal has `minute` 90 and `added_minute` 9

### Requirement: Date and timezone semantics

The system SHALL store and emit all timestamps in UTC, ISO 8601 format with a `Z` suffix.

Source kickoff times are converted to UTC using, in order: an explicit offset on the match line, else the time zone configured for the source file. Sync SHALL fail for a match line with neither.

#### Scenario: Explicit offset on the line

- **GIVEN** the line `Sat Jun 14 20:00 UTC-4 @ Miami Stadium, Miami`
- **WHEN** the match is ingested
- **THEN** `kickoff_utc` is `2025-06-15T00:00:00Z`

#### Scenario: File-level time zone

- **GIVEN** `england/2024-25/1-premierleague.txt` is configured as `Europe/London` and contains `Fri Aug 16 2024 20:00`
- **WHEN** the match is ingested
- **THEN** `kickoff_utc` is `2024-08-16T19:00:00Z`

#### Scenario: Filtering by date range

- **WHEN** a client GETs `/v1/matches?from=2024-08-01&to=2024-09-01`
- **THEN** the API responds 200 with matches whose `kickoff_utc` falls within the inclusive date range
