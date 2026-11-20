## RENAMED Requirements

- FROM: `### Requirement: Awarded matches in grids`
- TO: `### Requirement: Awarded matches from the seed`

## MODIFIED Requirements

### Requirement: Awarded matches from the seed

A grid can't mark a match as awarded, and a match box can give the score without saying the match was awarded. In a season read from Wikipedia, a match listed in `seeds/awarded.yaml` SHALL be stored flagged `awarded`, with the score the grid or box gives and the curated `played` value. An entry for a pairing the season doesn't have SHALL fail that season's sync.

#### Scenario: Awarded match from the seed

- **GIVEN** La Liga 1979-80, and an `awarded.yaml` entry for Málaga v Almería curated as `NONE`
- **WHEN** it is synced
- **THEN** that match is `COMPLETED`, `awarded` and `played` `NONE`, with the grid's score

#### Scenario: Box that doesn't say the match was awarded

- **GIVEN** the 1942 South American Championship, whose box for Argentina v Chile reads 0–0 with no mark, and an `awarded.yaml` entry for it curated as `PARTIAL`
- **WHEN** it is synced
- **THEN** that match is `COMPLETED`, `awarded` and `played` `PARTIAL`, with the score 0–0

### Requirement: Stage from section headings

Each match box SHALL take its stage, and its group or round number where there is one, from the section heading above it: preliminary round, numbered round, group, quarter-finals, semi-finals, third place (`Third place play-off`, `Third-place match`), final (`Final`, `Finals`), and their variants. A replay or play-off of a tie SHALL keep the stage of that tie. A heading that only wraps rounds (`Knockout phase`, `Final phase`, `Tournament phase`, `Qualifying phase`) SHALL name no stage, so the round under it decides. A box under a heading that maps to no stage SHALL fail the season.

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

#### Scenario: Two-legged final

- **GIVEN** the 1975 Copa América boxes under `Knockout stage / Finals`: two legs and a play-off
- **WHEN** they are read
- **THEN** all three have stage `FINAL`

#### Scenario: Third-place match

- **GIVEN** the 1993 Copa América box under `Knockout stage / Third-place match`
- **WHEN** it is read
- **THEN** its stage is `THIRD_PLACE`

## ADDED Requirements

### Requirement: Headings renamed to rounds

A Wikipedia season seeded with `wikipedia_rounds` SHALL read the boxes under each listed heading as the round label given for it, and take their stage from that label. A listed heading that the pinned pages don't have SHALL fail the season, so a moved pin can't silently stop renaming a round.

#### Scenario: Tournament played as one round robin

- **GIVEN** the 1916 South American Championship, whose boxes sit under `Results`, seeded with `wikipedia_rounds: {Results: Group stage}`
- **WHEN** it is synced
- **THEN** its matches have stage `GROUP` with no group name, and form one table of four teams

#### Scenario: Final round that is a group

- **GIVEN** the 1989 Copa América, whose four-team final round sits under `Final round`, seeded with `wikipedia_rounds: {Final round: Second group stage}`
- **WHEN** it is synced
- **THEN** those matches have stage `GROUP` in phase 2, not `FINAL`

#### Scenario: Heading that isn't there

- **GIVEN** a season seeded with `wikipedia_rounds: {Results: Group stage}` whose pinned pages have no `Results` section
- **WHEN** it is synced
- **THEN** the season fails with an error naming the heading

### Requirement: Abandoned matches replayed

A Wikipedia season seeded with `wikipedia_abandoned` SHALL store each listed match (date, home and away QIDs) as `CANCELLED` without a score, since it was replayed and the replay is the result. A listed match that no box holds SHALL fail the season.

#### Scenario: 1916 Argentina v Uruguay

- **GIVEN** the 1916 South American Championship, whose boxes include Argentina v Uruguay on 16 July, abandoned at 0–0, and its replay on 17 July, with the first listed under `wikipedia_abandoned`
- **WHEN** it is synced
- **THEN** the 16 July match is `CANCELLED` without a score
- **AND** the table counts the 17 July match, so each team has played 3
