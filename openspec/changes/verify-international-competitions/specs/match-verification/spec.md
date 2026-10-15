# Spec Delta

## RENAMED Requirements

- FROM: `### Requirement: Reference results for domestic cups`
- TO: `### Requirement: Reference results for cups and tournaments`

## MODIFIED Requirements

### Requirement: Reference results for cups and tournaments

The system SHALL use the match boxes of the English Wikipedia article named by each configured cup or tournament season as the verification reference, together with the sub-articles it links whose titles extend its own (for example `2022 FIFA World Cup Group A`, `2023–24 UEFA Champions League knockout phase`). Qualifying sub-articles are read only for seasons that hold qualifying matches; sub-articles about squads, other editions (women's, futsal) or non-match topics are not read, and a box found more than once is used once. Each box is paired with the stored match of the same home and away teams, identified only through Wikidata QIDs, and, when the pairing occurs more than once, the same date.

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

#### Scenario: Season spread over several articles

- **GIVEN** CONMEBOL Copa Libertadores 2024 names the article `2024 Copa Libertadores`
- **WHEN** verification runs
- **THEN** the boxes of its `qualifying stages`, `group stage` and `final stages` sub-articles are read
- **AND** its `Femenina` and `de Futsal` sub-articles are not

#### Scenario: Separate qualification tournament

- **GIVEN** the UEFA Euro 2024 article links `UEFA Euro 2024 qualifying`, and the season holds no qualifying matches
- **WHEN** verification runs
- **THEN** the qualification article is not read

#### Scenario: Same match in the main article and a sub-article

- **GIVEN** the 2022 FIFA World Cup article and its `Group A` sub-article both show Qatar v Ecuador
- **WHEN** verification runs
- **THEN** the match is compared once

#### Scenario: Teams named the other way round

- **GIVEN** openfootball lists the 1990 quarter-final as Yugoslavia v Argentina, and the Wikipedia box as Argentina v Yugoslavia, both on 30 June 1990
- **WHEN** verification runs
- **THEN** they are compared, with the box's score and shoot-out read the other way round
