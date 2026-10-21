# Spec Delta

## ADDED Requirements

### Requirement: Reference line-ups

For cups and tournaments, the system SHALL use as the events reference the line-up table that follows the match box paired with a stored match: the starters and substitutes who came on for each side, with their bookings, dismissals and substitutions. When the same match appears in several articles, the table SHALL be taken from whichever copy has one. No other page SHALL be fetched for it.

#### Scenario: Table after a group match

- **GIVEN** the `2022 FIFA World Cup Group A` article shows Qatar v Ecuador followed by its line-ups
- **WHEN** verification runs for the 2022 World Cup
- **THEN** the stored events of Qatar v Ecuador are compared with that table

#### Scenario: Table only in the sub-article

- **GIVEN** the 2022 FIFA World Cup article shows Qatar v Ecuador without line-ups, and its `Group A` sub-article shows it with them
- **WHEN** verification runs
- **THEN** the sub-article's table is used

#### Scenario: Table without shirt numbers

- **GIVEN** a 1934 World Cup line-up table whose rows have a position and a name but no number
- **WHEN** verification runs
- **THEN** the table is read and compared like any other

### Requirement: Events status per match

Each stored match paired with a match box SHALL get an events status, separate from its result status: `VERIFIED` (the stored events and the table agree), `MISMATCH` (they differ), `UNCONFIRMED` (only the stored match has events) or `SOURCE_BEHIND` (only the table exists). A match with neither gets no events status, nor does a match with no paired box.

#### Scenario: Everything agrees

- **GIVEN** a stored match whose starters, substitutes, substitutions and cards all agree with its table
- **WHEN** verification runs
- **THEN** the match's events status is `VERIFIED`

#### Scenario: Missing dismissal

- **GIVEN** stored events for Serbia v Ghana (2010) with Luković booked at 73', and a table with Luković booked at 54' and sent off for a second yellow at 74'
- **WHEN** verification runs
- **THEN** the match's events status is `MISMATCH`
- **AND** the stored events are unchanged

#### Scenario: Box without a table

- **GIVEN** a stored 2010 Club World Cup semi-final with events, whose box has no line-up table
- **WHEN** verification runs
- **THEN** the match's events status is `UNCONFIRMED`

#### Scenario: League match

- **WHEN** verification runs for Premier League 2025-26, whose stored matches have events
- **THEN** no match gets an events status

### Requirement: Events comparison

The comparison SHALL cover, for both sides, the starters, the substitutes who came on, the substitutions (player off, player on, minute) and, for matches from 1970 on, the cards (player, kind, minute). Minutes SHALL agree when they differ by at most one; added minutes SHALL be compared only when both sources have one. A Wikipedia second-yellow dismissal SHALL count as a `YELLOW` and a `SECOND_YELLOW`.

#### Scenario: Minute rounded differently

- **GIVEN** a stored booking at 18' and the same player's booking at 19' in the table
- **WHEN** verification runs
- **THEN** the bookings agree

#### Scenario: Second yellow

- **GIVEN** a stored `YELLOW` at 54' and `SECOND_YELLOW` at 74' for a player, and `{{sent off|2|54|74}}` for him in the table
- **WHEN** verification runs
- **THEN** the cards agree

#### Scenario: Cards before 1970

- **GIVEN** a 1966 match whose stored events record a caution that the table doesn't show, and whose line-ups agree
- **WHEN** verification runs
- **THEN** the match's events status is `VERIFIED`

### Requirement: Player pairing

Players SHALL be paired within one side of one match: first by name, ignoring case, accents, punctuation, spaces and the captain mark; then by a single shared name word; then by shirt number, when both the stored player's squad entry and the table have one. A player left unpaired SHALL be a difference.

#### Scenario: Accents and case

- **GIVEN** a stored `Sergej MILINKOVIC-SAVIC` and a table row `Sergej Milinković-Savić`
- **WHEN** verification runs
- **THEN** they are the same player

#### Scenario: Common name

- **GIVEN** a stored `SAAD ALSHEEB` and a table row `Saad Al-Sheeb`
- **WHEN** verification runs
- **THEN** they are the same player

#### Scenario: Spelling variant

- **GIVEN** a stored `Hans JEPPSSON` with no shirt number and a table row `Hans Jeppson`
- **WHEN** verification runs
- **THEN** they are paired by the shared word `hans` when no other player on the side shares it

### Requirement: Events disagreement report

Each verification run SHALL log one line per events `MISMATCH` and `SOURCE_BEHIND` match, naming the season, both teams and each difference with the stored and the reference value, and SHALL add the count of each events status to the season's summary line. A season that isn't verified again SHALL log the same lines from its stored statuses, as for results.

#### Scenario: Mismatch is listed

- **GIVEN** a match whose events status is `MISMATCH`
- **WHEN** verification finishes
- **THEN** the log has a line starting `<competition> <season>: MISMATCH events <home> v <away>: stored` that names each difference

### Requirement: Events verification in the API

Match responses SHALL include `events_verification`: `null` when the match has no events status, otherwise an object with `status`, `reference` (`wikipedia`) and `checked_at` (UTC). `/v1/matches` SHALL accept an `events_verification` filter taking one status. `verification` SHALL keep describing the result only.

#### Scenario: Verified events

- **WHEN** a client GETs a match whose events status is `VERIFIED`
- **THEN** `events_verification` is `{"status": "VERIFIED", "reference": "wikipedia", "checked_at": "<UTC timestamp>"}`

#### Scenario: Listing events mismatches

- **WHEN** a client GETs `/v1/matches?events_verification=MISMATCH`
- **THEN** only matches whose events status is `MISMATCH` are returned
