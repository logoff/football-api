# Match Events Capability

## Purpose

Record what happened inside a match beyond goals (who played, who was substituted, who was booked, who refereed and how many attended), and expose it through the match resource with honest per-season coverage.

## ADDED Requirements

### Requirement: Events source

A season in `seeds/competitions.yaml` MAY name an openfootball `-full` text file as `events:`. Lineups, substitutions, cards, referee and attendance SHALL come only from it; matches, scores and goals SHALL keep coming from `file:` (or its JSON mirror). Each events-file match SHALL link to the season's synced match with the same day, home team and away team; linking to none or to several SHALL fail the season's sync, naming the file and line.

#### Scenario: League season with a JSON mirror

- **GIVEN** the Premier League 2025-26 season with `file: england/2025-26/1-premierleague.txt`, a current JSON mirror, and `events: england/2025-26/1-premierleague-full.txt`
- **WHEN** it is synced
- **THEN** its matches and goals come from the JSON mirror as before, with the same UUIDs and verification statuses
- **AND** each match has the lineups and cards of the events file

#### Scenario: Events file lists a match that isn't synced

- **GIVEN** an events file that lists a match whose day and teams match no synced match of the season
- **WHEN** the season is synced
- **THEN** the season's sync fails with the events file's path and the match's line number

#### Scenario: Season without an events file

- **WHEN** a client GETs a Champions League match with `?expand=lineups,substitutions,cards`
- **THEN** `lineups.home.entries`, `lineups.away.entries`, `substitutions` and `cards` are empty
- **AND** `coverage.lineups`, `coverage.substitutions` and `coverage.cards` are `none`

### Requirement: Lineups

The system SHALL store, per match and side, every player who appeared: starters and the substitutes who came on. Each entry records its role (`STARTER` or `SUBSTITUTE`), a captain flag and, for starters, the 1-based index of the source line group it was listed in. The first lineup after a match is the home side's and the second the away side's; each SHALL be headed by that side's spelling on the match line, without any trailing country code, or sync fails.

#### Scenario: Starter line groups and captain

- **GIVEN** the source lineup `Chelsea FC: Robert SANCHEZ - Marc CUCURELLA, …, Reece JAMES [c], … - Enzo FERNANDEZ, …` under `Chelsea FC (ENG) v Paris Saint-Germain (FRA)`
- **WHEN** the match is ingested
- **THEN** `Robert Sanchez` is a home `STARTER` in line 1
- **AND** `Reece James` is a home `STARTER` in line 2 with `is_captain` true

#### Scenario: Substitute who came on

- **GIVEN** the lineup fragment `Enzo FERNANDEZ (61' ANDREY SANTOS)`
- **WHEN** the match is ingested
- **THEN** `Andrey Santos` is a `SUBSTITUTE` lineup entry for that side with no line index

#### Scenario: Match without a lineup block

- **GIVEN** Club World Cup 2020's Al Duhail v Auckland City, listed with a score and no lineups
- **WHEN** it is synced
- **THEN** it has no lineup entries, substitutions or cards, and no error is raised

### Requirement: Formation

The system SHALL expose, per match and side, a formation string made of the number of starters in each line group after the first, joined by `-`. It reflects the source's grouping, not an independently verified tactical shape. It SHALL be null when the side's starters form a single group.

#### Scenario: Deriving a formation

- **GIVEN** a side's starters are grouped 1 / 4 / 3 / 3 in the source
- **WHEN** a client GETs `/v1/matches/{id}?expand=lineups`
- **THEN** that side's `formation` is `4-3-3`

#### Scenario: Lineup without line groups

- **GIVEN** a Club World Cup 2018 lineup that lists eleven starters separated only by commas
- **WHEN** a client GETs the match with `?expand=lineups`
- **THEN** that side's `formation` is null

### Requirement: Substitutions

The system SHALL store each substitution with its side, minute, the player going off and the player coming on, including substitutions of players who themselves came on as substitutes.

#### Scenario: Chained substitution

- **GIVEN** the fragment `EMAM ASHOUR (14' ZIZO (79' MOHAMED AFSHA))`
- **WHEN** the match is ingested
- **THEN** there is a substitution at minute 14 with `Emam Ashour` off and `Zizo` on
- **AND** a substitution at minute 79 with `Zizo` off and `Mohamed Afsha` on

### Requirement: Cards

The system SHALL store each card with its side, player, minute and kind: `YELLOW`, `SECOND_YELLOW` or `RED`, read from inline tags (`[Y m']`, `[Y/R m']`, `[R m']`) or from card lines after a side's lineup (`Yellow:`, `Yellow-Red:`, `Red:`); each notation lists the three kinds in that order. A sending-off for a second yellow is two cards, a `YELLOW` and a `SECOND_YELLOW`, as both notations list them.

#### Scenario: Second yellow, inline

- **GIVEN** the fragment `Igor SMOLNIKOV [Y 28'] [Y/R 36']`
- **WHEN** the match is ingested
- **THEN** that player has a `YELLOW` card at minute 28 and a `SECOND_YELLOW` card at minute 36

#### Scenario: Second yellow, card lines

- **GIVEN** Burnley's lineup in Burnley v Liverpool (2025-26 Premier League) followed by `Yellow: Lesley UGOCHUKWU 16'` and `Yellow-Red: Lesley UGOCHUKWU 84'`
- **WHEN** the match is ingested
- **THEN** `Lesley Ugochukwu` has a home `YELLOW` card at minute 16 and a home `SECOND_YELLOW` card at minute 84

#### Scenario: Card shown to a substitute

- **GIVEN** the fragment `JOAO MARIO (77' Nehuen PEREZ [Y 90+1'])`
- **WHEN** the match is ingested
- **THEN** the `YELLOW` card belongs to `Nehuen Perez`, not `Joao Mario`

#### Scenario: Unknown notation fails

- **GIVEN** a lineup containing a tag other than `[c]`, `[Y …]`, `[Y/R …]` or `[R …]`
- **WHEN** the season is synced
- **THEN** sync fails with the events file's path and line number

### Requirement: Event minutes

Every substitution and card SHALL carry a `minute` and a nullable `added_minute` for time added at the end of a half or of extra time, parsed by the same rule as goal minutes. A minute the source writes without `+` (`94'`) SHALL be stored as written.

#### Scenario: Added time

- **GIVEN** a card marked `[Y 90+2']`
- **WHEN** the match is ingested
- **THEN** the card has `minute` 90 and `added_minute` 2

### Requirement: Event player resolution

Each lineup entry, substitution player and card SHALL reference a squad player of that team-season when the source name resolves to exactly one, compared case- and accent-insensitively. Otherwise it SHALL keep the source name, title-cased like goal scorers, with a null player reference. The name SHALL be stored in both cases.

#### Scenario: Resolved against the squad

- **GIVEN** World Cup 2022, whose squads are ingested, and a lineup name that matches one squad member
- **WHEN** the match is ingested
- **THEN** the lineup entry references that player and has that `player_name`

#### Scenario: Season without squads

- **GIVEN** a 2025-26 Premier League match
- **WHEN** it is ingested
- **THEN** every lineup entry, substitution and card has a null player reference and a `player_name`

### Requirement: Referee and attendance

The system SHALL store the referee's name and the attendance on the match, both nullable. The referee is the first name on the match's `Refs:` line, title-cased and without a bracketed country. The attendance is `Att: <n>` on the match's date or venue line.

#### Scenario: Match header and referee line

- **GIVEN** a header containing `Att: 81118` and a line `Refs: Alireza FAGHANI (AUS)`
- **WHEN** the match is ingested
- **THEN** the match has `attendance` 81118 and `referee` `Alireza Faghani`

#### Scenario: Referee with assistants

- **GIVEN** the line `Refs: Michael Oliver, Stuart Burt, James Mainwaring`
- **WHEN** the match is ingested
- **THEN** the match has `referee` `Michael Oliver`

#### Scenario: Source without attendance

- **WHEN** a client GETs a World Cup 1990 match
- **THEN** `attendance` is null

### Requirement: Event exposure

The system SHALL embed lineups (with per-side formation), substitutions and cards in match responses only when requested through `expand=lineups`, `expand=substitutions` and `expand=cards`, on both `/v1/matches` and `/v1/matches/{id}`. Substitutions and cards SHALL be ordered by minute, added minute, then source order.

#### Scenario: Expanding events

- **WHEN** a client GETs `/v1/matches/{id}?expand=lineups,substitutions,cards`
- **THEN** the response contains `lineups.home` and `lineups.away` (each with `formation` and entries), `substitutions` and `cards`

#### Scenario: Not expanded

- **WHEN** a client GETs `/v1/matches/{id}` without `expand`
- **THEN** the response contains no `lineups`, `substitutions` or `cards` keys

### Requirement: Event coverage

Each season SHALL record `lineups`, `substitutions` and `cards` coverage, each `full` when the season's events file provides that part, and `none` otherwise or without an events file. Season and match responses SHALL include them under `coverage`, next to `scorers`. A match with no cards in a season with `cards: full` had no cards. The OpenAPI descriptions and the README SHALL state which competitions and seasons have each part.

#### Scenario: Season with starters only

- **WHEN** a client GETs a Club World Cup 2019 match
- **THEN** `coverage.lineups` is `full`, and `coverage.substitutions` and `coverage.cards` are `none`

#### Scenario: Season with every part

- **WHEN** a client GETs a 2025-26 Bundesliga match
- **THEN** `coverage.lineups`, `coverage.substitutions` and `coverage.cards` are `full`

### Requirement: Idempotent event sync

Re-running sync with unchanged sources SHALL leave every event row and UUID unchanged. Lineup entries, substitutions and cards are identified by `(match, side, ordinal)` in source order; ordinals beyond the source's count are deleted. A match deleted because the source no longer lists it SHALL take its events with it.

#### Scenario: Repeat sync

- **GIVEN** World Cup 2022 events already synced
- **WHEN** sync runs again with no source change
- **THEN** every lineup entry, substitution and card keeps its UUID and values

#### Scenario: Source drops a card

- **GIVEN** a match synced with 4 home cards
- **WHEN** the source is corrected to 3 home cards and sync runs
- **THEN** home cards with ordinals 1–3 keep their UUIDs and the card with ordinal 4 is deleted
