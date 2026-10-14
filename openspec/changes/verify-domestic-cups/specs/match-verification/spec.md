# Spec Delta

## ADDED Requirements

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

## MODIFIED Requirements

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
