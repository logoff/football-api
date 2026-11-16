## ADDED Requirements

### Requirement: Wikipedia season source

A season seeded with `wikipedia_source` SHALL be read from the match boxes of the English Wikipedia pages it lists, each pinned to a revision ID, and SHALL NOT be read from the live pages. The pages are the season article and the sub-articles it needs. Each box is used once. A season seeded with both a Wikipedia source and an openfootball file SHALL fail the seed load.

#### Scenario: Season read from pinned revisions

- **GIVEN** European Cup 1955-56 pinned to revision 1384458360 of `1955–56 European Cup`
- **WHEN** the sync runs
- **THEN** the season has the 29 matches of that revision's boxes, each `COMPLETED` with its date and score

#### Scenario: Article edited after pinning

- **GIVEN** a pinned season whose article has since been edited on Wikipedia
- **WHEN** the sync runs
- **THEN** the stored matches still come from the pinned revision

#### Scenario: Unrelated sub-articles

- **GIVEN** the article `1960–61 European Cup`, which links `1960–61 European Cup Winners' Cup`
- **WHEN** its pins are written
- **THEN** the Winners' Cup article is not pinned, and none of its matches are stored in the European Cup season

### Requirement: Pinned revisions are cached

A pinned revision SHALL be fetched from Wikipedia at most once and kept under `SOURCES_DIR`. If a revision can't be fetched, that season's sync SHALL fail and leave its stored data as it was, as for a source file that can't be parsed.

#### Scenario: Second sync

- **GIVEN** a sync that fetched every pinned revision
- **WHEN** the sync runs again with the same pins
- **THEN** no request is sent to Wikipedia for those revisions

#### Scenario: Wikipedia unreachable

- **GIVEN** a season whose pin moved to a revision that isn't cached
- **WHEN** the sync runs and Wikipedia can't be reached
- **THEN** that season fails, its stored matches are unchanged, and the other seasons sync

### Requirement: Stage from section headings

Each match box SHALL take its stage, and its group or round number where there is one, from the section heading above it: preliminary round, numbered round, group, quarter-finals, semi-finals, final, and their variants. A replay or play-off of a tie SHALL keep the stage of that tie. A box under a heading that maps to no stage SHALL fail the season.

#### Scenario: Numbered rounds and groups

- **GIVEN** boxes under `First round`, `Group B` and `Quarter-finals`
- **WHEN** they are read
- **THEN** their stages are `ROUND` with matchday 1, `GROUP` with group `B`, and `QF`

#### Scenario: Unknown heading

- **GIVEN** a box under the heading `Trivia`
- **WHEN** the season is synced
- **THEN** the season fails with an error naming the page, revision and heading

### Requirement: Teams resolved by Wikidata QID

A team in a Wikipedia season SHALL resolve through the Wikidata QID of the club article its box links, to the team seeded with that QID or listing it under `reference_wikidata`. A box linking an article with no QID, or a QID that no team is seeded with, SHALL fail the season, as an unknown spelling does.

#### Scenario: Known club

- **GIVEN** a box linking `Real Madrid CF`, whose QID is Q8682
- **WHEN** it is read
- **THEN** the match's team is the team seeded with Q8682, the same one the openfootball seasons use

#### Scenario: Club not seeded

- **GIVEN** a box linking a club whose QID no team in `seeds/teams.yaml` has
- **WHEN** the season is synced
- **THEN** the season fails with an error naming the article and the QID

### Requirement: Walkovers

A box with no result (`w/o`, `Walkover`, or a tie a club withdrew from) SHALL be stored `CANCELLED` without a score. A box marked awarded SHALL be stored `COMPLETED`, flagged `awarded`, with the score it gives.

#### Scenario: Withdrawal

- **GIVEN** the 1961-62 box Linfield v Vorwärts Berlin (article `1. FC Frankfurt`), which gives no result
- **WHEN** it is read
- **THEN** the match is `CANCELLED` and has no score

#### Scenario: Awarded

- **GIVEN** the 2004-05 box Roma 0–3 Dynamo Kyiv (awd.)
- **WHEN** it is read
- **THEN** the match is `COMPLETED`, `awarded`, 0–3

## MODIFIED Requirements

### Requirement: Unchanged seasons are skipped

A season whose inputs (the code, its seed entries, `seeds/teams.yaml`, every source file it reads, and the revision IDs it is pinned to) are unchanged since its last successful sync SHALL NOT be re-synced, and SHALL log one line saying it is unchanged, with its match count. A season that fails to sync SHALL be synced again on the next run.

#### Scenario: Nothing changed

- **GIVEN** a database after a successful sync
- **WHEN** the sync runs again with the same sources, seeds and code
- **THEN** no season is re-synced
- **AND** every season logs that it is unchanged, with its match count
- **AND** the command exits 0

#### Scenario: Upstream correction to one season

- **GIVEN** a database after a successful sync
- **WHEN** openfootball corrects a score in one season's file and the sync runs
- **THEN** only that season is re-synced, and the corrected score is stored

#### Scenario: Seed or code change

- **GIVEN** a database after a successful sync
- **WHEN** `seeds/teams.yaml` or the code changes and the sync runs
- **THEN** every season is re-synced

#### Scenario: Squad or events file changes

- **GIVEN** a season with a squads or events file
- **WHEN** only that file changes and the sync runs
- **THEN** the season is re-synced

#### Scenario: A failed season is retried

- **GIVEN** a season whose sync failed on the previous run
- **WHEN** the sync runs again with the same sources
- **THEN** the season is synced again

#### Scenario: Pin moved

- **GIVEN** a Wikipedia season after a successful sync
- **WHEN** one of its pins moves to another revision and the sync runs
- **THEN** only that season is re-synced
