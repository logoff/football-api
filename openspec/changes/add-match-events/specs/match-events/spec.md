# Match Events Capability

## Purpose

Record what happened inside a match beyond goals — who played, who was substituted, who was booked, who refereed, and how many attended — and expose it through the match resource with honest per-match coverage.

## ADDED Requirements

### Requirement: Lineups

The system SHALL store, per match and side, every player who appeared: starters and substitutes who came on. Each entry records its role (`STARTER` or `SUBSTITUTE`), a captain flag, and for starters the 1-based index of the source line group it was listed in.

#### Scenario: Starter line groups and captain

- **GIVEN** the source lineup `Chelsea FC: Robert SANCHEZ - Marc CUCURELLA, …, Reece JAMES [c], … - Enzo FERNANDEZ, …`
- **WHEN** the match is ingested
- **THEN** `Robert Sanchez` is a `STARTER` with line 1
- **AND** `Reece James` is a `STARTER` in line 2 with `is_captain` true

#### Scenario: Substitute who came on

- **GIVEN** the lineup fragment `Enzo FERNANDEZ (61' ANDREY SANTOS)`
- **WHEN** the match is ingested
- **THEN** `Andrey Santos` is a `SUBSTITUTE` lineup entry for that side with no line index

### Requirement: Formation

The system SHALL expose, per match and side, a formation string formed by the count of starters in each line group after the first, joined by `-`. It reflects the source's grouping, not an independently verified tactical shape.

#### Scenario: Deriving a formation

- **GIVEN** a side's starters are grouped 1 / 4 / 3 / 3 in the source
- **WHEN** a client GETs `/v1/matches/{id}?expand=lineups`
- **THEN** that side's `formation` is `4-3-3`

### Requirement: Substitutions

The system SHALL store each substitution with its side, minute, the player going off, and the player coming on, including substitutions of players who themselves came on as substitutes.

#### Scenario: Chained substitution

- **GIVEN** the fragment `EMAM ASHOUR (14' ZIZO (79' MOHAMED AFSHA))`
- **WHEN** the match is ingested
- **THEN** there is a substitution at minute 14 with `Emam Ashour` off and `Zizo` on
- **AND** a substitution at minute 79 with `Zizo` off and `Mohamed Afsha` on

### Requirement: Cards

The system SHALL store each card with its side, player, minute, and kind: `YELLOW`, `SECOND_YELLOW`, or `RED`. A second yellow is stored as two cards: the first `YELLOW` and a `SECOND_YELLOW`.

#### Scenario: Second yellow

- **GIVEN** the fragment `Player NAME [Y 20'] [Y/R 78']`
- **WHEN** the match is ingested
- **THEN** that player has a `YELLOW` card at minute 20 and a `SECOND_YELLOW` card at minute 78

#### Scenario: Card shown to a substitute

- **GIVEN** the fragment `JOAO MARIO (77' Nehuen PEREZ [Y 90+1'])`
- **WHEN** the match is ingested
- **THEN** the `YELLOW` card belongs to `Nehuen Perez`, not `Joao Mario`

### Requirement: Event minutes

Every substitution and card SHALL carry a `minute` and a nullable `added_minute` for time added at the end of a half or of extra time.

#### Scenario: Added time

- **GIVEN** a card marked `[Y 90+2']`
- **WHEN** the match is ingested
- **THEN** the card has `minute` 90 and `added_minute` 2

### Requirement: Event player resolution

Each lineup entry, substitution player, and card SHALL reference a squad player of that team-season when the source name resolves to exactly one, compared case- and accent-insensitively. Otherwise it SHALL keep the source name, title-cased, with a null player reference.

#### Scenario: Unresolved name kept as text

- **GIVEN** a lineup name that matches no squad member of that team-season
- **WHEN** the match is ingested
- **THEN** the lineup entry has a null player reference and a title-cased `player_name`

### Requirement: Referee and attendance

The system SHALL store the referee's name (title-cased, without country) and the attendance on the match, both nullable.

#### Scenario: Match header and referee line

- **GIVEN** a header containing `Att: 81118` and a line `Refs: Alireza FAGHANI (AUS)`
- **WHEN** the match is ingested
- **THEN** the match has `attendance` 81118 and `referee` `Alireza Faghani`

### Requirement: Event exposure

The system SHALL embed lineups (with per-side formation), substitutions, and cards in match responses only when requested through `expand=lineups`, `expand=substitutions`, and `expand=cards`. `referee` and `attendance` are always present.

#### Scenario: Expanding events

- **WHEN** a client GETs `/v1/matches/{id}?expand=lineups,substitutions,cards`
- **THEN** the response contains `lineups.home`, `lineups.away` (each with `formation` and entries), `substitutions`, and `cards`

#### Scenario: Not expanded

- **WHEN** a client GETs `/v1/matches/{id}` without `expand`
- **THEN** the response contains no `lineups`, `substitutions`, or `cards` keys

### Requirement: Event coverage

Every match response SHALL include `coverage.events`: `full` when the source supplies lineups, substitutions and cards for that match, `none` otherwise. In this change only FIFA Club World Cup 2025 matches are `full`.

#### Scenario: Competition without event data

- **WHEN** a client GETs a Premier League match with `?expand=lineups,cards`
- **THEN** `lineups.home.entries`, `lineups.away.entries` and `cards` are empty
- **AND** `coverage.events` is `none`

### Requirement: Idempotent event sync

Re-running sync with unchanged sources SHALL leave every event row and UUID unchanged. Lineup entries, substitutions and cards are identified by `(match, side, ordinal)` in source order; ordinals beyond the source's count are deleted.

#### Scenario: Repeat sync

- **GIVEN** Club World Cup 2025 events already synced
- **WHEN** sync runs again with no source change
- **THEN** every lineup entry, substitution and card keeps its UUID and values

#### Scenario: Source drops a card

- **GIVEN** a match synced with 4 home cards
- **WHEN** the source is corrected to 3 home cards and sync runs
- **THEN** home cards with ordinals 1–3 keep their UUIDs and the card with ordinal 4 is deleted
