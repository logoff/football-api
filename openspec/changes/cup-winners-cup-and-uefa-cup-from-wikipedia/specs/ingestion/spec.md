## MODIFIED Requirements

### Requirement: Stage from section headings

Each match box SHALL take its stage, and its group or round number where there is one, from the section heading above it: preliminary round, numbered round, group, quarter-finals, semi-finals, final, and their variants. A replay or play-off of a tie SHALL keep the stage of that tie. A heading that only wraps rounds (`Knockout phase`, `Final phase`, `Tournament phase`, `Qualifying phase`) SHALL name no stage, so the round under it decides. A box under a heading that maps to no stage SHALL fail the season.

#### Scenario: Numbered rounds and groups

- **GIVEN** boxes under `First round`, `Group B` and `Quarter-finals`
- **WHEN** they are read
- **THEN** their stages are `ROUND` with matchday 1, `GROUP` with group `B`, and `QF`

#### Scenario: Unknown heading

- **GIVEN** a box under the heading `Trivia`
- **WHEN** the season is synced
- **THEN** the season fails with an error naming the page, revision and heading

#### Scenario: Round under a phase wrapper

- **GIVEN** the 1999–2000 UEFA Cup box under `Final phase / Third round`
- **WHEN** it is read
- **THEN** its stage is `ROUND` with matchday 3, not `FINAL`

### Requirement: Teams resolved by Wikidata QID

A team in a Wikipedia season SHALL resolve through the Wikidata QID of the club article its box links, to the team seeded with that QID or listing it under `reference_wikidata`. A club the box links to an article with no QID SHALL take the QID the season seed gives for that title (`wikipedia_qids`). Otherwise, a box linking an article with no QID, or a QID that no team is seeded with, SHALL fail the season, as an unknown spelling does.

#### Scenario: Known club

- **GIVEN** a box linking `Real Madrid CF`, whose QID is Q8682
- **WHEN** it is read
- **THEN** the match's team is the team seeded with Q8682, the same one the openfootball seasons use

#### Scenario: Club not seeded

- **GIVEN** a box linking a club whose QID no team in `seeds/teams.yaml` has
- **WHEN** the season is synced
- **THEN** the season fails with an error naming the article and the QID

#### Scenario: Club article that doesn't exist

- **GIVEN** the 1996–97 UEFA Cup, whose box links `Khazri Buzovna`, an article that doesn't exist, and a season seed giving `Khazri Buzovna: Q2338519`
- **WHEN** it is synced
- **THEN** the match's team is the team seeded with Q2338519

## ADDED Requirements

### Requirement: Sections left out

A Wikipedia season seeded with `wikipedia_skip` SHALL read no box under a section whose heading is one of those listed. A listed section that the pinned pages don't have SHALL fail the season, so a moved pin can't silently stop leaving a round out.

#### Scenario: Qualifying round left out

- **GIVEN** the 1997–98 UEFA Cup seeded with `wikipedia_skip: [First qualifying round, Second qualifying round]`
- **WHEN** it is synced
- **THEN** the season has the matches from the first round to the final, and none of the qualifying rounds

#### Scenario: Section that isn't there

- **GIVEN** a season seeded with `wikipedia_skip: [Preliminary round]` whose pinned pages have no such section
- **WHEN** it is synced
- **THEN** the season fails with an error naming the section
