# match-verification Specification

## Purpose

Checks stored match results against an independent, openly licensed reference so clients can tell which results two sources agree on, without ever changing the data or serving the reference's content.

## Requirements

### Requirement: Reference results for domestic leagues

The system SHALL use the results grid of the English Wikipedia article named by each configured domestic league season as the verification reference. A season that names no article is not verified. Reference teams SHALL be matched to stored teams only through their Wikidata QID.

#### Scenario: Grid resolved for a configured season

- **GIVEN** La Liga 2025-26 is a configured season
- **WHEN** verification runs for La Liga
- **THEN** the reference results are read from the 2025–26 La Liga article's results grid
- **AND** each grid team is identified by the Wikidata QID of the article it links to

#### Scenario: Article reached through a redirect

- **GIVEN** a season names an article title that redirects, such as `2000–01 Premier League` (redirects to `2000–01 FA Premier League`)
- **WHEN** verification runs for that season
- **THEN** the grid of the redirect target is used and its scores are compared

#### Scenario: Season without an article

- **GIVEN** a Serie A season that names no article, while the other Serie A seasons do
- **WHEN** verification runs for Serie A
- **THEN** that season is skipped without a warning and its matches have no status
- **AND** the other Serie A seasons are verified

#### Scenario: Reference team without a known QID

- **GIVEN** a grid team whose linked article has no Wikidata QID, or whose QID matches no stored team
- **WHEN** verification runs
- **THEN** that team's matches are not compared and keep or receive no status
- **AND** a warning naming the team is logged

### Requirement: Verification status per match

Each stored match with a counterpart in the reference SHALL get one status: `VERIFIED` (same home and away score, and the same shootout score when both sources have one), `MISMATCH` (both have a score and they differ), `UNCONFIRMED` (only the stored match has a score), or `SOURCE_BEHIND` (only the reference has one). Matches with no score in either source get no status. An awarded match whose stored score is level gets no status either: the source names no winner, so its score can't be compared with a reference that records the awarded result.

#### Scenario: Scores agree

- **GIVEN** a stored match Sevilla 2–1 Rayo Vallecano and a reference cell 2–1 for the same pairing
- **WHEN** verification runs
- **THEN** the match's status is `VERIFIED`

#### Scenario: Scores differ

- **GIVEN** a stored score 2–1 and a reference score 2–2 for the same pairing
- **WHEN** verification runs
- **THEN** the match's status is `MISMATCH`
- **AND** the stored score is unchanged

#### Scenario: Reference lags behind

- **GIVEN** a stored completed match whose reference cell is empty or a placeholder
- **WHEN** verification runs
- **THEN** the match's status is `UNCONFIRMED`

#### Scenario: Stored data lags behind

- **GIVEN** a stored match with no score whose reference cell has a score
- **WHEN** verification runs
- **THEN** the match's status is `SOURCE_BEHIND`

#### Scenario: Status follows the sources

- **GIVEN** a match that was `UNCONFIRMED`
- **WHEN** the reference later shows the same score and verification runs again
- **THEN** the status becomes `VERIFIED` and its check time is updated

#### Scenario: Awarded match recorded with a level score

- **GIVEN** a stored awarded match SC Bastia 0–0 Olympique Lyonnais and a reference cell 0–3
- **WHEN** verification runs
- **THEN** the match has no status, and any status it had is removed
- **AND** no disagreement is logged for it

#### Scenario: Awarded match recorded with the awarded score

- **GIVEN** a stored awarded match 1. FC Union Berlin 0–2 VfL Bochum 1848 and a reference cell 0–2
- **WHEN** verification runs
- **THEN** the match's status is `VERIFIED`

#### Scenario: Shootout scores compared

- **GIVEN** a stored cup match 1–1 decided 4–1 on penalties and a reference box 1–1 (a.e.t.) (4–2 p)
- **WHEN** verification runs
- **THEN** the match's status is `MISMATCH`

### Requirement: Reference content is never stored or served

The system SHALL NOT store, serve or change match data from the reference. Only the status, the reference's name and the time of the check SHALL be persisted.

#### Scenario: Mismatch leaves no reference data behind

- **GIVEN** a match marked `MISMATCH`
- **WHEN** a client GETs the match
- **THEN** the response contains the stored score and the verification status
- **AND** contains no score or other value taken from the reference

### Requirement: Disagreement report

Each verification run SHALL log one line per `MISMATCH` and `SOURCE_BEHIND` match (season, teams, stored and reference score) and a summary with the count of each status per season.

#### Scenario: Summary after a run

- **WHEN** verification for La Liga finishes
- **THEN** the log contains, for each configured season, the number of `VERIFIED`, `MISMATCH`, `UNCONFIRMED` and `SOURCE_BEHIND` matches

#### Scenario: Mismatch is listed

- **GIVEN** a match marked `MISMATCH`
- **WHEN** verification finishes
- **THEN** the log has a line naming the season, both teams, the stored score and the reference score

### Requirement: Reference unavailable

If the reference for a season can't be fetched or contains no results grid, that season SHALL be skipped with a warning, its existing statuses SHALL be left as they are, and the run SHALL still succeed.

#### Scenario: Article has no grid

- **GIVEN** a season article with no results grid
- **WHEN** verification runs
- **THEN** a warning names the season
- **AND** the other seasons are verified normally

#### Scenario: Reference returns an error

- **GIVEN** the reference API answers with an error or times out
- **WHEN** verification runs
- **THEN** existing statuses for that season are kept
- **AND** the run exits 0

### Requirement: Verification in the API

Match responses SHALL include `verification`: `null` when the match has no status, otherwise an object with `status`, `reference` (`wikipedia`) and `checked_at` (UTC). `/v1/matches` SHALL accept a `verification` filter taking one status.

#### Scenario: Verified match

- **WHEN** a client GETs a match whose status is `VERIFIED`
- **THEN** `verification` is `{"status": "VERIFIED", "reference": "wikipedia", "checked_at": "<UTC timestamp>"}`

#### Scenario: Competition without verification

- **WHEN** a client GETs a UEFA Champions League match
- **THEN** `verification` is `null`

#### Scenario: Listing mismatches

- **WHEN** a client GETs `/v1/matches?verification=MISMATCH`
- **THEN** only matches whose status is `MISMATCH` are returned

#### Scenario: Unknown status filter

- **WHEN** a client GETs `/v1/matches?verification=MAYBE`
- **THEN** the API responds 422 with the standard error envelope

### Requirement: Reference results for domestic cups

The system SHALL use the match boxes of the English Wikipedia article named by each configured domestic cup season as the verification reference. Each box is paired with the stored match of the same home and away teams, identified only through Wikidata QIDs, and, when the pairing occurs more than once, the same date.

#### Scenario: Cup season verified from its article

- **GIVEN** DFB-Pokal 2024-25 names the article `2024–25 DFB-Pokal`
- **WHEN** verification runs for the DFB-Pokal
- **THEN** each of the 63 stored matches is paired with its box in that article and gets a status

#### Scenario: Pairing played twice

- **GIVEN** FA Cup 2023-24 stores Scarborough Athletic v Forest Green Rovers on 4 November (1–1) and on 12 December (2–4)
- **WHEN** verification runs
- **THEN** each stored match is compared with the box of the same date

#### Scenario: Reference box without a result

- **GIVEN** a box whose score reads `w/o`, `Walkover`, `Void`, `Bye` or `v`
- **WHEN** verification runs
- **THEN** the box gives no reference score: a stored match paired with it is `UNCONFIRMED` if it has a score, and gets no status otherwise

#### Scenario: Box with an awarded score

- **GIVEN** a box `3–0 (awd.)` and a stored awarded match 3–0 for the same pairing
- **WHEN** verification runs
- **THEN** the match's status is `VERIFIED`
